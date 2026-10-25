# Deep Search Pro 文件存储架构设计

## 1. 文档信息

- 项目：Deep Search Pro
- 后端：`deep-search-pro-master-be`
- 前端：`deep-search-pro-master-fe`
- 日期：2026-10-21
- 方案：MinIO 持久化 + MySQL 元数据 + 本地临时工作区
- 适用形态：个人本地版

## 2. 背景与目标

当前项目长期保存上传文件和 Agent 生成文件到 `output/session_{thread_uuid}`。随着文件增加，项目目录持续膨胀，代码、运行数据和永久文件混合，不利于迁移、备份和生命周期管理。

改造目标：

1. MySQL 只保存文件元信息、会话关系、状态和 MinIO object key，不保存二进制。
2. MinIO 永久保存上传文件和 Agent 生成文件。
3. 保留 `OUTPUT`、`UPLOAD` 配置，但其会话子目录只作为临时目录。
4. 保留现有 `ContextVar`、路径安全逻辑和依赖本地路径的 Agent 文件工具。
5. 下载由后端鉴权并生成短期预签名 URL，浏览器直连 MinIO。
6. Agent 经营数据库只读连接与工作台应用数据库可写连接完全隔离。

## 3. 已确认的总体设计

```text
MySQL
└─ 文件元信息、会话关系、状态、object_key

MinIO
└─ 上传文件和 Agent 生成文件的永久内容

output/session_{thread_uuid}
└─ Agent 单次执行期间的临时工作区

updated/session_{thread_uuid}
└─ 前端文件上传到 MinIO 前的临时暂存区
```

继续保留：

```python
OUTPUT = ROOT / 'output'
UPLOAD = ROOT / 'updated'
```

`output/` 和 `updated/` 根目录可长期存在；`session_{thread_uuid}` 子目录按需创建、用完删除。不保留 `.keep`、`.source` 或其他空文件。

## 4. 总体架构

```text
                              ┌────────────────────┐
                              │      Vue 前端       │
                              │ 上传：multipart     │
                              │ 下载：预签名 URL    │
                              └─────────┬──────────┘
                                        │ HTTP API
                                        ▼
┌──────────────────────────────────────────────────────────┐
│                         FastAPI                          │
│  server.py                                               │
│  ├─ 上传、列表、下载地址、会话删除接口                   │
│  └─ Agent 任务编排                                       │
│                  │                                       │
│                  ▼                                       │
│  FileService                                             │
│  ├─ 文件状态管理                                         │
│  ├─ 准备/清理 Agent 工作区                               │
│  ├─ 发布 Agent 生成文件                                  │
│  ├─ 创建预签名 URL                                       │
│  └─ 删除会话文件                                         │
│            │                           │                 │
│            ▼                           ▼                 │
│  FileRepository                 MinioStorage             │
└────────────┬───────────────────────────┬─────────────────┘
             │                           │
             ▼                           ▼
      ┌─────────────┐             ┌─────────────┐
      │ 工作台 MySQL │             │    MinIO    │
      │ 文件元信息   │             │ 文件二进制   │
      └─────────────┘             └─────────────┘
```

Agent 执行链路：

```text
MySQL 查询 ready 文件
        ↓
MinIO 下载到 output/session_{thread_uuid}
        ↓
ContextVar 指向该临时目录
        ↓
Agent 使用原来的文件工具
        ↓
扫描新增或修改文件
        ↓
上传 MinIO 并写入 MySQL
        ↓
清理本地临时目录
```

## 5. 数据库和账号隔离

工作台数据与经营业务数据使用不同数据库。可以共用一个 MySQL Server，但必须使用不同 database、不同账号和不同连接池。

```text
MySQL Server
├─ business_data
│  └─ 原有经营业务表
│     └─ agent_reader 只读
│
└─ deep_search_workbench
   └─ files
      └─ deep_search_app 可读写
```

### 5.1 Agent 经营数据库

继续由 `tools/db_tools.py` 管理：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=agent_reader
MYSQL_PASSWORD=...
MYSQL_DATABASE=business_data
```

账号只允许查询，不能访问工作台 `files` 表，也不能获得 MinIO 密钥。

### 5.2 工作台应用数据库

```env
APP_MYSQL_HOST=127.0.0.1
APP_MYSQL_PORT=3306
APP_MYSQL_USER=deep_search_app
APP_MYSQL_PASSWORD=...
APP_MYSQL_DATABASE=deep_search_workbench
```

应用账号只维护工作台数据库。建表和迁移由管理账号执行，应用账号原则上不授予 `CREATE`、`ALTER`、`DROP`。

```text
Agent → tools/db_tools.py → MYSQL_* → business_data → 只读

FastAPI → FileRepository → APP_MYSQL_* → deep_search_workbench → 可读写
```

两套连接不复用、不跨库 JOIN、不在同一事务中混合操作。

## 6. files 表设计

```sql
CREATE TABLE files (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部自增主键',
    uuid CHAR(36) NOT NULL COMMENT '对外文件UUID',
    thread_uuid CHAR(36) NOT NULL COMMENT '所属会话UUID',
    original_name VARCHAR(255) NOT NULL COMMENT '上传或生成时的原始文件名',
    workspace_name VARCHAR(255) NOT NULL COMMENT 'Agent工作区中的唯一文件名',
    object_key VARCHAR(512) NOT NULL COMMENT 'MinIO对象键，不含bucket和endpoint',
    content_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream' COMMENT 'MIME类型',
    size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '文件大小，字节',
    sha256 CHAR(64) NOT NULL COMMENT '文件SHA-256摘要',
    file_source VARCHAR(16) NOT NULL COMMENT 'uploaded或generated',
    file_status VARCHAR(16) NOT NULL COMMENT 'pending、ready、failed、deleting',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间，UTC',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间，UTC',
    deleted_at DATETIME(3) NULL DEFAULT NULL COMMENT '软删除时间，NULL表示未删除',
    PRIMARY KEY pk_id (id),
    UNIQUE KEY uk_uuid (uuid),
    UNIQUE KEY uk_object_key (object_key),
    KEY idx_thread_uuid_id (thread_uuid, id),
    KEY idx_thread_uuid_status_id (thread_uuid, file_status, id)
)
ENGINE=InnoDB
DEFAULT CHARACTER SET=utf8mb4
COLLATE=utf8mb4_0900_ai_ci
COMMENT='工作台文件元信息';
```

字段说明：

| 字段 | 用途 |
|---|---|
| `id` | MySQL 内部自增聚簇主键 |
| `uuid` | 对外 file ID，用于前端和 API |
| `thread_uuid` | 文件所属会话 |
| `original_name` | 用户提供或 Agent 生成的原始名称 |
| `workspace_name` | 临时工作区中的唯一名称 |
| `object_key` | MinIO object key |
| `file_source` | `uploaded` 或 `generated` |
| `file_status` | `pending`、`ready`、`failed`、`deleting` |
| `deleted_at` | 软删除时间 |

## 7. Bucket 与 object key

项目只使用一个 bucket，bucket 名放在配置中：

```env
MINIO_BUCKET=deep-search-files
```

数据库不保存 bucket、endpoint、完整 URL或预签名 URL，只保存 object key。

上传文件：

```text
sessions/{thread_uuid}/uploads/{file_uuid}/{original_name}
```

Agent 生成文件：

```text
sessions/{thread_uuid}/generated/{file_uuid}/{original_name}
```

示例：

```text
sessions/ba2d.../uploads/55f3.../销售数据.xlsx
sessions/ba2d.../generated/782e.../华东区销售报告.pdf
```

UUID 防止同名覆盖，最后一段保留文件名以便 MinIO 控制台识别。应用不解析 object key 获取文件名，始终读取 MySQL 的 `original_name` 或 `workspace_name`。

同一会话存在同名文件时：

```text
original_name  = 销售数据.xlsx
workspace_name = 销售数据.xlsx

original_name  = 销售数据.xlsx
workspace_name = 销售数据 (1).xlsx
```

MinIO 通过不同 `file_uuid` 隔离，本地通过不同 `workspace_name` 隔离。前端展示 `workspace_name`，确保用户看到的名称与 Agent 实际可读取名称一致。

## 8. MinIO 配置

```env
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_PUBLIC_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET=deep-search-files
MINIO_SECURE=false
MINIO_DOWNLOAD_EXPIRES_SECONDS=600
WORKSPACE_MAX_AGE_HOURS=24
```

- `MINIO_ENDPOINT`：后端访问地址。
- `MINIO_PUBLIC_ENDPOINT`：浏览器可访问、用于签名的地址。
- Docker 内部地址如 `minio:9000` 通常不能直接返回浏览器。
- 签名 Host 必须与浏览器实际访问 Host 一致。

## 9. 上传流程

```text
前端上传 multipart 文件
    ↓
FastAPI 校验数量、文件名、后缀和大小
    ↓
生成 file_uuid，确定 workspace_name 与 object_key
    ↓
MySQL 插入 file_status=pending
    ↓
暂存到 updated/session_{thread_uuid}
    ↓
计算 size_bytes 和 sha256
    ↓
上传 MinIO
    ↓
MySQL 更新 file_status=ready
    ↓
删除临时文件和空的 session 子目录
    ↓
返回文件元信息
```

上传失败时设置 `file_status=failed`。无论成功失败，本地文件都在 `finally` 中清理。个人本地版第一阶段仍由 FastAPI 接收上传，不增加浏览器直传、分片和 finalize 接口。

## 10. Agent 临时工作区

当前同一会话同时只允许一个任务，因此继续使用：

```text
output/session_{thread_uuid}
```

任务开始：

1. 安全清理上次异常残留目录。
2. 创建 `output/session_{thread_uuid}`。
3. 查询 `deleted_at IS NULL AND file_status='ready'` 的会话文件。
4. 根据 object key 从 MinIO 下载，本地名称使用 `workspace_name`。
5. 记录输入文件路径和 SHA-256 manifest。
6. 将 ContextVar 指向工作区。
7. Agent 继续调用现有文件工具。

任务结束后比较文件清单：

- 不在输入 manifest 中：本次新生成文件。
- 在 manifest 中但 SHA-256 改变：Agent 修改后的生成版本。
- 在 manifest 中且 SHA-256 未改变：原始输入，不重复上传。

被修改的输入文件不覆盖原对象，必须生成新 `file_uuid`，以 `generated` 身份上传。

## 11. Agent 生成文件发布

```text
Agent 生成 Markdown/PDF 等文件
    ↓
Agent 正常完成
    ↓
扫描新增或修改文件
    ↓
为每个文件生成 file_uuid
    ↓
MySQL 插入 pending
    ↓
上传到 sessions/{thread_uuid}/generated/{file_uuid}/{original_name}
    ↓
MySQL 更新 ready
    ↓
任务标记成功
    ↓
finally 删除 output/session_{thread_uuid}
```

所有生成文件发布成功后才能向前端报告任务成功。Agent 失败或取消时不发布未完成结果，并清理临时工作区。

## 12. 下载流程

接口：

```http
POST /api/files/{file_uuid}/download-url
```

```text
前端提交 file_uuid
    ↓
后端查询工作台 MySQL
    ↓
校验文件存在、ready、未删除、属于当前会话/用户
    ↓
读取 object_key
    ↓
MinIO 生成短期预签名 URL
    ↓
返回前端
    ↓
浏览器直连 MinIO 下载
```

响应示例：

```json
{
  "downloadUrl": "http://127.0.0.1:9000/deep-search-files/...?X-Amz-Signature=...",
  "expiresIn": 600
}
```

前端不能提交 object key，也不能持久保存预签名 URL。文件流不经过 FastAPI。

## 13. 会话删除

```text
DELETE /api/sessions/{thread_uuid}
    ↓
检查任务和上传是否正在运行
    ↓
将文件标记为 deleting
    ↓
删除 MinIO 对象
    ↓
全部成功后写入 deleted_at
    ↓
删除 LangGraph checkpoint
    ↓
删除 tasks/events
    ↓
清理 output 和 updated 残留目录
    ↓
返回 204
```

对象已经不存在时视为成功，保证接口幂等。MinIO 删除失败时保留 `deleting` 并允许重试，不提前删除 checkpoint 和任务记录。

## 14. 一致性与恢复

MySQL 与 MinIO 没有跨系统事务。数据库事务中不能执行 MinIO 网络请求，通过状态机实现最终一致性。

```text
上传：pending → ready / failed

删除：ready → deleting → deleted_at
                    └→ 失败时保持 deleting
```

临时目录清理：

- 正常完成、异常或取消时在 `finally` 清理。
- 强制结束、断电可能留下文件。
- 启动时只清理超过 `WORKSPACE_MAX_AGE_HOURS` 的目录。
- 不无条件删除全部目录，避免 `--reload` 新旧进程交叉误删。

## 15. 后端代码边界

保持不变或基本不变：

```text
api/context.py
utils/path_utils.py
tools/markdown_tools.py
tools/pdf_tools.py
tools/upload_file_read_tool.py
```

新增：

```text
api/file_repository.py   # files 表 CRUD 和状态变更
api/minio_storage.py     # put/get/remove/presigned_get
api/file_service.py      # 编排 MySQL、MinIO、临时目录
migrations/001_create_files.sql
```

修改 `api/settings.py`：

- 保留 `OUTPUT`、`UPLOAD`。
- 增加 `APP_MYSQL_*`、`MINIO_*` 和临时目录过期配置。

修改 `api/server.py`：

- lifespan 初始化应用数据库、MinIO Client 和 FileService。
- 上传调用 FileService。
- 文件列表查询 MySQL。
- 下载返回预签名 URL。
- 会话删除清理 MySQL/MinIO 文件。
- Agent 调用增加 `run_id` 和 FileService。

修改 `agent/main_agent.py`：

- 删除 `copy_legacy_uploads()`。
- 执行前 `prepare_workspace()`。
- ContextVar 继续指向 `OUTPUT/session_{thread_uuid}`。
- 成功后 `publish_generated_files()`。
- `finally` 清理工作区。

依赖增加 MinIO Python SDK和独立的应用数据库访问配置，不复用 Agent 只读数据层。

## 16. 前端调整

涉及：

```text
src/types/workbench.ts
src/api/workbench.ts
src/stores/useWorkbenchStore.ts
src/components/files/ExecutionPanel.vue
```

文件模型：

```typescript
interface SessionFile {
  uuid: string
  originalName: string
  workspaceName: string
  contentType: string
  sizeBytes: number
  source: 'uploaded' | 'generated'
  createdAt: string
}
```

前端不保存 object key、bucket、endpoint 或预签名 URL。点击下载时请求 URL，然后执行：

```typescript
window.location.assign(downloadUrl)
```

## 17. 旧文件迁移

现有 `output/session_*` 和 `updated/session_*` 不能直接删除。新增一次性脚本：

```text
scripts/migrate_local_files.py
```

迁移步骤：

1. 扫描现有会话目录。
2. 根据旧 `.source` 标记识别 uploaded/generated。
3. 计算 SHA-256 和大小。
4. 创建 pending 记录。
5. 上传 MinIO。
6. 更新 ready。
7. 输出迁移报告。
8. 人工验证后再清理旧目录。

## 18. 分阶段实施

### 阶段一：基础设施与数据层

- 创建工作台数据库和独立账号。
- 创建 `files` 表和 MinIO bucket。
- 实现 FileRepository、MinioStorage、FileService。
- 完成数据库和对象存储测试。

### 阶段二：上传与列表

- 上传文件经 `UPLOAD` 暂存后写入 MinIO。
- 元信息写入 MySQL。
- 文件列表改为查询 MySQL。
- 前端适配 UUID 和新字段。

### 阶段三：Agent 工作区

- 执行前从 MinIO 下载输入。
- ContextVar 继续暴露本地路径。
- 执行后上传新增和修改文件。
- 清理 `OUTPUT/session_*`。

### 阶段四：下载、删除和恢复

- 下载改为预签名 URL。
- 会话删除同步清理 MinIO 与 MySQL。
- 增加失败恢复和过期工作区清理。

### 阶段五：旧数据迁移

- 运行迁移脚本。
- 核对报告并备份。
- 清理旧文件。

## 19. 验收标准

1. 上传成功后 MinIO 存在对象、MySQL 为 ready、本地暂存目录无残留。
2. Agent 能从 MinIO 恢复会话文件并继续使用现有本地工具。
3. Agent 生成文件成功上传并写入 MySQL，工作区随后清理。
4. Agent 失败或取消后也会清理工作区，未完成文件不显示为 ready。
5. 前端只通过 file UUID 下载，不接触 object key。
6. 下载文件流不经过 FastAPI。
7. 预签名 URL 不写入数据库或浏览器持久化存储。
8. 同名文件在 MinIO 和本地工作区均不会覆盖。
9. 会话删除后 MinIO、MySQL、checkpoint 和任务记录均被清理。
10. Agent 账号不能写业务数据或访问工作台表。
11. 工作台账号不能访问经营数据库。
12. 过期临时目录可以安全恢复和清理。

## 20. 本次不包含

- 浏览器预签名直传 MinIO。
- 大文件分片和断点续传。
- Celery 任务队列。
- 多 bucket 或租户独立 bucket。
- 文件版本历史界面。
- 在线预览、全文检索和 MinIO 高可用集群。

这些能力可在本架构上扩展，但不进入个人本地版第一阶段。
