<script setup lang="ts">
import { ref } from 'vue'
import { ArrowUp, Paperclip } from 'lucide-vue-next'
const props = defineProps<{ disabled: boolean; busy: boolean; uploading: boolean }>()
const emit = defineEmits<{ send: [query: string]; upload: [files: File[]] }>()
const text = ref('')
const input = ref<HTMLInputElement>()
function send() {
  if (!text.value.trim() || props.disabled) return
  emit('send', text.value)
}
function chosen(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  if (files.length) emit('upload', files)
  target.value = ''
}
function fill(value: string) { text.value = value }
function clear() { text.value = '' }
defineExpose({ fill, clear })
</script>
<template>
  <form class="composer" @submit.prevent="send">
    <label class="sr-only" for="research-query">研究问题</label>
    <textarea id="research-query" v-model="text" maxlength="20000" rows="3" :disabled="disabled" placeholder="提出问题，或上传资料，让研究更进一步…" @keydown.enter="event => { if (!event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); send() } }"></textarea>
    <div class="composer-toolbar"><button type="button" class="attach-button" :disabled="disabled" @click="input?.click()"><Paperclip :size="16" aria-hidden="true" />{{ uploading ? '正在上传…' : '添加文件' }}</button><span class="keyboard-hint">Enter 发送 · Shift + Enter 换行</span><button class="send-button" type="submit" :disabled="disabled || !text.trim()" aria-label="发送问题"><ArrowUp :size="20" aria-hidden="true" /></button></div>
    <input ref="input" class="sr-only" type="file" multiple accept=".txt,.md,.pdf,.docx,.xlsx" aria-label="选择上传文件" @change="chosen">
  </form>
  <p class="composer-note">AI 生成内容可能存在偏差，请核实重要信息。<span>单文件 ≤ 20 MiB · 最多 5 个</span></p>
</template>
