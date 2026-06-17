<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Markmap } from 'markmap-view'
import { Toolbar } from 'markmap-toolbar'
import type { IPureNode } from 'markmap-common'
import katex from 'katex'

const props = defineProps<{ markdown: string }>()

const svg = ref<SVGElement>()
let mm: Markmap | null = null

function renderMath(text: string): string {
  let result = text
  result = result.replace(/\$\$([\s\S]*?)\$\$/g, (_m, formula: string) => {
    try {
      return katex.renderToString(formula.trim(), { throwOnError: false, displayMode: true })
    } catch {
      return _m
    }
  })
  result = result.replace(/(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)/g, (_m, formula: string) => {
    try {
      return katex.renderToString(formula.trim(), { throwOnError: false })
    } catch {
      return _m
    }
  })
  return result
}

function parseMarkdown(md: string): IPureNode {
  const lines = md.trim().split('\n').filter(Boolean)
  const root: IPureNode = { content: '', children: [] }
  const stack: { node: IPureNode; level: number }[] = [{ node: root, level: 0 }]

  for (const line of lines) {
    const match = line.match(/^(#{1,6})\s+(.+)/)
    if (!match) continue
    const level = match[1].length
    const content = renderMath(match[2])

    const node: IPureNode = { content, children: [] }

    while (stack.length > 0 && stack[stack.length - 1].level >= level) {
      stack.pop()
    }

    const parent = stack[stack.length - 1]
    parent.node.children.push(node)
    stack.push({ node, level })
  }

  if (root.children.length === 1) return root.children[0]
  if (root.children.length > 1) return { content: '', children: root.children }
  return root
}

function fixMathNodes() {
  if (!svg.value) return
  const textEls = svg.value.querySelectorAll('text')
  textEls.forEach((textEl) => {
    const raw = textEl.textContent || ''
    if (!raw.includes('class="katex"')) return

    const bbox = textEl.getBBox()
    const foreignObj = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject')

    foreignObj.setAttribute('x', String(bbox.x))
    foreignObj.setAttribute('y', String(bbox.y - 6))
    foreignObj.setAttribute('width', '360')
    foreignObj.setAttribute('height', '1')
    foreignObj.style.overflow = 'visible'

    const div = document.createElementNS('http://www.w3.org/1999/xhtml', 'div')
    div.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml')
    div.style.cssText = 'font-size:14px;line-height:1.7;color:#333;word-break:break-word;white-space:normal'
    div.innerHTML = raw
    foreignObj.appendChild(div)

    textEl.replaceWith(foreignObj)
  })
}

function render() {
  if (!svg.value || !props.markdown) return

  const data = parseMarkdown(props.markdown)
  if (!data.children?.length && !data.content) return

  if (mm) {
    mm.setData(data)
  } else {
    mm = Markmap.create(svg.value, { initialExpandLevel: 2, maxWidth: 300 }, data)
    Toolbar.create(mm).attach(mm)
  }
  nextTick(() => {
    fixMathNodes()
    mm?.fit()
  })
}

function destroy() {
  mm?.destroy()
  mm = null
}

watch(() => props.markdown, () => {
  if (props.markdown) {
    nextTick(render)
  }
})

onMounted(() => {
  if (props.markdown) render()
})

onUnmounted(destroy)
</script>

<template>
  <div ref="container" class="mindmap-viewer">
    <svg ref="svg" class="mindmap-svg" />
  </div>
</template>

<style scoped>
.mindmap-viewer {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  overflow: hidden;
}
.mindmap-svg {
  width: 100%;
  height: 600px;
  display: block;
}
</style>
