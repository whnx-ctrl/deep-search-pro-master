import { z } from 'zod'
import { request } from '../lib/httpClient'
import { HealthSchema, TaskSchema, FileSchema } from '../types/workbench'
const UploadSchema = z.object({ files: z.array(z.object({
  name: z.string(), status: z.enum(['uploaded','failed']), error: z.string().optional(), size: z.number().optional(),
})) })
export const api = {
  health: async () => HealthSchema.parse(await request('/api/health')),
  task: async (query: string, threadId: string) => z.object({ run_id: z.string() }).parse(
    await request('/api/task', { method: 'POST', headers: { 'Content-Type':'application/json' },
      body: JSON.stringify({ query, thread_id: threadId }) })),
  snapshot: async (runId: string) => TaskSchema.parse(await request('/api/tasks/' + encodeURIComponent(runId))),
  active: async (threadId: string) => z.object({ run_id: z.string().nullable() }).parse(
    await request('/api/sessions/' + encodeURIComponent(threadId) + '/active')),
  deleteSession: async (threadId: string) => request(
    '/api/sessions/' + encodeURIComponent(threadId), { method: 'DELETE' }),
  files: async (threadId: string) => z.object({ files: z.array(FileSchema) }).parse(
    await request('/api/files?thread_id=' + encodeURIComponent(threadId))),
  upload: async (threadId: string, files: File[]) => {
    const body = new FormData()
    body.append('thread_id', threadId)
    files.forEach(file => body.append('files', file))
    return UploadSchema.parse(await request('/api/upload', { method: 'POST', body }, 120000))
  },
  downloadUrl: async (fileUuid: string) => z.object({
    downloadUrl: z.string().url(), expiresIn: z.number(), filename: z.string(),
  }).parse(await request('/api/files/' + encodeURIComponent(fileUuid) + '/download-url', {
    method: 'POST',
  })),
}
