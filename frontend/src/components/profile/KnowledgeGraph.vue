<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  knowledgeBase: Record<string, number>   // knowledge_base only (not ability_scores)
  discipline?: string                      // 功能4: 学科门类
  graphData?: { nodes: any[]; links: any[]; categories: any[] } | null  // 外部传入图谱数据
}>()

const emit = defineEmits<{
  (e: 'node-click', nodeId: string): void  // 功能3: 跳转资源
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

// 功能4: discipline → 图谱文件映射
const DISCIPLINE_MAP: Record<string, string> = {
  '计算机': '/static/knowledge_graph_cs.json',
  '软件': '/static/knowledge_graph_cs.json',
  '信息': '/static/knowledge_graph_cs.json',
  '数学': '/static/knowledge_graph_math.json',
  '统计': '/static/knowledge_graph_math.json',
  '经济': '/static/knowledge_graph_economics.json',
  '金融': '/static/knowledge_graph_economics.json',
}

function resolveGraphFile(discipline?: string): string | null {
  if (!discipline) return null
  for (const [key, file] of Object.entries(DISCIPLINE_MAP)) {
    if (discipline.includes(key)) return file
  }
  return null
}

let graphData: { nodes: any[]; links: any[]; categories: any[] } | null = null

const MASTERY_COLOR = {
  mastered: '#2F9E8B',
  developing: '#D9922E',
  weak: '#C24B45',
  unassessed: '#A8B0B9',
  next: '#6C63B5',
  nextBorder: '#3F3A87',
}

const isExternalEmptyGraph = computed(() =>
  Boolean(props.graphData && (!props.graphData.nodes || props.graphData.nodes.length === 0))
)

// 功能5: 计算"下一步推荐"节点 —— 前置依赖全绿/橙但自身是红的节点
const nextStepNodes = computed(() => {
  if (!graphData) return []
  const kb = props.knowledgeBase
  // 构建前置依赖 map: target -> [sources]
  const prereqs: Record<string, string[]> = {}
  for (const link of graphData.links) {
    if (!prereqs[link.target]) prereqs[link.target] = []
    prereqs[link.target].push(link.source)
  }
  return graphData.nodes
    .filter(n => {
      const score = kb[n.id] ?? 0
      if (score >= 0.5) return false                        // 自身已掌握
      const pres = prereqs[n.id] || []
      if (!pres.length) return score === 0                  // 无前置的未评估节点也推荐
      return pres.every(p => (kb[p] ?? 0) >= 0.5)          // 前置全部 ≥50%
    })
    .slice(0, 3)
    .map(n => n.id)
})

async function loadGraph() {
  // 优先使用外部传入的图谱数据
  if (props.graphData) {
    graphData = props.graphData
    if (!graphData.nodes?.length) {
      chart?.clear()
      return
    }
    renderChart()
    return
  }

  const file = resolveGraphFile(props.discipline)

  if (file) {
    // 功能4: 加载预置图谱
    if (!graphData) {
      try {
        const r = await fetch(file)
        graphData = await r.json()
      } catch { graphData = null }
    }
  }

  if (!graphData) {
    // 功能1: 动态节点模式 —— 兜底任意专业
    const kb = props.knowledgeBase
    const keys = Object.keys(kb)
    if (!keys.length) return
    graphData = {
      nodes: keys.map(k => ({ id: k, category: 0, value: 0 })),
      links: [],
      categories: [{ name: '知识点' }],
    }
  }

  renderChart()
}

function renderChart() {
  if (!chartRef.value || !graphData) return
  if (!chart) chart = echarts.init(chartRef.value)

  const kb = props.knowledgeBase
  const nextSet = new Set(nextStepNodes.value)

  const nodes = graphData.nodes.map((n: any) => {
    const score = kb[n.id] ?? 0
    const isNext = nextSet.has(n.id)
    const color = isNext ? MASTERY_COLOR.next
      : score >= 0.8 ? MASTERY_COLOR.mastered
      : score >= 0.5 ? MASTERY_COLOR.developing
      : score > 0 ? MASTERY_COLOR.weak
      : MASTERY_COLOR.unassessed
    return {
      ...n,
      name: n.id,
      symbolSize: isNext ? 42 : 28 + score * 20,
      itemStyle: { color, borderColor: isNext ? MASTERY_COLOR.nextBorder : undefined, borderWidth: isNext ? 2 : 0 },
    }
  })

  chart.setOption({
    tooltip: {
      formatter: (p: any) => {
        if (p.dataType === 'edge') return ''
        const score = kb[p.data.id] ?? 0
        const isNext = nextSet.has(p.data.id)
        return `${p.data.id}<br/>掌握度：${score > 0 ? Math.round(score * 100) + '%' : '未评估'}${isNext ? '<br/><b>推荐下一步学习</b>' : ''}`
      }
    },
    legend: [{ data: graphData!.categories.map((c: any) => c.name), bottom: 0, textStyle: { fontSize: 11 } }],
    series: [{
      type: 'graph',
      layout: 'force',
      data: nodes,
      links: graphData!.links,
      categories: graphData!.categories,
      roam: true,
      force: { repulsion: 150, edgeLength: 100 },
      lineStyle: { color: 'source', curveness: 0.1, opacity: 0.42 },
      emphasis: { focus: 'adjacency' },
      label: {
        show: true,
        fontSize: 13,
        fontWeight: 500,
        color: '#2A221E',
        position: 'bottom',
        distance: 6,
      },
    }],
  }, true)

  // 功能3: 点击节点 emit 事件
  chart.off('click')
  chart.on('click', (params: any) => {
    if (params.dataType === 'node') emit('node-click', params.data.id)
  })
}

onMounted(loadGraph)

// 功能4: discipline 变化时重置并重新加载
watch(() => props.discipline, () => { graphData = null; loadGraph() })

// graphData 外部传入时重新加载
watch(() => props.graphData, () => { graphData = null; loadGraph() })

// 功能2: 只响应 knowledgeBase 变化重绘（不再合并 ability_scores）
watch(() => props.knowledgeBase, renderChart, { deep: true })
</script>

<template>
  <div class="kg-wrap">
    <div class="kg-legend">
      <span class="dot" style="background:#67c23a"/> 已掌握(≥80%)
      <span class="dot" style="background:#e6a23c"/> 基础(50-80%)
      <span class="dot" style="background:#f56c6c"/> 薄弱(&lt;50%)
      <span class="dot" style="background:#909399"/> 未评估
      <span class="dot" style="background:#9b59b6"/> 推荐下一步
    </div>
    <div v-if="nextStepNodes.length" class="kg-next">
      推荐优先学习：
      <el-tag v-for="n in nextStepNodes" :key="n" size="small" color="#f3e8ff" style="border-color:#9b59b6;color:#6c3483;margin-left:6px;cursor:pointer" @click="emit('node-click', n)">{{ n }}</el-tag>
    </div>
    <div v-if="isExternalEmptyGraph" class="kg-empty">
      <div class="kg-empty-title">暂无可渲染的知识点节点</div>
      <div class="kg-empty-desc">当前课程还没有配置课内知识点图谱，因此不展示空白画布。</div>
    </div>
    <div v-else ref="chartRef" class="kg-chart" />
  </div>
</template>

<style scoped>
.kg-wrap { background: var(--bg-card, #FFFBF5); border: 1px solid var(--border-light, #EFE6DC); border-radius: var(--radius-md, 12px); padding: 16px; }
.kg-legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary, #6B635C); margin-bottom: 8px; flex-wrap: wrap; align-items: center; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; flex-shrink: 0; }
.dot[style*="#67c23a"] { background: #2F9E8B !important; }
.dot[style*="#e6a23c"] { background: #D9922E !important; }
.dot[style*="#f56c6c"] { background: #C24B45 !important; }
.dot[style*="#909399"] { background: #A8B0B9 !important; }
.dot[style*="#9b59b6"] { background: #6C63B5 !important; }
.kg-next { font-size: 12px; color: #6B635C; margin-bottom: 10px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.kg-next :deep(.el-tag) { background-color: #F0EEFF !important; border-color: #6C63B5 !important; color: #3F3A87 !important; }
.kg-chart { width: 100%; height: 420px; }
.kg-empty { height: 220px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; border: 1px dashed #ead8c4; border-radius: 10px; background: #fffaf4; color: #7A6A5C; }
.kg-empty-title { font-weight: 700; color: #3A332E; }
.kg-empty-desc { font-size: 13px; }
</style>
