<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import api from '../../api'
import KnowledgeGraph from './KnowledgeGraph.vue'

const props = defineProps<{
  userId: string
  major?: string
  knowledgeBase?: Record<string, number>
}>()
const emit = defineEmits<{ (e: 'node-click', id: string): void }>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const selectedCourse = ref<string | null>(null)
const courseKpData = ref<{ nodes: any[]; links: any[]; categories: any[] } | null>(null)
const parseText = ref('')
const parsing = ref(false)
const showParsePanel = ref(false)

const STATUS_COLOR: Record<string, string> = {
  completed:   '#52c41a',
  learning:    '#1890ff',
  planned:     '#69b1ff',
  not_started: '#d9d9d9',
}
const STATUS_LABEL: Record<string, string> = {
  completed:   '已完成',
  learning:    '学习中',
  planned:     '已计划',
  not_started: '未开始',
}

const filteredKb = computed(() => {
  if (!courseKpData.value || !props.knowledgeBase) return {}
  const nodeIds = new Set(courseKpData.value.nodes.map((n: any) => n.id))
  return Object.fromEntries(
    Object.entries(props.knowledgeBase).filter(([k]) => nodeIds.has(k))
  )
})

async function loadGraph() {
  const res = await api.get('/curriculum/graph', {
    params: { user_id: props.userId, major: props.major || '' },
  })
  await nextTick()
  renderGraph(res.data)
}

function renderGraph(data: { nodes: any[]; links: any[] }) {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  chart.resize()

  const nodes = data.nodes.map(n => ({
    id: n.id,
    name: n.id,
    symbolSize: 38,
    status: n.status,
    semester: n.semester,
    category: n.category,
    itemStyle: { color: STATUS_COLOR[n.status] || '#d9d9d9' },
    label: { show: true, position: 'bottom', fontSize: 11, color: '#333' },
  }))

  chart.setOption({
    tooltip: {
      formatter: (p: any) =>
        p.dataType === 'node'
          ? `${p.data.name}<br/>第${p.data.semester || '?'}学期 · ${p.data.category || ''}<br/>状态：${STATUS_LABEL[p.data.status] || p.data.status}`
          : '',
    },
    series: [{
      type: 'graph',
      layout: 'force',
      force: {
        repulsion: 300,
        edgeLength: [80, 160],
        gravity: 0.08,
        layoutAnimation: true,
      },
      roam: true,
      draggable: true,
      nodes,
      edges: data.links.map(l => ({
        source: l.source, target: l.target,
        lineStyle: { color: '#ccc', width: 1.5 },
        symbol: ['none', 'arrow'], symbolSize: 8,
      })),
      emphasis: { focus: 'adjacency' },
    }],
  })

  chart.off('click')
  chart.on('click', async (p: any) => {
    if (p.dataType !== 'node') return
    const courseName = p.data.id

    if (selectedCourse.value === courseName) {
      selectedCourse.value = null
      courseKpData.value = null
      return
    }

    selectedCourse.value = courseName
    try {
      const res = await api.get(`/curriculum/kp/${encodeURIComponent(courseName)}`)
      courseKpData.value = res.data
    } catch {
      courseKpData.value = { nodes: [], links: [], categories: [] }
    }
  })
}

async function parseCurriculum() {
  if (!parseText.value.trim()) return
  parsing.value = true
  try {
    await api.post('/curriculum/parse', { user_id: props.userId, text: parseText.value })
    parseText.value = ''
    showParsePanel.value = false
    await loadGraph()
  } finally {
    parsing.value = false
  }
}

onMounted(async () => {
  await nextTick()
  await loadGraph()
})

watch(() => props.userId, loadGraph)

onUnmounted(() => chart?.dispose())
</script>

<template>
  <div class="curriculum-graph-wrap">
    <div class="cg-toolbar">
      <span class="cg-hint">点击课程节点查看课内知识点</span>
      <el-button size="small" text @click="showParsePanel = !showParsePanel">
        上传我的培养方案
      </el-button>
    </div>

    <div v-if="showParsePanel" class="parse-panel">
      <el-input
        v-model="parseText"
        type="textarea"
        :rows="5"
        placeholder="粘贴你的培养方案文本，AI将自动提取课程和先修关系..."
      />
      <div class="parse-actions">
        <el-button size="small" @click="showParsePanel = false">取消</el-button>
        <el-button size="small" type="primary" :loading="parsing" @click="parseCurriculum">
          AI解析并更新图谱
        </el-button>
      </div>
    </div>

    <div ref="chartRef" class="cg-chart" />

    <div v-if="selectedCourse && courseKpData" class="kp-section">
      <div class="kp-header">
        <span class="kp-title">{{ selectedCourse }} · 知识点图谱</span>
        <el-button size="small" text @click="selectedCourse = null; courseKpData = null">收起</el-button>
      </div>
      <KnowledgeGraph
        :knowledgeBase="filteredKb"
        :graphData="courseKpData"
        @node-click="(id) => emit('node-click', id)"
      />
    </div>
  </div>
</template>

<style scoped>
.curriculum-graph-wrap { display: flex; flex-direction: column; gap: 12px; }
.cg-toolbar { display: flex; justify-content: space-between; align-items: center; }
.cg-hint { font-size: 12px; color: #999; }
.cg-chart { width: 100%; height: 480px; border: 1px solid #f0e8e0; border-radius: 8px; background: #fff; }
.parse-panel { background: #fafafa; border: 1px solid #e8e0d8; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.parse-actions { display: flex; justify-content: flex-end; gap: 8px; }
.kp-section { border: 1px solid #f0e8e0; border-radius: 8px; overflow: hidden; }
.kp-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #fef9f4; border-bottom: 1px solid #f0e8e0; }
.kp-title { font-size: 13px; font-weight: 600; color: #6b5344; }
</style>
