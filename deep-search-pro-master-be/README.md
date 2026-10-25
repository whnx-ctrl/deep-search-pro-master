<p align="center">
  <h1 align="center">🤖 Deep Search Pro Backend</h1>
  <p align="center"><b>面向个人本地研究工作台的多智能体后端服务</b></p>
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.12-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.129.2-green.svg" alt="FastAPI">
    <img src="https://img.shields.io/badge/LangChain-1.2.10-orange.svg" alt="LangChain">
    <img src="https://img.shields.io/badge/deepagents-0.4.3-purple.svg" alt="deepagents">
    <img src="https://img.shields.io/badge/Docker-ready-2496ED.svg" alt="Docker">
  </p>
</p>

---

## 🎯 项目概览

Deep Search Pro Backend 是 Deep Search Pro 本地工作台的后端服务。它以主智能体为统一入口，根据运行环境中已配置的能力，动态调度网络搜索、数据库查询和知识库检索子智能体，并提供任务执行、实时事件、文件管理、会话清理与 PDF 生成等能力。

本目录仅包含后端。完整的前后端分离部署、端口映射和 Docker Compose 操作请查看[项目根目录 README](../README.md)。

### 当前能力

| 能力 | 实现方式 | 状态 |
|------|----------|------|
| 多智能体编排 | DeepAgents + LangGraph，主智能体按能力动态挂载子智能体 | ✅ 已实现 |
| 异步任务 | FastAPI 后台任务 + SQLite 任务状态存储 | ✅ 已实现 |
| 实时事件 | WebSocket 多连接广播，事件先持久化再推送 | ✅ 已实现 |
| 会话恢复 | LangGraph `AsyncSqliteSaver` 保存检查点 | ✅ 已实现 |
| 文件工作台 | MySQL 元数据 + S3/MinIO 兼容对象存储 + 本地临时工作区 | ✅ 已实现 |
| Markdown 转 PDF | Python Markdown + WeasyPrint + 受限本地资源访问 | ✅ 已实现 |
| 容器部署 | 非 root 多阶段镜像，Compose 编排前端、后端、MySQL 和对象存储 | ✅ 已实现 |

---

## 🏗️ 系统架构

```text
Vue 前端 / API 调用方
        │
        ├── HTTP：任务、文件、会话、健康检查
        └── WebSocket：工具调用、助手调用、结果、异常
                         │
                    FastAPI API
                         │
          ┌──────────────┼──────────────┐
          │              │              │
      TaskStore      FileService     Agent Runtime
       SQLite       MySQL + S3       DeepAgents
          │              │              │
       运行记录       文件生命周期    LangGraph Checkpointer
       事件记录       临时工作区      SQLite
                                        │
                       ┌────────────────┼────────────────┐
                       │                │                │
                   网络搜索子智能体  数据库子智能体   知识库子智能体
                      Tavily        MySQL（只读）      RAGFlow
```

### 任务执行链路

```text
POST /api/task
  → 校验会话并创建 run_id
  → 恢复对象存储中的会话文件
  → 绑定 ContextVar 会话上下文
  → 主智能体流式执行并记录事件
  → 发布新增或修改的产物到对象存储
  → 更新任务终态并清理临时工作区
```

### 文件生命周期

```text
上传文件
  → 文件名、类型、数量和大小校验
  → MySQL 写入 pending 元数据
  → 本地分块暂存并计算哈希
  → 上传 S3/MinIO，元数据转为 ready

删除会话
  → 拒绝正在执行任务或上传文件的会话
  → 删除该会话的对象存储文件
  → 软删除 MySQL 文件元数据
  → 删除 LangGraph 检查点和任务事件
  → 删除本地 output/updated 工作目录
```

---

## 🚀 快速启动

### 方式一：Docker Compose（推荐）

在项目根目录执行：

```powershell
cd D:\deep-search-pro-master
Copy-Item .\deep-search-pro-master-be\.env.example .\deep-search-pro-master-be\.env
```

至少在 `deep-search-pro-master-be/.env` 中填写以下模型配置：

```env
OPENAI_BASE_URL=https://your-provider.example/v1
OPENAI_API_KEY=replace-me
LLM_MODEL=your-model-id
```

根目录 `.env` 只负责 Compose 对外端口和本地基础设施凭据；需要自定义这些值时再创建：

```powershell
Copy-Item .\.env.example .\.env
```

然后构建并启动完整工作台：

```powershell
docker compose up -d --build
docker compose ps
```

默认地址：

| 服务 | 地址 |
|------|------|
| 前端 | <http://127.0.0.1:5173> |
| 后端 API 文档 | <http://127.0.0.1:8000/docs> |
| 后端健康检查 | <http://127.0.0.1:8000/api/health> |
| MySQL（宿主机） | `127.0.0.1:3307` |
| 对象存储 API | `127.0.0.1:9010` |
| 对象存储控制台 | <http://127.0.0.1:9011> |

查看日志或停止服务：

```powershell
docker compose logs -f backend
docker compose down
```

### 方式二：Windows 本地运行后端

本地运行需要 Python 3.12、可用的 MySQL 和 S3/MinIO 兼容对象存储。若要在 Windows 原生环境生成 PDF，还需要安装 Pango/GLib，并让 WeasyPrint 能找到对应 DLL。

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-be
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

完成环境变量配置后，可以使用启动脚本：

```powershell
.\scripts\start-backend.ps1 -Reload
```

也可以直接启动 Uvicorn：

```powershell
.\venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
```

如 Pango/GLib 安装在 MSYS2 的 UCRT64 目录，可在启动前设置：

```powershell
$env:WEASYPRINT_DLL_DIRECTORIES = 'C:\msys64\ucrt64\bin'
```

Docker 镜像已经包含 WeasyPrint 所需的原生运行库，不需要在容器内额外安装。

---

## ⚙️ 环境变量

后端完整变量模板见[后端 `.env.example`](./.env.example)；根目录 [`.env.example`](../.env.example) 只配置 Compose 对外端口和个人本地基础设施凭据。

### 模型配置

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_BASE_URL` | 是 | OpenAI 兼容接口地址 |
| `OPENAI_API_KEY` | 是 | 模型服务密钥 |
| `LLM_MODEL` | 是 | 当前服务商实际可用的模型 ID |

> 如果接口返回 `401 invalid_model`，通常表示 `LLM_MODEL` 与当前服务商不匹配，或账号没有该模型的访问权限。

### 可选子智能体

| 能力 | 启用条件 |
|------|----------|
| 网络搜索 | 配置 `TAVILY_API_KEY` |
| 数据库查询 | 配置 `MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE` |
| RAGFlow 知识库 | 配置 `RAGFLOW_API_URL`、`RAGFLOW_API_KEY` |

未配置某组变量时，对应子智能体不会注册，其他能力仍可运行。

### 工作台基础设施

| 变量 | 说明 |
|------|------|
| `APP_MYSQL_HOST` / `APP_MYSQL_PORT` | 文件元数据数据库地址 |
| `APP_MYSQL_USER` / `APP_MYSQL_PASSWORD` | 文件元数据库凭据 |
| `APP_MYSQL_DATABASE` | 文件元数据库名 |
| `MINIO_ENDPOINT` | 后端访问对象存储的内部地址 |
| `MINIO_PUBLIC_ENDPOINT` | 返回给浏览器的预签名下载地址 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 对象存储凭据 |
| `MINIO_BUCKET` | 文件桶名称 |
| `MINIO_SECURE` | 是否通过 HTTPS 连接对象存储 |
| `MINIO_DOWNLOAD_EXPIRES_SECONDS` | 预签名下载地址有效期，默认 600 秒 |
| `WORKSPACE_MAX_AGE_HOURS` | 启动时清理陈旧工作区的时间阈值 |
| `CORS_ORIGINS` | 允许访问 API 的前端来源列表 |

`MYSQL_*` 用于数据库查询子智能体，`APP_MYSQL_*` 用于工作台自身的文件元数据，两者职责不同。完整后端启动要求 `APP_MYSQL_*` 和对象存储配置可用；Docker Compose 会自动注入容器内地址。

---

## 🔌 API 与实时事件

### HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查和能力状态 |
| `POST` | `/api/task` | 创建异步 Agent 任务，返回 `202` |
| `GET` | `/api/tasks/{run_id}` | 查询任务状态与已持久化事件 |
| `GET` | `/api/sessions/{thread_id}/active` | 查询会话当前是否繁忙 |
| `DELETE` | `/api/sessions/{thread_id}` | 删除会话关联的文件、状态、检查点和工作区 |
| `POST` | `/api/upload` | 向指定会话上传文件 |
| `GET` | `/api/files?thread_id={uuid}` | 获取会话文件列表 |
| `POST` | `/api/files/{file_uuid}/download-url` | 生成新的预签名下载地址 |

创建任务示例：

```powershell
$body = @{
    query = '你好，请只回复：运行成功'
} | ConvertTo-Json

$task = Invoke-RestMethod `
    -Method Post `
    -Uri 'http://127.0.0.1:8000/api/task' `
    -ContentType 'application/json; charset=utf-8' `
    -Body $body

$task
Invoke-RestMethod "http://127.0.0.1:8000/api/tasks/$($task.run_id)"
```

任务接口立即返回 `thread_id` 和 `run_id`；Agent 在后台执行。同一会话只允许一个活动任务，任务执行与文件上传也会互斥，冲突时返回 `409`。

### WebSocket

连接地址：

```text
ws://127.0.0.1:8000/ws/{thread_id}
```

同一会话支持多个 WebSocket 连接。服务端会推送 `session_created`、`tool_start`、`assistant_call`、`task_result`、`interrupted` 和 `error` 等事件；客户端发送 `ping` 时服务端返回 `pong`。

实时连接断开不会丢失已经写入的运行记录，可通过 `GET /api/tasks/{run_id}` 重新获取任务状态和事件。

### 文件限制

| 项目 | 限制 |
|------|------|
| 单次上传数量 | 最多 5 个文件 |
| 单文件大小 | 最大 20 MiB |
| 支持格式 | `.txt`、`.md`、`.pdf`、`.docx`、`.xlsx` |
| 下载方式 | 短时效预签名 URL |

---

## 📄 Markdown 转 PDF

PDF 链路已经从 Word COM 改为跨平台实现：

```text
Markdown
  → Python Markdown 转 HTML
  → 加载 assets/pdf/default.css
  → WeasyPrint 渲染
  → 校验 PDF 文件头和页面
  → 原子写入最终文件
```

相关文件：

| 文件 | 职责 |
|------|------|
| `tools/pdf_tools.py` | Agent 工具参数、输出文件名和会话路径校验 |
| `utils/word_converter.py` | Markdown、HTML、CSS、资源限制和 PDF 生成 |
| `assets/pdf/default.css` | PDF 默认视觉样式 |

`utils/word_converter.py` 保留了历史文件名，但当前实现不再依赖 Microsoft Word。转换器会转义原始 HTML、禁止网络资源，并将本地图片访问限制在当前会话工作区内。

---

## 💾 持久化与清理

| 数据 | 存储位置 | 用途 |
|------|----------|------|
| 任务与事件 | `data/tasks.sqlite3` | 任务状态、错误和实时事件回放 |
| Agent 检查点 | `data/checkpoints.sqlite3` | LangGraph 会话状态 |
| 文件元数据 | MySQL | 文件状态、对象键、大小、哈希和软删除信息 |
| 文件内容 | S3/MinIO 兼容对象存储 | 上传文件和 Agent 生成文件 |
| 临时文件 | `output/session_{thread_id}` | 单次会话执行工作区 |

服务启动时会把未完成任务标记为 `interrupted`，初始化文件表与对象存储桶，并清理超过 `WORKSPACE_MAX_AGE_HOURS` 的陈旧本地工作区。

删除会话不是只删本地目录：当前实现还会删除对象存储中的关联对象、软删除 MySQL 元数据、清理 LangGraph 检查点以及 SQLite 中的任务和事件记录。

---

## 🛡️ 安全边界

- 会话路径经过规范化和越界校验，Agent 不能写出当前会话工作区。
- PDF 转换禁止网络资源，只允许受控工作区中的本地图片和受限的 Data URI。
- 数据库子智能体只允许单条 `SELECT`，使用 SQL AST 白名单、只读事务、10 秒执行上限和最多 100 行结果。
- 上传流程校验文件名、扩展名、数量和实际流式大小，并使用状态机处理失败回滚。
- API 错误统一转换为安全响应，后台任务异常会被显式消费并记录。
- 服务进程与 Docker 容器均不依赖 Word COM；容器以非 root 用户运行。

当前版本尚未提供身份认证，建议只在受信任的本地网络中运行，不要直接暴露到公网。

---

## 📁 目录结构

```text
deep-search-pro-master-be/
├── agent/                    # 主智能体、模型配置和提示词
│   ├── main_agent.py
│   ├── llm.py
│   └── subagents/            # 网络、数据库、知识库子智能体
├── api/                      # FastAPI、任务、文件和对象存储服务
│   ├── server.py
│   ├── monitor.py
│   ├── task_store.py
│   ├── file_service.py
│   ├── file_repository.py
│   ├── minio_storage.py
│   ├── settings.py
│   └── context.py
├── assets/pdf/default.css    # PDF 样式
├── prompt/prompts.yml        # Agent 提示词
├── scripts/start-backend.ps1 # Windows 启动脚本
├── tests/test_workbench.py   # 工作台核心行为测试
├── tools/                    # 搜索、数据库、RAG、文件和 PDF 工具
├── utils/                    # 路径防护与 PDF 转换
├── Dockerfile
├── requirements.txt
└── README.md
```

### 关键模块索引

| 模块 | 入口 |
|------|------|
| HTTP / WebSocket 路由 | `api/server.py` |
| 后台任务与事件存储 | `api/task_store.py` |
| WebSocket 连接与事件上报 | `api/monitor.py` |
| 文件生命周期编排 | `api/file_service.py` |
| 主智能体构建与流式执行 | `agent/main_agent.py` |
| 数据库只读约束 | `tools/db_tools.py` |
| PDF 工具入口 | `tools/pdf_tools.py` |
| 路径安全 | `utils/path_utils.py` |

---

## 🧪 验证与排障

### 基础验证

```powershell
curl.exe -i http://127.0.0.1:8000/api/health
curl.exe -i http://127.0.0.1:8000/openapi.json
```

返回 `200 OK` 只能说明 HTTP 服务已经启动。要验证完整 Agent 链路，还应创建任务，并通过任务查询接口确认最终状态为 `succeeded`；如果返回 `failed`，查看响应中的错误事件以及后端日志。

### 运行测试

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-be
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Docker 状态检查

```powershell
cd D:\deep-search-pro-master
docker compose config
docker compose ps
docker compose logs --tail 200 backend
```

常见问题：

| 现象 | 原因与处理 |
|------|------------|
| `ModuleNotFoundError: agent` | 不要直接执行 `python api/server.py`；应在后端根目录使用 `python -m uvicorn api.server:app` |
| `curl: (7) Failed to connect` | 核对 Uvicorn 实际监听端口，默认是 `8000`，不是 `8001` |
| `401 invalid_model` | `LLM_MODEL` 不存在或当前账号无权访问，改为服务商实际提供的模型 ID |
| API 正常但任务失败 | HTTP 服务与模型调用是两条链路，继续检查模型凭据、能力配置和任务事件 |
| Windows PDF 生成失败 | 安装 Pango/GLib 并设置 `WEASYPRINT_DLL_DIRECTORIES`，或直接使用 Docker |
| 下载地址无法从浏览器访问 | 检查 `MINIO_PUBLIC_ENDPOINT` 是否为宿主机可访问的地址 |

---

## 🧰 技术栈

| 分类 | 技术 |
|------|------|
| Web 服务 | FastAPI、Uvicorn、WebSocket |
| Agent | DeepAgents、LangChain、LangGraph |
| 状态存储 | SQLite、LangGraph SQLite Checkpointer |
| 文件元数据 | MySQL |
| 对象存储 | MinIO SDK、S3 兼容服务 |
| PDF | Python Markdown、WeasyPrint、Pango/GLib |
| 外部能力 | Tavily、RAGFlow、SQLAlchemy |
| 部署 | Docker、多阶段构建、Docker Compose |

---

## 🗺️ 后续优化方向

| 优化项 | 状态 | 目标 |
|--------|------|------|
| WeasyPrint PDF 链路 | ✅ 已完成 | 摆脱 Word COM，同时支持 Windows 与 Linux |
| 子智能体反思机制 | 📋 计划中 | 子智能体输出后执行结构化自检，提高结果准确性 |
| JWT 认证 | 📋 计划中 | 为 `/api/task` 及文件、会话接口增加身份与权限校验 |
| LangGraph 人工审批节点 | 📋 计划中 | 敏感工具执行前暂停流程，等待用户确认后继续 |
| 子智能体通信 | 📋 计划中 | 让数据库、网络搜索和知识库子智能体交换中间结论 |
| Node + Chromium/Puppeteer PDF | 🔍 评估中 | 支持 Mermaid、数学公式和更完整的复杂 CSS 浏览器排版 |

---

## 📄 License

MIT License
