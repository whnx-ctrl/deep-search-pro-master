# 后端进程稳定性修复设计

日期：2026-10-17

## 背景

本地前端偶发收到 `ECONNREFUSED 127.0.0.1:8000`。现有日志只记录了 Uvicorn 正常启动，没有 Python traceback，也没有正常关闭日志，说明现有观测不足以区分热重载、外部终止和进程级故障。当前 `python api/server.py` 会强制启用 `reload=True`；使用 `python -m uvicorn ... --reload` 时也会运行父子双进程。个人本地工作台不需要默认依赖该模式。

## 目标

- 默认使用稳定的单进程 Uvicorn 启动方式。
- 普通 Agent、模型、数据库和 WebSocket 异常不得导致 API 主进程退出。
- 服务发生启动、正常关闭或未处理后台异常时留下可诊断日志。
- 健康接口能够显示当前进程身份和运行时长，以识别服务重启。
- 提供不依赖当前 PowerShell 目录的标准启动脚本。

## 非目标

- 不引入 Windows Service、NSSM 或第三方进程守护器。
- 不自动重启被操作系统强制结束的进程。
- 不修改现有 API 路径、前端代理、CORS、模型配置或 SQLite 数据结构。
- 不把普通任务失败提升为进程退出。

## 设计

### 启动入口

`api/server.py` 的直接运行入口默认关闭 reload。仅当 `BACKEND_RELOAD` 明确设置为真值时启用热重载。模块启动 `python -m uvicorn api.server:app` 继续受 Uvicorn 命令行参数控制。

### 生命周期与诊断

FastAPI lifespan 在启动时保存进程 PID、UTC 启动时间和单调时钟起点，并记录 Python 版本、工作目录和进程信息。关闭时记录正常 shutdown。启用 Python `faulthandler`，使可捕获的解释器级故障尽量输出到标准错误；启动脚本统一将标准输出和错误写入日志。

`GET /api/health` 在现有字段之外返回：

- `pid`
- `started_at`
- `uptime_seconds`

这些字段只用于诊断，不改变已有字段语义。

### 后台任务隔离

用命名函数替换当前只做集合清理的 task done callback。回调始终从活动集合移除任务；对于非取消任务读取 `task.exception()` 并记录任何遗漏异常。Agent 执行函数继续把业务异常转换成任务失败事件，不将异常传播到 Uvicorn 请求循环。

### PowerShell 启动脚本

新增 `scripts/start-backend.ps1`：

- 根据脚本自身位置定位后端根目录。
- 验证 `venv/Scripts/python.exe` 存在。
- 创建 `logs` 目录。
- 默认执行无 reload 的 Uvicorn。
- 支持显式 `-Reload` 参数用于开发热重载。
- 将控制台输出同步保存到 `logs/backend.log`。
- 保留 Uvicorn/Python 的真实退出码。

### 错误处理边界

- 模型、搜索、数据库、RAGFlow 和文件工具异常：任务失败，服务继续运行。
- WebSocket 单连接异常：清理该连接，服务继续运行。
- 后台任务未处理异常：写入日志，服务继续运行。
- Ctrl+C、终端关闭、系统强制终止：不伪装为业务错误；能执行 lifespan 时记录正常关闭，无法执行时依靠最后日志判断为外部或进程级终止。

## 测试与验收

- 单元测试验证健康接口包含稳定的 PID、启动时间和非负运行时长。
- 单元测试让后台任务抛出异常，并验证任务进入失败状态且健康接口仍返回 200。
- 静态验证直接运行入口默认不启用 reload。
- 执行现有全部后端测试，确保上传、下载、WebSocket、任务持久化和 SQL 安全逻辑没有回归。
- 手工使用启动脚本运行，确认日志包含启动记录，并能通过 Ctrl+C 正常关闭。

## 已知边界

单进程和异常隔离可以修复项目内可控的退出风险，但无法阻止用户关闭终端、PyCharm 停止进程、Windows 强制结束 Python 或硬件/原生扩展崩溃。若修复后日志仍无 shutdown 和 traceback 就突然中断，后续应采用独立进程守护方案，而不是继续修改业务异常处理。
