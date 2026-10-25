# 本地工作台实施计划

用户已批准以书面计划替代 writing-plans，并批准完整设计。

1. 后端：集中配置、会话文件边界、SQLite 任务记录、后台任务生命周期、多连接 WebSocket。
2. Agent：按配置注册助手、任务准备异常处理、单次最终结果、SQL 校验、RAG 清理及提示词修正。
3. 前端：Vue/Vite 工程、类型化 API、IndexedDB 会话、WebSocket 恢复、三栏界面与安全 Markdown。
4. 验证：后端 unittest、前端类型检查/lint/Vitest、Playwright 成功与失败路径、构建与视觉检查。
5. 交付：两工程启动说明、配置模板和审查记录。自动测试不调用收费服务。

当前目录没有 Git 元数据，不创建 Git 提交。
