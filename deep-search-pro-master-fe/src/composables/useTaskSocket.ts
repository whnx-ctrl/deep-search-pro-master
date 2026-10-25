import { onUnmounted, ref, watch, type Ref } from 'vue'
import { websocketUrl } from '../lib/env'
import { EventSchema, type RunEvent } from '../types/workbench'

export function useTaskSocket({ threadId, onEvent, onReady }: {
  threadId: Ref<string>, onEvent: (event: RunEvent) => void, onReady: () => void,
}) {
  const status = ref<'connecting'|'connected'|'disconnected'>('disconnected')
  let socket: WebSocket | undefined
  let retry: ReturnType<typeof setTimeout> | undefined
  let heartbeat: ReturnType<typeof setInterval> | undefined
  let attempts = 0
  let generation = 0
  let disposed = false
  function close() {
    generation++
    clearTimeout(retry)
    clearInterval(heartbeat)
    socket?.close()
    socket = undefined
    status.value = 'disconnected'
  }
  function open() {
    close()
    if (!threadId.value || disposed) return
    const currentGeneration = generation
    status.value = 'connecting'
    const current = new WebSocket(websocketUrl(threadId.value))
    socket = current
    const readyTimeout = setTimeout(() => {
      if (status.value !== 'connected' && generation === currentGeneration) current.close()
    }, 10000)
    current.onmessage = ({ data }) => {
      if (generation !== currentGeneration) return
      try {
        const message = JSON.parse(data)
        if (message.type === 'ready') {
          clearTimeout(readyTimeout)
          attempts = 0
          status.value = 'connected'
          heartbeat = setInterval(() => { if (current.readyState === WebSocket.OPEN) current.send('ping') }, 20000)
          onReady()
        } else {
          const parsed = EventSchema.safeParse(message)
          if (parsed.success) onEvent(parsed.data)
        }
      } catch { /* Invalid transport data cannot enter the UI state. */ }
    }
    current.onclose = () => {
      clearTimeout(readyTimeout)
      if (generation !== currentGeneration || disposed) return
      clearInterval(heartbeat)
      status.value = 'disconnected'
      if (attempts < 6) retry = setTimeout(open, Math.min(1000 * 2 ** attempts++, 15000))
    }
    current.onerror = () => current.close()
  }
  async function ensureConnected() {
    const ready = () => status.value === 'connected'
    if (ready()) return
    if (!socket || socket.readyState > WebSocket.OPEN) { attempts = 0; open() }
    const started = Date.now()
    while (!ready()) {
      if (Date.now() - started > 10000 || disposed) throw new Error('实时连接失败，请确认后端已启动后重试')
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }
  watch(threadId, () => { attempts = 0; open() }, { immediate: true })
  onUnmounted(() => { disposed = true; close() })
  return { status, ensureConnected, reconnect: open }
}
