<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Markmap } from 'markmap-view'
import { Toolbar } from 'markmap-toolbar'
import type { IPureNode } from 'markmap-common'

const props = defineProps<{ markdown: string }>()

const svg = ref<SVGElement>()
let mm: Markmap | null = null

function parseMarkdown(md: string): IPureNode {
  const lines = md.trim().split('\n').filter(Boolean)
  const root: IPureNode = { content: '', children: [] }
  const stack: { node: IPureNode; level: number }[] = [{ node: root, level: 0 }]

  for (const line of lines) {
    const match = line.match(/^(#{1,6})\s+(.+)/)
    if (!match) continue
    const level = match[1].length
    const content = match[2]

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
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}
.mindmap-svg {
  width: 100%;
  height: 600px;
  display: block;
}
</style>
