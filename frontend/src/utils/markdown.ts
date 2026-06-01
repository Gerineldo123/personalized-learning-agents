import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import 'katex/dist/katex.min.css'

export function normalizeMathDelimiters(text: string): string {
  return text
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, expr) => `$$\n${String(expr).trim()}\n$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, expr) => `$${String(expr).trim()}$`)
}

const md = new MarkdownIt({ html: false, breaks: true, linkify: true }).use(texmath, {
    engine: katex,
    delimiters: 'dollars',
    katexOptions: { throwOnError: false, strict: 'ignore' },
  } as any)

export function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export const codeBlockStore: Record<string, string> = {}

let codeBlockSeq = 0

export function renderMarkdown(content: string): string {
  return md.render(normalizeMathDelimiters(content || ''))
}

export function renderMarkdownEnhanced(content: string): string {
  codeBlockSeq = 0
  const codeBlockList: Array<{ lang: string; code: string }> = []

  const processed = content.replace(/```\s*(\S*?)[ \t]*\r?\n([\s\S]*?)```/g, (_m, lang, code) => {
    const idx = codeBlockList.length
    codeBlockList.push({ lang: lang || '', code })
    return `\uFFF0CB${idx}\uFFF1`
  })

  let html = renderMarkdown(processed)

  html = html.replace(/\uFFF0CB(\d+)\uFFF1/g, (_m, idxStr) => {
    const idx = +idxStr
    const { lang, code } = codeBlockList[idx]
    const id = `code-${codeBlockSeq++}`
    codeBlockStore[id] = code
    const cls = lang ? ` class="language-${lang}"` : ''
    return `<div class="code-block-wrapper">
      <div class="code-header"><span class="code-lang">${lang}</span><span class="code-copy-btn" data-code-id="${id}">复制</span></div>
      <pre><code${cls}>${escapeHtml(code)}</code></pre>
    </div>`
  })

  return html
}
