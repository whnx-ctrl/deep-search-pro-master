# Deep Search Pro Docker 本地部署实施计划

1. 补齐根 Compose、环境变量示例和忽略规则。
2. 构建后端多阶段镜像，安装 WeasyPrint Linux 运行库并使用非 root 用户。
3. 构建前端静态镜像，配置 Nginx API 与 WebSocket 反向代理。
4. 兼容标准 `LLM_MODEL` 变量并同步部署文档。
5. 执行 Python、前端构建、Compose 解析、镜像构建和容器联调。
6. 在容器中完成健康检查、前端代理和中文 PDF 冒烟测试。

范围和验收标准以对应设计文档为准。
