<script setup lang="ts">
import { h } from 'vue'
import { renderMarkdown } from '../../lib/markdown'
const props = defineProps<{ content: string }>()
const MarkdownTree = () => h('div', { class: 'markdown-body' }, renderMarkdown(props.content))
</script>
<template><MarkdownTree /></template>
