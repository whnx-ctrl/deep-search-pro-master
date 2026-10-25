<p align="center">
  <h1 align="center">🔎 Deep Search Pro</h1>
  <p align="center"><b>面向个人本地使用的多智能体研究工作台</b></p>
  <p align="center">
    <img src="https://img.shields.io/badge/Vue-3.5-42b883.svg" alt="Vue">
    <img src="https://img.shields.io/badge/FastAPI-0.129.2-009688.svg" alt="FastAPI">
    <img src="https://img.shields.io/badge/LangGraph-1.0.9-orange.svg" alt="LangGraph">
    <img src="https://img.shields.io/badge/WeasyPrint-68.1-blueviolet.svg" alt="WeasyPrint">
    <img src="https://img.shields.io/badge/Docker_Compose-ready-2496ED.svg" alt="Docker Compose">
  </p>
</p>

---

## 🎯 项目简介

Deep Search Pro 是一个前后端分离的本地研究工作台。用户可以在浏览器中创建会话、上传资料并提交研究任务，由主智能体按当前配置调度网络搜索、数据库查询和知识库检索子智能体，实时展示执行过程并管理生成文件。

项目由两个独立工程组成：

| 工程 | 职责 | 技术栈 |
|------|------|--------|
| [`deep-search-pro-master-fe`](./deep-search-pro-master-fe/) | 会话、文件、任务事件和 Markdown 结果界面 | Vue 3、Vite、Pinia、Tailwind CSS 4 |
| [`deep-search-pro-master-be`](./deep-search-pro-master-be/) | Agent 编排、API、任务状态、文件存储和 PDF 生成 | FastAPI、DeepAgents、LangGraph、MySQL、S3/MinIO、WeasyPrint |

当前版本定位为个人本机工作台，默认只绑定 `127.0.0.1`，尚未提供登录和多用户权限体系。

---

## ✨ 核心能力

| 能力 | 说明 |
|------|------|
| 多智能体协作 | 主智能体根据环境配置动态挂载网络搜索、数据库和 RAGFlow 子智能体 |
| 实时执行过程 | 通过 WebSocket 展示工具调用、助手调用、结果和错误事件 |
| 会话任务恢复 | SQLite 保存任务事件，LangGraph Checkpointer 保存 Agent 会话状态 |
| 文件工作台 | 上传、列举、下载和删除会话文件，生成文件自动发布到对象存储 |
| Markdown 与 PDF | 前端渲染 Markdown，后端使用 WeasyPrint 生成跨平台 PDF |
| 本地持久化 | MySQL 保存文件元数据，对象存储保存文件，Docker Volume 保存服务数据 |
| 一键容器化 | Compose 统一拉起前端、后端、MySQL 和 S3/MinIO 兼容对象存储 |

---

## 🏗️ 整体架构

```text
浏览器
  │
  ▼
Vue 3 前端（5173）
  ├── HTTP：任务、文件、会话管理
  └── WebSocket：实时执行事件
             │
             ▼
FastAPI 后端（8000）
  ├── 主智能体 ── 网络搜索 / 数据库 / RAGFlow 子智能体
  ├── SQLite ──── 任务事件 / LangGraph 检查点
  ├── MySQL ───── 文件元数据
  ├── S3/MinIO ── 上传文件 / Agent 生成文件
  └── WeasyPrint  Markdown → PDF
```

Docker Compose 服务默认端口：

| 服务 | 地址 |
|------|------|
| 工作台 | <http://127.0.0.1:5173> |
| 后端 API 文档 | <http://127.0.0.1:8000/docs> |
| 后端健康检查 | <http://127.0.0.1:8000/api/health> |
| MySQL | `127.0.0.1:3307` |
| 对象存储 API | `127.0.0.1:9010` |
| 对象存储控制台 | <http://127.0.0.1:9011> |

---

## 🚀 Docker 一键启动

### 1. 配置模型

在项目根目录执行：

```powershell
Copy-Item .\deep-search-pro-master-be\.env.example .\deep-search-pro-master-be\.env
```

编辑 `deep-search-pro-master-be/.env`，至少填写：

```env
OPENAI_BASE_URL=https://your-provider.example/v1
OPENAI_API_KEY=replace-me
LLM_MODEL=your-model-id
```

Tavily、数据库查询和 RAGFlow 子智能体均按环境变量动态启用。未配置的可选能力不会注册，也不会阻止基础 Agent 启动。

如需修改宿主机端口或本地基础设施凭据，再创建根环境文件：

```powershell
Copy-Item .\.env.example .\.env
```

### 2. 启动服务

启动 Docker Desktop，然后执行：

```powershell
cd D:\deep-search-pro-master
docker compose config
docker compose up -d --build
docker compose ps
```

服务健康后访问 <http://127.0.0.1:5173>。可用以下命令确认前后端代理链路：

```powershell
curl.exe http://127.0.0.1:8000/api/health
curl.exe http://127.0.0.1:5173/api/health
```

### 3. 日志与停止

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

`docker compose down` 会保留 MySQL、对象存储、任务状态和 Agent 文件。以下命令会永久删除 Compose 数据卷，只应在确定需要清空全部本地数据时使用：

```powershell
docker compose down -v
```

---

## 💻 Windows 本机启动

后端和前端分别运行在两个 PowerShell 窗口中。

### 后端

首次准备依赖和配置：

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-be
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

配置 `.env` 后启动：

```powershell
.\scripts\start-backend.ps1 -Reload
```

Windows 原生生成 PDF 需要 Pango/GLib。若安装在 MSYS2 UCRT64 默认目录，启动前设置：

```powershell
$env:WEASYPRINT_DLL_DIRECTORIES = 'C:\msys64\ucrt64\bin'
```

### 前端

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-fe
pnpm.cmd install
pnpm.cmd dev
```

浏览器访问 <http://127.0.0.1:5173>。后端的完整环境变量、API 和排障说明见[后端 README](./deep-search-pro-master-be/README.md)，前端脚本和模块说明见[前端 README](./deep-search-pro-master-fe/README.md)。

---

## 📖 使用流程

```text
新建会话
  → 上传参考文件（可选）
  → 输入研究问题
  → 查看实时 Agent 调用事件
  → 阅读 Markdown 结果
  → 下载生成文件
```

- 支持 `.txt`、`.md`、`.pdf`、`.docx`、`.xlsx`。
- 单文件最大 20 MiB，每批最多上传 5 个文件。
- 同一会话只允许一个活动任务，执行任务与上传文件互斥。
- 浏览器 IndexedDB 保存前端会话索引；后端负责持久化任务、检查点和文件。
- 删除会话时会同步清理对象存储文件、MySQL 文件元数据、SQLite 任务事件、LangGraph 检查点和本地工作区。

---

## 📁 项目目录

```text
deep-search-pro-master/
├── deep-search-pro-master-be/   # FastAPI + 多智能体后端
├── deep-search-pro-master-fe/   # Vue 3 单页前端
├── docs/                        # 设计与部署文档
├── compose.yaml                 # 完整工作台容器编排
├── .env.example                 # Compose 端口与本地凭据模板
├── .gitignore
└── README.md
```

### GitHub 上传前检查

```powershell
git status --short
git check-ignore .env deep-search-pro-master-be/.env
git grep -n "OPENAI_API_KEY="
```

确认没有真实密钥、虚拟环境、`node_modules`、数据库、对象存储数据或构建产物后再提交。Docker 部署设计见 [`docs/superpowers/specs/2026-10-24-docker-local-deployment-design.md`](./docs/superpowers/specs/2026-10-24-docker-local-deployment-design.md)。

---

## 🗺️ 后续优化方向

| 优化项 | 状态 |
|--------|------|
| WeasyPrint 跨平台 PDF 链路 | ✅ 已完成 |
| 子智能体执行后的结构化反思 | 📋 计划中 |
| JWT 登录与接口权限校验 | 📋 计划中 |
| LangGraph 敏感操作人工审批节点 | 📋 计划中 |
| 数据库、搜索与知识库子智能体通信 | 📋 计划中 |
| Node + Chromium/Puppeteer 高级 PDF 排版 | 🔍 评估中 |

---

## 📄 License

MIT License
