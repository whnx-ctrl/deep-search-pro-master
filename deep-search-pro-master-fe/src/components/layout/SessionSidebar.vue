<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { Plus, MessageSquare, Sprout, PanelLeftClose, Monitor, Trash2 } from 'lucide-vue-next'
import { useWorkbenchStore } from '../../stores/useWorkbenchStore'
defineEmits<{ close: [] }>()
const store = useWorkbenchStore()
const { sessions, selectedUuid, uploading, submitting, deletingUuid } = storeToRefs(store)
async function deleteSession(uuid: string, title: string) {
  if (!window.confirm(`确定删除“${title}”吗？\n\n对话记录、模型记忆和会话文件都会永久删除。`)) return
  await store.deleteSession(uuid)
}
</script>
<template>
  <aside class="session-sidebar">
    <div class="brand-row"><div class="brand-mark"><Sprout :size="23" aria-hidden="true" /></div><div><strong>Deep Search<span class="brand-dot">.</span></strong><small>PRO · 个人研究空间</small></div><button class="icon-button mobile-only" aria-label="关闭会话列表" @click="$emit('close')"><PanelLeftClose :size="18" /></button></div>
    <button class="new-session" :disabled="uploading || submitting" @click="store.createSession(); $emit('close')"><Plus :size="17" aria-hidden="true" />新建研究<span>＋</span></button>
    <div class="sidebar-label">你的研究 <span>{{ sessions.length }}</span></div>
    <nav class="session-list" aria-label="会话列表">
      <div v-for="session in sessions" :key="session.uuid" class="session-item" :class="{ selected: session.uuid === selectedUuid }">
        <button class="session-select" :disabled="uploading || submitting || Boolean(deletingUuid)" :aria-current="session.uuid === selectedUuid ? 'page' : undefined" @click="store.selectSession(session.uuid); $emit('close')">
          <MessageSquare :size="15" aria-hidden="true" /><span>{{ session.title }}</span><i v-if="['queued','running'].includes(session.status)" class="activity-dot" />
        </button>
        <button class="session-delete" :aria-label="`删除会话：${session.title}`" :disabled="uploading || submitting || Boolean(deletingUuid) || ['queued','running'].includes(session.status)" @click="deleteSession(session.uuid, session.title)">
          <Trash2 :size="14" aria-hidden="true" />
        </button>
      </div>
    </nav>
    <div class="sidebar-footer"><Monitor :size="18" aria-hidden="true" /><div>本地工作区<small>历史记录保存在当前浏览器</small></div><span class="local-tag">LOCAL</span></div>
  </aside>
</template>
