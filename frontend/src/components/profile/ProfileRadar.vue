<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

interface KnowledgeBase {
  [key: string]: number
}

const props = defineProps<{
  knowledgeBase: KnowledgeBase
  title?: string
  color?: string
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const accentColor = computed(() => props.color || '#409eff')

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

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
        areaStyle: { color: hexToRgba(accentColor.value, 0.2) },
        lineStyle: { color: accentColor.value },
        itemStyle: { color: accentColor.value },
      },
    ],
  })
}

onMounted(async () => {
  await nextTick()
  renderChart()
  await nextTick()
  chart?.resize()
})

watch(() => props.knowledgeBase, async () => {
  await nextTick()
  renderChart()
  await nextTick()
  chart?.resize()
}, { deep: true })
</script>

<template>
  <div class="profile-radar">
    <div ref="chartRef" class="chart" />
  </div>
</template>

<style scoped>
.profile-radar {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  padding: 20px;
}

.chart {
  width: 100%;
  height: 260px;
}
</style>
