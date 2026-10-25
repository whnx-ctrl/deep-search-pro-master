import { afterAll, beforeAll, afterEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
const server = setupServer(
  http.get('http://localhost:8000/api/health', () => HttpResponse.json({
    status:'ok', instance_id:'instance', capabilities:{ search:true, database:false, knowledge:false },
  })),
)
beforeAll(() => { vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000'); server.listen({ onUnhandledRequest:'error' }) })
afterEach(() => server.resetHandlers())
afterAll(() => { server.close(); vi.unstubAllEnvs() })
it('validates successful backend responses', async () => {
  const { api } = await import('./workbench')
  expect((await api.health()).capabilities.search).toBe(true)
})
it('surfaces localized backend errors', async () => {
  server.use(http.get('http://localhost:8000/api/health', () =>
    HttpResponse.json({ error:{ code:'unavailable', message:'服务暂不可用' } }, { status:503 })))
  const { api } = await import('./workbench')
  await expect(api.health()).rejects.toThrow('服务暂不可用')
})
it('accepts an empty 204 response when deleting a session', async () => {
  server.use(http.delete('http://localhost:8000/api/sessions/:uuid', () =>
    new HttpResponse(null, { status:204 })))
  const { api } = await import('./workbench')
  await expect(api.deleteSession('8e476c68-4c2d-4c8a-a097-4ae87ce67810')).resolves.toBeNull()
})
it('requests a fresh presigned URL for a file download', async () => {
  server.use(http.post('http://localhost:8000/api/files/:uuid/download-url', () =>
    HttpResponse.json({
      downloadUrl:'http://127.0.0.1:9000/deep-search-files/report?signature=test',
      expiresIn:600,
      filename:'report.md',
    })))
  const { api } = await import('./workbench')
  const result = await api.downloadUrl('8e476c68-4c2d-4c8a-a097-4ae87ce67810')
  expect(result.filename).toBe('report.md')
  expect(result.expiresIn).toBe(600)
})
