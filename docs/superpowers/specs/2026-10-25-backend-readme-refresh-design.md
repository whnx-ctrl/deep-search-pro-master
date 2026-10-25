# Deep Search Pro 后端 README 更新设计

日期：2026-10-25

## 目标

更新 `deep-search-pro-master-be/README.md`，使其准确描述当前后端，而不再停留在第一版学习 Demo。README 继续作为后端独立说明书，并简要链接父目录的前端与 Docker Compose 文档。

## 写作与样式

- 保留现有居中标题、徽章、emoji、分隔线、Markdown 表格、代码块和 ASCII 架构图。
- 删除“适合学习练手”“你能学到什么”“练手建议”等教学和简历导向内容。
- 使用专业、直接、可核验的工程文档语气。
- 只描述当前代码已经实现的能力；未来功能统一放入路线图并标记为计划项。
- 避免与父目录 README 重复整套前端和 Compose 说明，只保留入口、必要命令和链接。

## 内容结构

1. 项目标题、徽章和一句话定位。
2. 核心能力。
3. 系统架构与任务执行流程。
4. 快速启动：Docker Compose 与 Windows 本机启动。
5. 环境变量配置表。
6. HTTP API 与 WebSocket 接口表。
7. 文件与会话生命周期。
8. 数据持久化说明。
9. 项目目录结构。
10. PDF 跨平台支持与安全边界。
11. 测试、健康检查与排错入口。
12. 技术栈。
13. 后续优化方向。
14. 常见问题。
15. License。

## 必须纠正的旧内容

- 删除“不足 1000 行代码”“只有 6 个核心模块”等已失效描述。
- Python 运行基线以 Dockerfile 的 Python 3.12 和当前代码要求为准。
- 模型变量使用 `LLM_MODEL`，并说明代码仅为旧本地配置兼容 `LLM_QWEN3.5`。
- Tavily、RAGFlow 和 Agent 数据库查询能力均为按环境变量注册的可选能力。
- 更新工具数量、目录树、模块职责和推荐排查入口。
- 删除仍将前端、SQLite checkpointer、WeasyPrint 和 Docker 化列为“未完成”的内容。

## 当前能力说明

README 需要覆盖以下实际能力：

- DeepAgents 主智能体与网络搜索、数据库查询、RAGFlow 知识库三个可选子智能体。
- 后台任务、同会话互斥、任务状态查询、最多 250 条事件快照和服务重启后的中断标记。
- WebSocket 实时事件、多连接支持、心跳与断线后通过 HTTP 恢复任务快照。
- LangGraph `AsyncSqliteSaver` 会话上下文持久化。
- 上传、列表、预签名下载、Agent 读取、生成文件发布与完整会话删除。
- MySQL 保存文件元数据，MinIO/S3 兼容存储保存文件内容；会话删除同步处理对象、元数据、任务、事件、checkpoint 和本地目录。
- 上传限制：每批最多 5 个、单文件最多 20 MiB，支持 `.txt`、`.md`、`.pdf`、`.docx`、`.xlsx`。
- Markdown + HTML + CSS + WeasyPrint PDF 生成，包含工作区路径、外部网络资源和图片类型/大小限制。
- Docker 中的 Pango、GLib、Harfbuzz 与 Noto CJK 中文字体支持。

## 启动与配置

- Docker Compose 作为完整本地工作台的推荐启动方式；后端 README 指向父目录 `README.md` 和 `compose.yaml`。
- 保留 Windows 本机虚拟环境与 `scripts/start-backend.ps1` 启动方式。
- 环境变量按 LLM、可选 Agent 能力、CORS、工作台 MySQL、对象存储、工作区清理分组展示。
- 明确真实 `.env` 不提交 Git，Compose 会覆盖容器内部 MySQL 和对象存储地址。

## 接口说明

接口表以 `api/server.py` 当前路由为准：

- `GET /api/health`
- `POST /api/task`
- `GET /api/tasks/{run_id}`
- `GET /api/sessions/{thread_id}/active`
- `DELETE /api/sessions/{thread_id}`
- `POST /api/upload`
- `GET /api/files`
- `POST /api/files/{file_uuid}/download-url`
- `WS /ws/{thread_id}`

说明常见的 `202`、`204`、`409`、`413` 和 `422` 语义，但不复制自动生成的完整 OpenAPI 文档。

## 路线图

路线图使用状态表，不再使用教学难度分级：

- 已完成：WeasyPrint 跨平台 PDF，替代 Word COM。
- 计划：子智能体结果反思和必要重试。
- 计划：JWT 认证与任务、文件、会话接口权限控制。
- 计划：LangGraph 人工审批节点。
- 计划：子智能体之间共享中间结论和协作通信。
- 评估：将 PDF 引擎迁移至 Node.js + Chromium/Puppeteer，以支持 Mermaid、公式和复杂 CSS；同时评估镜像体积、内存、启动时间及资源访问安全边界。

## 验收标准

- README 中的路径、路由、变量、端口、文件限制和启动命令均能在当前仓库找到对应实现。
- 不再出现 `LLM_QWEN_MAX`、InMemorySaver、待增加前端、待 Docker 化等失效描述。
- 当前能力与路线图清晰分离，不把计划项写成已实现。
- Docker 与本机启动说明不互相矛盾。
- Markdown 层级、表格和代码块渲染正常，无 `TODO`、`TBD` 或占位章节。
