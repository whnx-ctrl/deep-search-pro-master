import { describe, expect, it } from 'vitest'
import { renderMarkdown, safeUrl } from './markdown'
describe('safe Markdown', () => {
  it('rejects script and data links', () => {
    expect(safeUrl('javascript:alert(1)')).toBeUndefined()
    expect(safeUrl('data:text/html,bad')).toBeUndefined()
    expect(safeUrl('https://example.com')).toBe('https://example.com/')
  })
  it('keeps injected HTML as text and never creates script nodes', () => {
    const result = JSON.stringify(renderMarkdown('<script>alert(1)</script>'))
    expect(result).not.toContain('"type":"script"')
    expect(result).toContain('<script>')
  })
})
