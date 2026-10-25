import MarkdownIt from 'markdown-it'
import { h, type VNodeChild } from 'vue'
import type Token from 'markdown-it/lib/token.mjs'
const parser = new MarkdownIt({ html: false, linkify: false, breaks: true })
const tags = new Set(['p','h1','h2','h3','h4','h5','h6','blockquote','ul','ol','li','strong','em','s','table','thead','tbody','tr','th','td','a'])
export function safeUrl(value: string) {
  try { const url = new URL(value); return ['http:','https:'].includes(url.protocol) ? url.href : undefined }
  catch { return undefined }
}
export function renderMarkdown(source: string): VNodeChild[] {
  function render(tokens: Token[]): VNodeChild[] {
    const root: VNodeChild[] = []
    const stack: { tag: string, props: Record<string, unknown>, children: VNodeChild[] }[] = []
    const append = (node: VNodeChild) => (stack.at(-1)?.children || root).push(node)
    for (const token of tokens) {
      if (token.nesting === 1) {
        const tag = tags.has(token.tag) ? token.tag : 'span'
        const props: Record<string, unknown> = {}
        if (tag === 'a') {
          props.href = safeUrl(token.attrGet('href') || '')
          props.target = '_blank'; props.rel = 'noopener noreferrer'
        }
        stack.push({ tag, props, children: [] })
      } else if (token.nesting === -1) {
        const item = stack.pop()
        if (item) append(h(item.tag, item.props, item.children))
      } else if (token.type === 'inline') append(render(token.children || []))
      else if (token.type === 'fence' || token.type === 'code_block') append(h('pre', [h('code', token.content)]))
      else if (token.type === 'code_inline') append(h('code', token.content))
      else if (token.type === 'softbreak' || token.type === 'hardbreak') append(h('br'))
      else if (token.type === 'hr') append(h('hr'))
      else if (token.type === 'image') append(token.content)
      else append(token.content)
    }
    return root
  }
  return render(parser.parse(source, {}))
}
