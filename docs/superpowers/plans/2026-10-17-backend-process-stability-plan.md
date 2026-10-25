# 后端进程稳定性实施计划

1. 修改 `api/server.py`：启用 faulthandler，记录启动/关闭信息，在 health 返回 PID、启动时间和运行时长。
2. 修改 `api/server.py`：为后台任务增加安全的完成回调，确保遗漏异常被读取和记录。
3. 修改 `api/server.py`：直接执行时默认关闭 reload，仅通过 `BACKEND_RELOAD` 显式开启。
4. 新增 `scripts/start-backend.ps1`：定位虚拟环境、创建日志目录、支持可选 Reload、保存退出码。
5. 修改后端 README 和 `.env.example`：统一推荐启动方式并说明 `BACKEND_RELOAD`。
6. 扩充 `tests/test_workbench.py`：验证 health 诊断字段、后台失败隔离和启动默认值。
7. 运行全部后端 unittest，并进行真实 Uvicorn 启动、health 和正常关闭冒烟测试。

不修改前端、API 路径、CORS、模型参数和 SQLite 表结构。
