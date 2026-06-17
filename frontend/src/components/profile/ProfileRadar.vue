<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

interface KnowledgeBase {
  [key: string]: number
}

const props = defineProps<{
  knowledgeBase: KnowledgeBase
  title?: string
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chartRef.value) return

  const subjects = Object.keys(props.knowledgeBase || {})
  const rawValues = Object.values(props.knowledgeBase || {}) as number[]
  const maxRaw = rawValues.length ? Math.max(...rawValues) : 0
  const radarMax = maxRaw <= 1 ? 1 : 10
  const values = rawValues.map((v) => Math.max(0, Math.min(v, radarMax)))

  if (subjects.length === 0) return

  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  chart.setOption({
    title: { text: props.title || '能力雷达图', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {},
    radar: {
      indicator: subjects.map((s) => ({ name: s, max: radarMax })),
    },
    series: [
      {
        type: 'radar',
        data: [{ value: values, name: '当前水平' }],
        areaStyle: { color: 'rgba(249, 217, 184, 0.25)' },
        lineStyle: { color: '#DBA878' },
        itemStyle: { color: '#DBA878' },
      },
    ],
  })
}

onMounted(() => renderChart())
watch(() => props.knowledgeBase, () => renderChart(), { deep: true })
</script>

<template>
  <div class="profile-radar">
    <div ref="chartRef" class="chart" />
  </div>
</template>

<style scoped>
.profile-radar {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  padding: 20px;
}
.chart {
  width: 100%;
  height: 260px;
}
</style>
