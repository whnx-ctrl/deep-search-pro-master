import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
export default defineConfig({
  testDir: './tests/e2e', fullyParallel: false, workers: 1,
  use: { baseURL: 'http://127.0.0.1:5179', channel: process.platform === 'win32' ? 'msedge' : undefined,
    viewport: { width:1440, height:960 }, trace:'retain-on-failure' },
  webServer: [
    { command: '"' + resolve('../deep-search-pro-master-be/venv/Scripts/python.exe') + '" -m uvicorn tests.fixture_server:app --app-dir ../deep-search-pro-master-be --host 127.0.0.1 --port 8019',
      url: 'http://127.0.0.1:8019/api/health', env: { CORS_ORIGINS:'http://127.0.0.1:5179' }, reuseExistingServer:false },
    { command: 'pnpm dev --port 5179', env: { API_PROXY_TARGET: 'http://127.0.0.1:8019' },
      url: 'http://127.0.0.1:5179', reuseExistingServer:false },
  ],
})
