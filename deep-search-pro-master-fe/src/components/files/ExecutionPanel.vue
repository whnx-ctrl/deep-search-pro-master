<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { Activity, FileText, Download, RefreshCw, FolderOpen, X, CircleCheck, CircleAlert } from 'lucide-vue-next'
import { useWorkbenchStore } from '../../stores/useWorkbenchStore'
defineEmits<{ close: [] }>()
const store = useWorkbenchStore()
const { current, files, filesLoading, fileError, busy, health } = storeToRefs(store)
const labels: Record<string,string> = { idle:'尚未开始', queued:'等待执行', running:'进行中', succeeded:'已完成', failed:'执行失败', interrupted:'已中断' }
function size(value: number) { return value < 1024 ? value + ' B' : value < 1024*1024 ? (value/1024).toFixed(1) + ' KB' : (value/1024/1024).toFixed(1) + ' MB' }
</script>
<template>
  <aside class="execution-panel">
    <div class="panel-heading"><h2><Activity :size="16" aria-hidden="true" />执行过程</h2><button class="icon-button" aria-label="收起执行面板" @click="$emit('close')"><X :size="16" aria-hidden="true" /></button></div>
    <div class="run-status" :class="{ failed: current?.status === 'failed' }"><CircleCheck v-if="current?.status === 'succeeded'" :size="15" aria-hidden="true" /><CircleAlert v-else-if="current?.status === 'failed'" :size="15" aria-hidden="true" /><i v-else class="activity-dot" />{{ labels[current?.status || 'idle'] }}<small>当前研究</small></div>
    <ol v-if="current?.events.length" class="timeline">
      <li v-for="event in current.events" :key="event.run_id + ':' + event.sequence"><span class="timeline-dot" /><strong>{{ event.message }}</strong><small>{{ new Date(event.timestamp).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', second:'2-digit' }) }}</small></li>
    </ol>
    <div v-else class="progress-empty"><Activity :size="25" :stroke-width="1.3" aria-hidden="true" /><p>{{ busy ? '任务已提交，等待执行事件' : '研究开始后，过程将在这里呈现' }}</p></div>
    <p v-if="current?.truncated" class="muted-note">仅展示最近 250 条事件，最终回答完整保留。</p>
    <div class="panel-heading files-heading"><h2><FolderOpen :size="16" aria-hidden="true" />会话文件 <small>{{ files.length }}</small></h2><button class="icon-button" aria-label="刷新文件列表" :disabled="filesLoading" @click="store.refreshFiles()"><RefreshCw :size="14" aria-hidden="true" /></button></div>
    <div v-if="filesLoading && !files.length" class="file-skeleton" aria-label="正在加载文件"></div>
    <div v-else-if="fileError" class="file-error" role="alert">{{ fileError }}<button @click="store.refreshFiles()">重试</button></div>
    <div v-else-if="!files.length" class="files-empty"><FileText :size="26" :stroke-width="1.3" aria-hidden="true" /><p>还没有文件</p><small>上传资料或让助手生成一份报告</small></div>
    <div v-for="file in files" :key="file.uuid" class="file-card"><FileText :size="20" :stroke-width="1.5" aria-hidden="true" /><div><strong :title="file.workspaceName">{{ file.workspaceName }}</strong><small>{{ file.source === 'uploaded' ? '上传资料' : '生成产物' }} · {{ size(file.sizeBytes) }}</small></div><button type="button" :aria-label="'下载 ' + file.workspaceName" class="download-button" @click="store.downloadFile(file.uuid)"><Download :size="16" aria-hidden="true" /></button></div>
    <div class="capability-box"><h3>研究能力</h3><div v-for="(label, key) in { search:'网络搜索', database:'经营数据库', knowledge:'内部知识库' }" :key="key"><span>{{ label }}</span><small :class="{ enabled: health?.capabilities[key] }">{{ health?.capabilities[key] ? '已配置' : '未配置' }}</small></div><p>已配置表示存在连接信息，实际状态以调用结果为准。</p></div>
  </aside>
</template>
