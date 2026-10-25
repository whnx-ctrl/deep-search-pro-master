import { apiBase } from './env'
export async function request(path: string, init: RequestInit = {}, timeout = 20000): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(apiBase + path, {
      ...init, signal: controller.signal,
      headers: { 'X-Request-Id': crypto.randomUUID(), ...init.headers },
    })
    const body = response.status === 204 ? null : await response.json()
    if (!response.ok) {
      const error = body as { error?: { message?: string } } | null
      throw new Error(error?.error?.message || '请求失败，请稍后重试')
    }
    return body
  } catch (error) {
    if (error instanceof TypeError) throw new Error('无法连接后端，请确认 8000 端口的服务已启动')
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('请求超时，请检查任务状态后重试')
    throw error
  } finally { clearTimeout(timer) }
}
