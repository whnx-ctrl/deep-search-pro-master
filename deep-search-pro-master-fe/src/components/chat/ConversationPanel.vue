<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Copy, Check, Sprout, ArrowUpRight, FileSearch, ChartNoAxesCombined, Globe } from 'lucide-vue-next'
import MarkdownMessage from './MarkdownMessage.vue'
import type { Session } from '../../types/workbench'
const props = defineProps<{ session?: Session; busy: boolean }>()
defineEmits<{ example: [value: string] }>()
const panel = ref<HTMLElement>()
const copied = ref('')
const copyError = ref('')
const examples = [
  { icon: Globe, label: '探索行业趋势', text: '搜索近期电商行业趋势，整理核心变化和信息来源。', hint: '从公开信息中寻找新方向' },
  { icon: ChartNoAxesCombined, label: '分析经营数据', text: '查询近 30 天的商品销量，找出销售表现最好的商品。', hint: '连接数据，理解业务变化' },
  { icon: FileSearch, label: '整理上传资料', text: '请分析我上传的资料，提取关键结论并生成 Markdown 报告。', hint: '把零散资料变成清晰结论' },
]
watch(() => [props.session?.messages.length, props.busy, props.session?.uuid], async () => {
  await nextTick()
  panel.value?.scrollTo({ top: panel.value.scrollHeight, behavior: 'auto' })
})
async function copy(uuid: string, content: string) {
  try {
    await navigator.clipboard.writeText(content)
    copied.value = uuid
    setTimeout(() => { copied.value = '' }, 2000)
  } catch { copyError.value = '无法使用剪贴板，请选中文字复制。' }
}
</script>
<template>
  <section ref="panel" class="conversation-panel" aria-label="研究对话">
    <div v-if="!session?.messages.length" class="welcome">
      <span class="eyebrow">A LITTLE CURIOSITY, A CLEARER PICTURE</span>
      <div class="welcome-symbol"><Sprout :size="38" :stroke-width="1.3" aria-hidden="true" /></div>
      <h1>让每一个问题，<br>都有迹可循<span>。</span></h1>
      <p>连接网络、数据与知识，从一个问题开始你的研究。</p>
      <div class="example-cards"><button v-for="example in examples" :key="example.label" class="example-card" @click="$emit('example', example.text)"><component :is="example.icon" :size="21" :stroke-width="1.6" aria-hidden="true" /><strong>{{ example.label }}<ArrowUpRight :size="15" aria-hidden="true" /></strong><small>{{ example.hint }}</small></button></div>
      <div class="welcome-bottom">搜索 · 分析 · 整理 · 生成报告</div>
    </div>
    <div v-else class="message-list">
      <article v-for="message in session.messages" :key="message.uuid" class="message" :class="message.role">
        <template v-if="message.role === 'user'"><div class="user-message">{{ message.content }}</div></template>
        <template v-else>
          <div class="assistant-heading"><Sprout :size="18" aria-hidden="true" /><span>DEEP SEARCH</span><small>{{ message.error ? '执行提示' : '研究结果' }}</small></div>
          <div v-if="message.error" class="error-answer" role="alert">{{ message.content }}</div>
          <MarkdownMessage v-else :content="message.content" />
          <button class="copy-button" @click="copy(message.uuid, message.content)"><Check v-if="copied === message.uuid" :size="14" aria-hidden="true" /><Copy v-else :size="14" aria-hidden="true" />{{ copied === message.uuid ? '已复制' : '复制回答' }}</button>
        </template>
      </article>
      <div v-if="busy" class="researching" role="status"><span class="activity-dot" />正在研究，请稍候…<small>工具调用会显示在执行面板中</small></div>
      <p v-if="copyError" role="alert">{{ copyError }}</p>
    </div>
  </section>
</template>
