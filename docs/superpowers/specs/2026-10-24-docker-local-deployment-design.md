# Deep Search Pro 个人本地 Docker 部署设计

日期：2026-10-24

## 目标

为 `deep-search-pro-master` 补齐可公开提交到 GitHub 的个人本地 Docker 部署配置。使用一条 `docker compose up -d` 命令启动前端、后端、MySQL 和 MinIO 兼容对象存储；模型 API、Tavily 与 RAGFlow 保持为外部服务。

## 范围

本次新增或调整以下内容：

- 根目录 Compose 编排及 Compose 环境变量示例。
- 后端 Linux 多阶段镜像，包含 WeasyPrint 所需 Pango、GLib、Harfbuzz 和中文字体。
- 前端 Vue 构建镜像及 Nginx 静态文件、HTTP API、WebSocket 代理配置。
- MySQL、MinIO 兼容对象存储数据卷、健康检查和服务启动依赖。
- 后端模型环境变量兼容与环境变量示例同步。
- Docker 使用说明、忽略规则和本地验证命令。

不包含：

- 将 RAGFlow 加入本 Compose。
- 云平台、Kubernetes、HTTPS、域名和多节点部署。
- 自动创建或推送 GitHub 仓库。
- 改造现有 Agent、数据库或文件业务逻辑。

## 架构

```text
浏览器 http://127.0.0.1:5173
  |
  v
frontend (Nginx + Vue 静态文件)
  |-- /api/* --> backend:8000
  `-- /ws/*  --> backend:8000
                    |-- mysql:3306
                    |-- minio:9000
                    `-- 外部模型 API / Tavily / RAGFlow
```

对宿主机开放：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| 前端 | `127.0.0.1:5173` | 主要访问入口 |
| 后端 | `127.0.0.1:8000` | Swagger、调试和健康检查 |
| MySQL | `127.0.0.1:3307` | 本地数据库调试 |
| MinIO API | `127.0.0.1:9010` | 浏览器下载和对象 API |
| MinIO Console | `127.0.0.1:9011` | 本地对象管理 |

所有端口只绑定回环地址，不向局域网公开。

## 服务设计

### 后端

后端使用 `python:3.12-slim-bookworm` 多阶段镜像。构建阶段安装编译依赖并生成 Python wheels；运行阶段只安装运行库、Pango、Harfbuzz、Fontconfig、中文字体和 wheels。容器使用非 root 用户运行 Uvicorn：

```text
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```

镜像构建阶段或容器验收阶段执行 `python -m weasyprint --info`，确认 WeasyPrint 可以加载 Linux 原生库。`output/`、`updated/` 等会话目录保留在后端命名卷中。

### 前端

前端构建阶段使用 Node 与 `pnpm-lock.yaml` 执行冻结依赖安装和生产构建。运行阶段使用 Nginx 提供 `dist/`：

- SPA 路由回退到 `index.html`。
- `/api/` 反向代理到 `backend:8000`。
- `/ws/` 反向代理到 `backend:8000`，保留 WebSocket Upgrade 头。
- 健康检查访问 Nginx 根页面。

生产前端继续使用相对 `/api` 和 `/ws` 地址，不在浏览器构建产物中写死后端容器地址。

### MySQL

MySQL 使用官方 8.4 镜像和命名卷。Compose 为个人本地环境提供可覆盖的默认用户、密码和数据库名称。后端容器强制使用 Compose 服务名 `mysql`，不使用 `localhost`。

工作台元数据连接使用 `APP_MYSQL_*`。Agent 的可选数据库工具使用 `MYSQL_*`；默认指向同一个本地数据库，用户可以通过未提交的根 `.env` 覆盖。

### 对象存储

对象存储使用 PGSTY SILO 固定版本镜像和命名卷，同时开放 API 与 Console。SILO 是社区维护的 MinIO 分支，保留 S3 API、`MINIO_*` 环境变量和数据接口。Compose 仍使用服务名 `minio`，因此后端内部地址保持 `minio:9000`，下发给浏览器的预签名地址使用 `127.0.0.1:9010`。后端现有启动逻辑负责确认 bucket；Compose 使用 SILO 内置探针阻止后端在对象存储未就绪时启动。

## 配置与密钥

- 根 `.env` 与后端真实 `.env` 均保持忽略，不进入 Git 或镜像。
- `.env.example` 只包含占位值和个人本地默认值。
- Compose 使用后端 `.env` 读取模型、Tavily 和 RAGFlow 密钥，再用 `environment` 覆盖容器内部的 MySQL、MinIO 地址。
- 标准模型变量统一为 `LLM_MODEL`；代码保留对旧 `LLM_QWEN3.5` 的兼容，避免现有本机配置立即失效。
- `WEASYPRINT_DLL_DIRECTORIES` 只用于 Windows，不传入 Linux 容器。

## 持久化与删除

命名卷：

- `mysql-data`：MySQL 数据。
- `minio-data`：MinIO 对象。
- `backend-output`：Agent 会话产物。
- `backend-updated`：后端更新或中间产物。
- `backend-data`：任务状态与 LangGraph checkpoint SQLite 数据。

普通 `docker compose down` 保留数据；只有用户明确执行 `docker compose down -v` 才删除全部命名卷。

## 健康检查与启动顺序

1. MySQL 和对象存储启动并通过各自健康检查。
2. 后端启动，初始化工作台数据库表、对象存储 bucket 和后台清理任务。
3. 前端 Nginx 启动并代理 API/WebSocket。

后端健康检查使用 `GET /api/health`。Compose 中 `depends_on.condition: service_healthy` 只解决启动顺序；运行期间的外部模型或 RAGFlow 错误继续由现有任务状态和 WebSocket 事件返回。

## 安全边界

- `.dockerignore` 排除 `.env`、虚拟环境、Node modules、构建产物、运行目录、IDE 文件和测试缓存。
- 不把真实密钥写入 Dockerfile、Compose 默认值或前端 `VITE_*` 变量。
- 后端镜像以非 root 用户运行。
- MySQL、对象存储和后端调试端口只绑定 `127.0.0.1`。
- PDF 转换继续使用现有受限资源抓取器，不开放网络或任意本地文件访问。

## 验收

静态验证：

```powershell
docker compose config
docker compose build
```

运行验证：

```powershell
docker compose up -d
docker compose ps
curl.exe http://127.0.0.1:8000/api/health
curl.exe http://127.0.0.1:5173/api/health
```

功能验证：

- 从前端提交最小 Agent 任务并收到 WebSocket 事件。
- 上传文件后在对象存储创建对象并在 MySQL 写入元数据。
- 在后端容器中将包含中文、粗体和表格的 Markdown 转成 PDF。
- 重启 Compose 后 MySQL、对象存储和 Agent 文件仍存在。

## 交付文件

```text
deep-search-pro-master/
|-- compose.yaml
|-- .env.example
|-- README.md
|-- deep-search-pro-master-be/
|   |-- Dockerfile
|   |-- .dockerignore
|   |-- .env.example
|   `-- agent/llm.py
`-- deep-search-pro-master-fe/
    |-- Dockerfile
    |-- nginx.conf
    `-- .dockerignore
```
