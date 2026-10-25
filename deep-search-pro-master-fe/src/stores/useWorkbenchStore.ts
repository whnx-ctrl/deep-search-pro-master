import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/workbench'
import { loadHistory, saveHistory } from '../lib/history'
import type { Health, RunEvent, Session, SessionFile, TaskSnapshot } from '../types/workbench'

export const useWorkbenchStore = defineStore('workbench', () => {
  const sessions = ref<Session[]>([])
  const selectedUuid = ref('')
  const health = ref<Health | null>(null)
  const online = ref(false)
  const initialized = ref(false)
  const notice = ref('')
  const storageError = ref('')
  const fileError = ref('')
  const uploading = ref(false)
  const submitting = ref(false)
  const deletingUuid = ref('')
  const filesLoading = ref(false)
  const files = ref<SessionFile[]>([])
  const current = computed(() => sessions.value.find(s => s.uuid === selectedUuid.value))
  const busy = computed(() => ['queued','running'].includes(current.value?.status || '') || submitting.value)
  let saveQueue = Promise.resolve()

  function persist() {
    const snapshot = JSON.parse(JSON.stringify(sessions.value)) as Session[]
    saveQueue = saveQueue.then(() => saveHistory(snapshot)).catch(() => {
      storageError.value = '浏览器历史保存失败；请保留当前页面并复制重要回答。'
    })
  }
  function createSession() {
    if (uploading.value || submitting.value) return
    const session: Session = {
      uuid: crypto.randomUUID(), title: '新的研究', instanceId: health.value?.instance_id || '',
      createdAt: Date.now(), messages: [], status: 'idle', events: [], truncated: false,
    }
    sessions.value.unshift(session)
    selectedUuid.value = session.uuid
    files.value = []
    notice.value = ''
    fileError.value = ''
    persist()
  }
  function selectSession(uuid: string) {
    if (uploading.value || submitting.value || deletingUuid.value) return
    selectedUuid.value = uuid
    files.value = []
    notice.value = ''
    void refreshFiles()
  }
  async function deleteSession(uuid: string) {
    const index = sessions.value.findIndex(session => session.uuid === uuid)
    const session = sessions.value[index]
    if (!session || deletingUuid.value || uploading.value || submitting.value ||
        ['queued','running'].includes(session.status)) return false
    deletingUuid.value = uuid
    notice.value = ''
    try {
      await api.deleteSession(uuid)
      sessions.value.splice(index, 1)
      if (selectedUuid.value === uuid) {
        const next = sessions.value[Math.min(index, sessions.value.length - 1)]
        if (next) {
          selectedUuid.value = next.uuid
          files.value = []
          await refreshFiles()
          persist()
        } else {
          createSession()
        }
      } else {
        persist()
      }
      return true
    } catch (error) {
      notice.value = error instanceof Error ? error.message : '删除会话失败'
      return false
    } finally { deletingUuid.value = '' }
  }
  async function checkHealth() {
    try {
      health.value = await api.health()
      online.value = true
    } catch { online.value = false }
  }
  async function initialize() {
    await checkHealth()
    try { sessions.value = await loadHistory() }
    catch { storageError.value = '无法读取本机历史记录，当前会话仍可使用。' }
    if (!sessions.value.length) createSession()
    else selectedUuid.value = sessions.value[0].uuid
    initialized.value = true
    await syncTasks()
    await refreshFiles()
  }
  function applySnapshot(snapshot: TaskSnapshot) {
    const session = sessions.value.find(s => s.uuid === snapshot.thread_id)
    if (!session || (session.runId && session.runId !== snapshot.run_id)) return
    if (['succeeded','failed','interrupted'].includes(session.status) && ['queued','running'].includes(snapshot.status)) return
    session.runId = snapshot.run_id
    session.status = snapshot.status
    session.events = snapshot.events
    session.truncated = snapshot.truncated
    if (['succeeded','failed','interrupted'].includes(snapshot.status)) {
      let message = session.messages.find(m => m.runId === snapshot.run_id && m.role === 'assistant')
      if (!message) {
        message = { uuid: crypto.randomUUID(), role: 'assistant', content: '', runId: snapshot.run_id }
        session.messages.push(message)
      }
      message.content = snapshot.result || snapshot.error || '任务结束，未返回回答'
      message.error = snapshot.status !== 'succeeded'
    }
    persist()
  }
  async function syncTasks() {
    await Promise.all(sessions.value.filter(s => s.runId && ['queued','running'].includes(s.status))
      .map(async session => {
        try {
          const snapshot = await api.snapshot(session.runId!)
          applySnapshot(snapshot)
          if (session.uuid === selectedUuid.value && snapshot.status === 'succeeded') await refreshFiles()
        } catch { /* Keep the active state until a confirmed snapshot arrives. */ }
      }))
  }
  function receiveEvent(event: RunEvent) {
    const session = sessions.value.find(s => s.runId === event.run_id)
    if (!session || session.events.some(e => e.sequence === event.sequence)) return
    session.events = [...session.events, event].sort((a,b) => a.sequence-b.sequence).slice(-250)
    if (['task_result','error','interrupted'].includes(event.event)) void syncTasks()
  }
  async function refreshFiles() {
    const uuid = selectedUuid.value
    if (!uuid) return
    filesLoading.value = true
    fileError.value = ''
    try {
      const response = await api.files(uuid)
      if (selectedUuid.value === uuid) files.value = response.files
    } catch (error) {
      if (selectedUuid.value === uuid) fileError.value = error instanceof Error ? error.message : '文件读取失败'
    } finally { if (selectedUuid.value === uuid) filesLoading.value = false }
  }
  async function uploadFiles(selected: File[]) {
    const session = current.value
    if (!session || busy.value || uploading.value) return
    if (selected.length > 5 || selected.some(f => f.size > 20 * 1024 * 1024)) {
      notice.value = '每次最多 5 个文件，单文件不超过 20 MiB'
      return
    }
    uploading.value = true
    notice.value = ''
    try {
      const result = await api.upload(session.uuid, selected)
      notice.value = result.files.map(f => f.status === 'uploaded' ? '已上传：' + f.name : f.name + '：' + f.error).join('；')
      await refreshFiles()
    } catch (error) { notice.value = error instanceof Error ? error.message : '上传失败' }
    finally { uploading.value = false }
  }
  async function downloadFile(fileUuid: string) {
    fileError.value = ''
    try {
      const result = await api.downloadUrl(fileUuid)
      window.location.assign(result.downloadUrl)
    } catch (error) {
      fileError.value = error instanceof Error ? error.message : '下载地址获取失败'
    }
  }
  async function submit(query: string, connect: () => Promise<void>) {
    const session = current.value
    if (!session || !query.trim() || busy.value || uploading.value) return false
    submitting.value = true
    notice.value = ''
    try {
      await connect()
      const response = await api.task(query.trim(), session.uuid)
      session.instanceId = health.value?.instance_id || session.instanceId
      session.runId = response.run_id
      session.status = 'queued'
      session.events = []
      session.messages.push({ uuid: crypto.randomUUID(), role: 'user', content: query.trim(), runId: response.run_id })
      if (session.messages.length === 1) session.title = query.trim().slice(0, 24)
      persist()
      await syncTasks()
      return true
    } catch (error) {
      notice.value = error instanceof Error ? error.message : '提交失败'
      // A timeout can happen after the backend accepted a task. Discover, never resubmit.
      try {
        const active = await api.active(session.uuid)
        if (active.run_id) {
          session.runId = active.run_id
          session.status = 'running'
          if (!session.messages.some(m => m.runId === active.run_id)) {
            session.messages.push({ uuid: crypto.randomUUID(), role: 'user', content: query.trim(), runId: active.run_id })
          }
          persist()
        }
      } catch { /* Retry health/status manually without replaying the prompt. */ }
      return false
    } finally { submitting.value = false }
  }
  return { sessions, selectedUuid, health, online, initialized, notice, storageError, fileError,
    uploading, submitting, deletingUuid, filesLoading, files, current, busy, persist, initialize,
    createSession, selectSession, deleteSession, checkHealth, syncTasks, receiveEvent, refreshFiles,
    uploadFiles, downloadFile, submit }
})
