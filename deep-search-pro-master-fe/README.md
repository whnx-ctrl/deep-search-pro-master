# Deep Search Pro Frontend

Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS 4。独立于 FastAPI 运行的个人本地研究工作台。

## 开发

```powershell
cd D:\deep-search-pro-master\deep-search-pro-master-fe
pnpm.cmd install
pnpm.cmd dev
```

默认地址 http://127.0.0.1:5173 ，`/api` 和 `/ws` 自动代理到 http://127.0.0.1:8000 。端口占用时不会静默切换端口。

可复制 `.env.example` 为 `.env` 并修改 `API_PROXY_TARGET`，不要把任何服务 Key 放入前端。

## 构建和预览

```powershell
pnpm.cmd build
pnpm.cmd preview
```

预览地址 http://127.0.0.1:4173 ，同样配置后端代理。若将 dist 交给其他静态服务器，需自行转发 `/api` 和 `/ws`；也可在构建前设置 `VITE_API_BASE_URL` 指向后端并配置后端本地 CORS 来源。Vue Router 使用 history 模式，需要静态服务器提供 SPA fallback。

## 检查

```powershell
pnpm.cmd typecheck
pnpm.cmd lint
pnpm.cmd test
pnpm.cmd test:e2e
```

E2E 使用隔离的受控 Python 服务，不调用真实模型，不访问原始文件。Windows 默认使用 Edge；Linux/macOS 先安装 Playwright Chromium。8019 与 5179 端口需空闲。

## 模块

- `src/stores/useWorkbenchStore.ts`：会话、任务、文件与 IndexedDB 保存。
- `src/composables/useTaskSocket.ts`：ready 握手、心跳、重连、事件校验。
- `src/api/workbench.ts`：类型化 HTTP 接口与 Zod 边界校验。
- `src/lib/markdown.ts`：Markdown token 转 Vue 节点，禁用原始 HTML 和危险链接。
- `src/components`：会话列表、对话、输入、进度与文件组件。

浏览器保留会话历史和稳定的 `thread_id`；后端重启后会从 SQLite checkpoint 恢复模型上下文，旧会话可以继续。下载链接按会话和相对 storagePath 动态生成，不保存绝对磁盘路径。
