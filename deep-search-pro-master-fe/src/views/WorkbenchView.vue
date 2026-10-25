<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { PanelLeft, PanelRight, RefreshCw, Sprout } from 'lucide-vue-next'
import SessionSidebar from '../components/layout/SessionSidebar.vue'
import ChatComposer from '../components/chat/ChatComposer.vue'
import ConversationPanel from '../components/chat/ConversationPanel.vue'
import ExecutionPanel from '../components/files/ExecutionPanel.vue'
import { useWorkbenchStore } from '../stores/useWorkbenchStore'
import { useTaskSocket } from '../composables/useTaskSocket'
const store = useWorkbenchStore()
const { selectedUuid, current, busy, online, initialized, uploading, notice, storageError } = storeToRefs(store)
const leftOpen = ref(false)
const rightOpen = ref(true)
const composer = ref<InstanceType<typeof ChatComposer>>()
const dragging = ref(false)
const socket = useTaskSocket({ threadId: selectedUuid, onEvent: store.receiveEvent,
  onReady: () => { void store.syncTasks() } })
let timer: ReturnType<typeof setInterval> | undefined
onMounted(async () => {
  rightOpen.value = window.innerWidth > 1150
  await store.initialize()
  timer = setInterval(() => { void store.checkHealth(); void store.syncTasks() }, 3000)
})
onUnmounted(() => clearInterval(timer))
async function send(query: string) {
  if (await store.submit(query, socket.ensureConnected)) composer.value?.clear()
}
function dropped(event: DragEvent) {
  dragging.value = false
  if (event.dataTransfer?.files.length) void store.uploadFiles(Array.from(event.dataTransfer.files))
}
</script>
<template>
  <div class="workbench" :class="{ 'right-collapsed': !rightOpen }">
    <div class="sidebar-wrap" :class="{ 'drawer-open': leftOpen }"><SessionSidebar @close="leftOpen = false" /></div>
    <button v-if="leftOpen" class="drawer-backdrop" aria-label="关闭侧栏遮罩" @click="leftOpen = false"></button>
    <main class="main-panel" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="dropped">
      <header class="workbench-header"><div class="header-title"><button class="icon-button mobile-only" aria-label="打开会话列表" @click="leftOpen = true"><PanelLeft :size="18" /></button><Sprout class="header-sprout" :size="17" aria-hidden="true" /><span>{{ current?.title || '个人研究工作台' }}</span></div><div class="header-actions"><span class="connection-status" :class="{ offline: !online }"><i />{{ online ? '本地后端已连接' : '后端未连接' }}</span><button class="icon-button" aria-label="重新连接" @click="store.checkHealth(); socket.reconnect(); store.syncTasks()"><RefreshCw :size="15" /></button><button class="icon-button" :aria-expanded="rightOpen" aria-label="切换执行与文件面板" @click="rightOpen = !rightOpen"><PanelRight :size="18" /></button></div></header>
      <div v-if="storageError" class="banner warning" role="alert">{{ storageError }}</div>
      <div v-if="!online" class="banner warning" role="status">请启动本地后端服务。<button @click="store.checkHealth()">重新检查</button></div>
      <div v-else-if="socket.status.value === 'disconnected'" class="banner warning" role="status">实时连接中断，正在恢复；任务结果也会通过状态查询补齐。<button @click="socket.reconnect()">重连</button></div>
      <div v-if="!initialized" class="initial-skeleton" aria-label="正在加载工作台"><div /><div /><div /></div>
      <ConversationPanel v-else :session="current" :busy="busy" @example="composer?.fill($event)" />
      <div v-if="notice" class="upload-notice" role="status">{{ notice }}<button aria-label="关闭提示" @click="store.notice = ''">×</button></div>
      <div class="composer-area"><ChatComposer ref="composer" :disabled="busy || uploading || !online" :busy="busy" :uploading="uploading" @send="send" @upload="store.uploadFiles" /></div>
      <div v-if="dragging" class="drop-overlay" @dragleave.prevent="dragging = false"><span>松开以添加研究资料</span><small>TXT / Markdown / PDF / DOCX / XLSX</small></div>
    </main>
    <div v-show="rightOpen" class="execution-wrap"><ExecutionPanel @close="rightOpen = false" /></div>
  </div>
</template>
