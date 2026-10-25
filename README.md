# Deep Search Pro 本地研究工作台

项目由两个独立工程组成：

- `deep-search-pro-master-be`：FastAPI、DeepAgents、MySQL、MinIO 兼容对象存储和 WeasyPrint。
- `deep-search-pro-master-fe`：Vue 3、Vite、Pinia 和 Tailwind CSS。

项目仅面向个人本机使用，支持直接在 Windows 启动，也支持 Docker Compose 一键启动。

## Docker 一键启动

### 1. 准备配置

后端真实密钥只保存在未提交的 `.env` 中：

```powershell
Copy-Item .\deep-search-pro-master-be\.env.example .\deep-search-pro-master-be\.env
```

编辑 `deep-search-pro-master-be/.env`，至少填写：

```dotenv
OPENAI_BASE_URL=https://your-provider.example/v1
OPENAI_API_KEY=replace-me
LLM_MODEL=your-model-id
```

Tavily 和 RAGFlow 没有配置时只会禁用对应工具。Compose 会覆盖 MySQL 和 MinIO 的容器内部地址，因此不要把容器服务名写回本机开发配置。

如果要修改本地端口或个人本地数据库密码，再创建根环境文件：

```powershell
Copy-Item .\.env.example .\.env
```

默认配置已经可以用于只绑定 `127.0.0.1` 的个人本地环境。真实 `.env` 均已被 Git 和 Docker 构建上下文忽略。

### 2. 启动

先启动 Docker Desktop，然后在项目根目录执行：

```powershell
docker compose config
docker compose up --build -d
docker compose ps
```

访问地址：

| 服务 | 地址 |
| --- | --- |
| 工作台 | http://127.0.0.1:5173 |
| 后端 Swagger | http://127.0.0.1:8000/docs |
| 后端健康检查 | http://127.0.0.1:8000/api/health |
| 对象存储 Console | http://127.0.0.1:9011 |

验证 Nginx 到后端的代理：

```powershell
curl.exe http://127.0.0.1:8000/api/health
curl.exe http://127.0.0.1:5173/api/health
```

### 3. 日志和停止

```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

`docker compose down` 会保留 MySQL、对象存储、任务状态和 Agent 文件。以下命令会永久删除全部 Compose 数据卷，只在确实要清空本地数据时使用：

```powershell
docker compose down -v
```

## Windows 本机启动

第一个 PowerShell：

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-be
.\scripts\start-backend.ps1
```

第二个 PowerShell：

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-fe
pnpm.cmd install
pnpm.cmd dev
```

浏览器访问 http://127.0.0.1:5173 。如果原有后端进程已经在 8000 运行，先用 `Ctrl+C` 停止并重新启动，确保加载最新接口。

首次准备后端依赖：

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-be
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows 本机生成 PDF 需要 Pango/GLib，并设置：

```text
WEASYPRINT_DLL_DIRECTORIES=C:\msys64\ucrt64\bin
```

Docker 镜像已经内置 Pango、GLib、Harfbuzz 和 Noto CJK 中文字体，不依赖 Windows 环境变量或 Microsoft Word。

## 使用

新建会话 → 添加文件 → 输入问题 → 查看真实调用事件 → 阅读 Markdown 回答 → 下载生成文件。示例卡片只负责填入问题，不会自动调用模型。

支持 txt、md、pdf、docx、xlsx，单文件不超过 20 MiB，每批最多 5 个。同会话执行期间禁止再次提交；失败后可主动重试。

会话历史保存在浏览器 IndexedDB。任务状态与 LangGraph checkpoint 保存在后端 `data/`，会话文件保存在 `output/session_UUID`，永久文件保存在兼容 MinIO API 的对象存储中。

## 验证

后端：

```powershell
cd .\deep-search-pro-master-be
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

前端：

```powershell
cd .\deep-search-pro-master-fe
pnpm.cmd build
pnpm.cmd lint
pnpm.cmd test
```

Docker：

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

浏览器端到端测试会独立启动测试服务、使用受控模型桩，不调用真实模型。

## GitHub 上传前检查

```powershell
git status --short
git check-ignore .env deep-search-pro-master-be/.env
git grep -n "OPENAI_API_KEY="
```

确认没有真实 Key、数据库文件、MinIO 数据、虚拟环境、`node_modules` 或构建产物后再提交和推送。

Docker 部署设计见 `docs/superpowers/specs/2026-10-24-docker-local-deployment-design.md`。
