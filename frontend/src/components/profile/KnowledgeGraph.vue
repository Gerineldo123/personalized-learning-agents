<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  // knowledgeBase: {知识点名称: 0-1分数}
  knowledgeBase: Record<string, number>
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

// 加载预置CS知识图谱
let graphData: { nodes: any[]; links: any[]; categories: any[] } | null = null

async function loadGraph() {
  if (!graphData) {
    try {
      const r = await fetch('/static/knowledge_graph_cs.json')
      graphData = await r.json()
    } catch { return }
  }
  renderChart()
}

function renderChart() {
  if (!chartRef.value || !graphData) return
  if (!chart) chart = echarts.init(chartRef.value)

  const kb = props.knowledgeBase || {}
  const nodes = graphData.nodes.map((n: any) => {
    const score = kb[n.id] ?? 0
    const color = score >= 0.8 ? '#67c23a' : score >= 0.5 ? '#e6a23c' : score > 0 ? '#f56c6c' : '#909399'
    return {
      ...n,
      symbolSize: 28 + score * 20,
      itemStyle: { color },
      label: { show: true, fontSize: 11 },
    }
  })

  chart.setOption({
    tooltip: {
      formatter: (p: any) => {
        const score = kb[p.data.id] ?? 0
        return `${p.data.id}<br/>掌握度：${score > 0 ? Math.round(score * 100) + '%' : '未评估'}`
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
      force: { repulsion: 120, edgeLength: 80 },
      lineStyle: { color: 'source', curveness: 0.1, opacity: 0.5 },
      emphasis: { focus: 'adjacency' },
    }],
  })
}

onMounted(loadGraph)
watch(() => props.knowledgeBase, renderChart, { deep: true })
</script>

<template>
  <div class="kg-wrap">
    <div class="kg-legend">
      <span class="dot" style="background:#67c23a"/> 已掌握(≥80%)
      <span class="dot" style="background:#e6a23c"/> 基础(50-80%)
      <span class="dot" style="background:#f56c6c"/> 薄弱(&lt;50%)
      <span class="dot" style="background:#909399"/> 未评估
    </div>
    <div ref="chartRef" class="kg-chart" />
  </div>
</template>

<style scoped>
.kg-wrap { background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 16px; }
.kg-legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; flex-wrap: wrap; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; }
.kg-chart { width: 100%; height: 360px; }
</style>
