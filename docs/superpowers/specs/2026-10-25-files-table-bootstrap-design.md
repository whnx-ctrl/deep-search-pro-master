# Files 表启动初始化修复设计

## 背景

后端容器能够通过健康检查，但首次使用 `/api/files` 时返回 500。原因是 `FileRepository.open()` 只执行 `SELECT 1` 检查 MySQL 连接，没有创建业务依赖的 `files` 表。

## 方案

在 `FileRepository.open()` 中使用同一异步 SQLAlchemy 引擎完成两步启动初始化：

1. 建立数据库连接并验证连接可用。
2. 在事务中执行 `CREATE TABLE IF NOT EXISTS files`，结构与现有文件存储架构设计一致。

建表操作必须幂等，已有表和数据不受影响。数据库连接或建表失败时，异常继续向上传播，由 FastAPI lifespan 阻止服务进入可用状态，避免健康检查正常但业务接口不可用。

## 改动范围

- 修改 `deep-search-pro-master-be/api/file_repository.py`。
- 增加仓储初始化测试，覆盖首次建表和重复初始化。
- 不修改 HTTP API、文件生命周期、MinIO、Compose 端口或现有数据。

## 验证

1. 运行新增测试。
2. 重建并启动后端容器。
3. 确认后端健康。
4. 请求空会话的 `/api/files`，应返回 HTTP 200 和空文件数组。
5. 确认前端仍可通过 `127.0.0.1:5173` 访问。
