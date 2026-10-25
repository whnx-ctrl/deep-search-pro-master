export const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export function websocketUrl(threadId: string) {
  const url = new URL(apiBase || window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/ws/' + encodeURIComponent(threadId)
  return url.toString()
}
