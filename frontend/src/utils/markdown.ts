// @ts-nocheck
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

/**
 * 渲染纯文本中的行内数学公式（非 Markdown 场景，如 QuizCard 的题面/选项/解析）
 * 处理 $...$ / $$...$$ 分隔的 LaTeX，也会识别题库中常见的裸数学表达式。
 */
export function renderMathInline(text: string): string {
  if (!text) return ''
  const normalizedText = normalizeMathDelimiters(text)
  // Step 1: $$ display math blocks
  const displayPlaceholders: string[] = []
  let step1 = normalizedText.replace(/\$\$([^$]+)\$\$/g, (_m, formula) => {
    try {
      const html = renderKatexFormula(formula, true)
      const idx = displayPlaceholders.length
      displayPlaceholders.push(html)
      return `\uFFF0DM${idx}\uFFF1`
    } catch { return _m }
  })
  // Step 2: $ inline math (single $, not followed by another $)
  const inlinePlaceholders: string[] = []
  let step2 = step1.replace(/\$([^$]+)\$/g, (_m, formula) => {
    try {
      const html = renderKatexFormula(formula, false)
      const idx = inlinePlaceholders.length
      inlinePlaceholders.push(html)
      return `\uFFF0IM${idx}\uFFF1`
    } catch { return _m }
  })
  step2 = renderLooseMathSegments(step2)
  // Restore display blocks
  step2 = step2.replace(/\uFFF0IM(\d+)\uFFF1/g, (_m, idx) => inlinePlaceholders[+idx] || _m)
  step2 = step2.replace(/\uFFF0DM(\d+)\uFFF1/g, (_m, idx) => displayPlaceholders[+idx] || _m)
  return step2
}

const MATH_SYMBOLS = new Set('∫∑√∞≤≥≠≈→←↦∀∃εεδδθλπμΩαβγΔ')

function renderKatexFormula(formula: string, displayMode = false): string {
  return katex.renderToString(normalizeFormulaForKatex(formula), {
    throwOnError: false,
    strict: 'ignore',
    displayMode,
    trust: false,
  })
}

function normalizeFormulaForKatex(formula: string): string {
  const subscriptMap: Record<string, string> = {
    '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
    '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
  }
  return String(formula || '')
    .trim()
    .replace(/[₀-₉]+/g, (m) => `_{${Array.from(m).map(ch => subscriptMap[ch] || ch).join('')}}`)
    .replace(/([A-Za-z])(\d+)/g, '$1_{$2}')
    .replace(/lim_/g, '\\lim_')
    .replace(/→|↦/g, '\\to ')
    .replace(/←/g, '\\leftarrow ')
    .replace(/∞/g, '\\infty ')
    .replace(/≤/g, '\\le ')
    .replace(/≥/g, '\\ge ')
    .replace(/≠/g, '\\ne ')
    .replace(/≈/g, '\\approx ')
    .replace(/∫/g, '\\int ')
    .replace(/∑/g, '\\sum ')
    .replace(/√/g, '\\sqrt')
    .replace(/∀/g, '\\forall ')
    .replace(/∃/g, '\\exists ')
    .replace(/ε/g, '\\varepsilon ')
    .replace(/δ/g, '\\delta ')
    .replace(/θ/g, '\\theta ')
    .replace(/λ/g, '\\lambda ')
    .replace(/π/g, '\\pi ')
    .replace(/μ/g, '\\mu ')
}

function isLooseMathChar(ch: string): boolean {
  return /[A-Za-z0-9\s+\-*/=<>^_{}()[\].,|\\']/.test(ch) || MATH_SYMBOLS.has(ch)
}

function shouldRenderLooseMath(segment: string): boolean {
  const value = segment.trim()
  if (value.length < 2) return false
  if (/^https?:\/\//i.test(value)) return false
  return (
    /\\[a-zA-Z]+/.test(value) ||
    /lim_\{/.test(value) ||
    /[∫∑√∞≤≥≠≈→←↦∀∃εεδδθλπμΩαβγΔ]/.test(value) ||
    /[A-Za-z]\s*'\s*\(/.test(value) ||
    /[A-Za-z]\([^)]*\)/.test(value) ||
    /[_^]/.test(value) ||
    (/[+\-*/=<>]/.test(value) && /[A-Za-z0-9]/.test(value))
  )
}

function renderLooseMathSegments(text: string): string {
  let output = ''
  let index = 0
  while (index < text.length) {
    const ch = text[index]
    if (!isLooseMathChar(ch)) {
      output += escapeHtml(ch)
      index += 1
      continue
    }
    let end = index
    while (end < text.length && isLooseMathChar(text[end])) end += 1
    const segment = text.slice(index, end)
    if (shouldRenderLooseMath(segment)) {
      const match = segment.match(/^(\s*)([\s\S]*?)(\s*)$/)
      const leading = match?.[1] || ''
      const body = match?.[2] || segment
      const trailing = match?.[3] || ''
      try {
        output += escapeHtml(leading) + renderKatexFormula(body) + escapeHtml(trailing)
      } catch {
        output += escapeHtml(segment)
      }
    } else {
      output += escapeHtml(segment)
    }
    index = end
  }
  return output
}

export const codeBlockStore: Record<string, string> = {}

let codeBlockSeq = 0

export function renderMarkdown(content: string): string {
  return md.render(normalizeMathDelimiters(content || ''))
}

export function renderMarkdownEnhanced(content: string): string {
  codeBlockSeq = 0
  const codeBlockList: Array<{ lang: string; code: string }> = []

  // 提取原始HTML块（视频卡片等），避免被 markdown-it (html:false) 转义
  const htmlBlocks: string[] = []
  let preprocessed = content
    .replace(/<div class="video-results">[\s\S]*?<\/div>\s*$/gm, (m) => { const i = htmlBlocks.length; htmlBlocks.push(m); return `\uFFF0HT${i}\uFFF1` })
    .replace(/<script[\s>][\s\S]*?<\/script>/g, (m) => { const i = htmlBlocks.length; htmlBlocks.push(m); return `\uFFF0HT${i}\uFFF1` })
    .replace(/<style[\s>][\s\S]*?<\/style>/g, (m) => { const i = htmlBlocks.length; htmlBlocks.push(m); return `\uFFF0HT${i}\uFFF1` })

  const processed = preprocessed.replace(/```\s*(\S*?)[ \t]*\r?\n([\s\S]*?)```/g, (_m, lang, code) => {
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

  // 还原 HTML 块
  html = html.replace(/\uFFF0HT(\d+)\uFFF1/g, (_m, i) => htmlBlocks[+i] || '')

  return html
}
