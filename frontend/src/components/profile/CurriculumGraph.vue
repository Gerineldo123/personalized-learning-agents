<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import api from '../../api'
import KnowledgeGraph from './KnowledgeGraph.vue'

const props = defineProps<{
  userId: string
  major?: string
  knowledgeBase?: Record<string, number>
}>()

const emit = defineEmits<{
  (e: 'node-click', id: string, courseName?: string): void
  (e: 'course-click', courseName: string): void
}>()

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const graphData = ref<{ nodes: any[]; links: any[]; meta?: any } | null>(null)
const selectedCourse = ref<string | null>(null)
const courseKpData = ref<{ nodes: any[]; links: any[]; categories: any[] } | null>(null)
const parseText = ref('')
const parsing = ref(false)
const showParsePanel = ref(false)
const graphSource = ref<'preset' | 'parsed'>('preset')

const STATUS_COLOR: Record<string, string> = {
  completed: '#52c41a',
  learning: '#1890ff',
  available: '#69b1ff',
  locked: '#d9d9d9',
  weak: '#f56c6c',
  recommended: '#9b59b6',
  not_started: '#d9d9d9',
}

const STATUS_LABEL: Record<string, string> = {
  completed: '应已学习',
  learning: '正在学习',
  available: '可学习',
  locked: '未解锁',
  weak: '薄弱',
  recommended: '推荐',
  not_started: '未开始',
}

const RELATION_STYLE: Record<string, any> = {
  prerequisite: { color: '#8c6d5a', width: 2, type: 'solid' },
  support: { color: '#7aa6c2', width: 1.5, type: 'dashed' },
  parallel: { color: '#d8c3a5', width: 1, type: 'dotted' },
  advanced: { color: '#9b59b6', width: 2, type: 'solid' },
  cross_domain: { color: '#d46b08', width: 2, type: 'dashed' },
}

const selectedNode = computed(() =>
  graphData.value?.nodes.find((node: any) => node.id === selectedCourse.value) || null
)

const hasCourseKpGraph = computed(() => Boolean(courseKpData.value?.nodes?.length))

const incomingLinks = computed(() =>
  (graphData.value?.links || []).filter((link: any) => link.target === selectedCourse.value)
)

const outgoingLinks = computed(() =>
  (graphData.value?.links || []).filter((link: any) => link.source === selectedCourse.value)
)

const filteredKb = computed(() => {
  if (!courseKpData.value || !props.knowledgeBase) return {}
  const nodeIds = new Set(courseKpData.value.nodes.map((node: any) => node.id))
  return Object.fromEntries(
    Object.entries(props.knowledgeBase).filter(([key]) => nodeIds.has(key))
  )
})

function percentOf(value: any) {
  return Math.round(Number(value || 0) * 100)
}

function countOf(value: any) {
  return Number(value || 0)
}

async function loadGraph() {
  if (!props.userId) return
  const res = await api.get('/curriculum/graph', {
    params: {
      user_id: props.userId,
      major: props.major || '',
      source: graphSource.value,
    },
  })
  graphData.value = res.data
  await nextTick()
  renderGraph()
}

function renderGraph() {
  if (!chartRef.value || !graphData.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  chart.resize()

  if (!graphData.value.nodes?.length) {
    chart.clear()
    return
  }

  const nodes = graphData.value.nodes.map((node: any) => ({
    ...node,
    id: node.id,
    name: node.name || node.id,
    symbolSize: node.status === 'weak' ? 46 : 38,
    itemStyle: {
      color: STATUS_COLOR[node.status] || '#d9d9d9',
      borderColor: selectedCourse.value === node.id ? '#3A332E' : '#fff',
      borderWidth: selectedCourse.value === node.id ? 3 : 1,
    },
    label: { show: true, position: 'bottom', fontSize: 11, color: '#333' },
  }))

  chart.setOption({
    tooltip: {
      formatter: (params: any) => {
        if (params.dataType === 'edge') {
          return `${params.data.source} → ${params.data.target}<br/>${params.data.type || ''}<br/>${params.data.reason || ''}`
        }
        const data = params.data
        const mastery = percentOf(data.mastery)
        const coverage = percentOf(data.coverage_ratio)
        const measured = countOf(data.measured_kp_count)
        const total = countOf(data.total_kp_count)
        return `${data.name}<br/>第 ${data.semester || '?'} 学期 · ${data.category || ''}<br/>状态：${STATUS_LABEL[data.status] || data.status}<br/>已测掌握度：${mastery}%<br/>覆盖率：${coverage}%（${measured}/${total}）`
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      force: {
        repulsion: 320,
        edgeLength: [90, 170],
        gravity: 0.08,
        layoutAnimation: true,
      },
      roam: true,
      draggable: true,
      nodes,
      edges: graphData.value.links.map((link: any) => {
        const style = RELATION_STYLE[link.type] || RELATION_STYLE.support
        return {
          ...link,
          source: link.source,
          target: link.target,
          lineStyle: style,
          symbol: ['none', 'arrow'],
          symbolSize: 8,
        }
      }),
      emphasis: { focus: 'adjacency' },
    }],
  }, true)

  chart.off('click')
  chart.on('click', (params: any) => {
    if (params.dataType !== 'node') return
    void selectCourse(params.data.id)
  })
}

async function selectCourse(courseName: string) {
  if (selectedCourse.value === courseName) {
    selectedCourse.value = null
    courseKpData.value = null
    renderGraph()
    return
  }

  selectedCourse.value = courseName
  try {
    const res = await api.get(`/curriculum/kp/${encodeURIComponent(courseName)}`, {
      params: { major: props.major || '' },
    })
    courseKpData.value = res.data
  } catch {
    courseKpData.value = { nodes: [], links: [], categories: [] }
  }
  renderGraph()
}

async function parseCurriculum() {
  if (!parseText.value.trim()) return
  parsing.value = true
  try {
    await api.post('/curriculum/parse', { user_id: props.userId, text: parseText.value })
    parseText.value = ''
    showParsePanel.value = false
    graphSource.value = 'parsed'
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
watch(() => props.major, loadGraph)
watch(() => props.knowledgeBase, loadGraph, { deep: true })

onUnmounted(() => chart?.dispose())
</script>

<template>
  <div class="curriculum-graph-wrap">
    <div class="cg-toolbar">
      <span class="cg-hint">
        预制培养方案图谱 · 点击课程节点查看课程关系和课内知识点
      </span>
      <div class="cg-actions">
        <el-tag v-if="graphData?.meta?.major_name" size="small" type="success">
          {{ graphData.meta.major_name }} · 第 {{ graphData.meta.current_semester }} 学期
        </el-tag>
        <el-button v-if="graphSource === 'parsed'" size="small" text @click="graphSource = 'preset'; loadGraph()">
          返回预制图谱
        </el-button>
        <el-button size="small" text @click="showParsePanel = !showParsePanel">
          高级：上传培养方案
        </el-button>
      </div>
    </div>

    <div v-if="showParsePanel" class="parse-panel">
      <el-alert
        title="比赛演示默认使用预制 JSON；上传解析仅作为备用调试入口。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-input
        v-model="parseText"
        type="textarea"
        :rows="5"
        placeholder="粘贴培养方案文本，AI 将提取课程和先修关系..."
      />
      <div class="parse-actions">
        <el-button size="small" @click="showParsePanel = false">取消</el-button>
        <el-button size="small" type="primary" :loading="parsing" @click="parseCurriculum">
          AI解析并查看备用图谱
        </el-button>
      </div>
    </div>

    <div class="cg-layout">
      <div v-if="graphData && graphData.nodes.length === 0" class="cg-empty-state">
        <div class="cg-empty-title">暂无课程图谱</div>
        <div class="cg-empty-desc">当前专业或学期没有匹配到预制培养方案课程节点，请先确认注册专业是否在系统预制范围内。</div>
      </div>
      <div v-else ref="chartRef" class="cg-chart" />
      <div v-if="selectedNode" class="course-panel">
        <div class="course-panel-head">
          <div>
            <h3>{{ selectedNode.name }}</h3>
            <p>第 {{ selectedNode.semester }} 学期 · {{ selectedNode.category }} · {{ selectedNode.credits || '-' }} 学分</p>
          </div>
          <el-tag :type="selectedNode.status === 'weak' ? 'danger' : selectedNode.status === 'learning' ? 'primary' : 'success'">
            {{ STATUS_LABEL[selectedNode.status] || selectedNode.status }}
          </el-tag>
        </div>

        <el-progress :percentage="percentOf(selectedNode.mastery)" :stroke-width="8" />
        <div class="course-mastery-meta">
          <span>已测掌握度 {{ percentOf(selectedNode.mastery) }}%</span>
          <span>覆盖率 {{ percentOf(selectedNode.coverage_ratio) }}%（{{ countOf(selectedNode.measured_kp_count) }}/{{ countOf(selectedNode.total_kp_count) }}）</span>
        </div>

        <el-alert
          v-if="courseKpData && !hasCourseKpGraph"
          title="该课程暂未配置课内知识点图谱"
          description="当前只能展示课程级关系，学习资源会先绑定课程节点；补充 kp_file 后可继续绑定具体知识点。"
          type="warning"
          :closable="false"
          show-icon
        />

        <div class="relation-block">
          <div class="relation-title">前置/支撑课程</div>
          <el-empty v-if="incomingLinks.length === 0" description="暂无前置关系" :image-size="48" />
          <div v-else class="relation-tags">
            <el-tag v-for="link in incomingLinks" :key="link.source + link.type" size="small" effect="plain">
              {{ link.source }} · {{ link.type }}
            </el-tag>
          </div>
        </div>

        <div class="relation-block">
          <div class="relation-title">后继/进阶课程</div>
          <el-empty v-if="outgoingLinks.length === 0" description="暂无后继关系" :image-size="48" />
          <div v-else class="relation-tags">
            <el-tag v-for="link in outgoingLinks" :key="link.target + link.type" size="small" effect="plain">
              {{ link.target }} · {{ link.type }}
            </el-tag>
          </div>
        </div>

        <div class="course-actions">
          <el-button size="small" type="primary" @click="emit('course-click', selectedNode.name)">
            去生成课程资源包
          </el-button>
          <el-button size="small" text @click="selectedCourse = null; courseKpData = null; renderGraph()">
            收起
          </el-button>
        </div>
      </div>
    </div>

    <div v-if="selectedCourse && courseKpData" class="kp-section">
      <div class="kp-header">
        <span class="kp-title">{{ selectedCourse }} · 知识点图谱</span>
        <span class="kp-tip">点击知识点可进入学习资源页生成补弱资源</span>
      </div>
      <KnowledgeGraph
        v-if="hasCourseKpGraph"
        :knowledgeBase="filteredKb"
        :graphData="courseKpData"
        @node-click="(id) => emit('node-click', id, selectedCourse || undefined)"
      />
      <div v-else class="kp-empty-state">
        <div class="kp-empty-title">暂无课内知识点图谱</div>
        <div class="kp-empty-desc">
          该课程在培养方案中存在课程节点，但还没有关联具体 kp_file。
          当前不会渲染空白图谱，也不会伪造知识点标签。
        </div>
        <el-button size="small" type="primary" @click="emit('course-click', selectedCourse)">
          按课程生成资源包
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.curriculum-graph-wrap { display: flex; flex-direction: column; gap: 12px; }
.cg-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.cg-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.cg-hint { font-size: 12px; color: #6B635C; }
.cg-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 12px; }
.cg-chart { width: 100%; height: 520px; border: 1px solid #f0e8e0; border-radius: 8px; background: #fff; }
.cg-empty-state { width: 100%; height: 520px; border: 1px dashed #ead8c4; border-radius: 8px; background: #fffaf4; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; text-align: center; padding: 24px; color: #7A6A5C; }
.cg-empty-title { font-weight: 700; color: #3A332E; }
.cg-empty-desc { max-width: 520px; font-size: 13px; line-height: 1.7; }
.course-panel { border: 1px solid #f0e8e0; border-radius: 8px; background: #fffaf4; padding: 14px; display: flex; flex-direction: column; gap: 14px; }
.course-panel-head { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
.course-panel h3 { margin: 0 0 6px; color: #3A332E; font-size: 17px; }
.course-panel p { margin: 0; color: #7A6A5C; font-size: 12px; }
.course-mastery-meta { display: flex; justify-content: space-between; gap: 8px; color: #7A6A5C; font-size: 12px; }
.relation-block { display: flex; flex-direction: column; gap: 8px; }
.relation-title { font-size: 13px; font-weight: 600; color: #3A332E; }
.relation-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.course-actions { display: flex; justify-content: space-between; margin-top: auto; }
.parse-panel { background: #fafafa; border: 1px solid #e8e0d8; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.parse-actions { display: flex; justify-content: flex-end; gap: 8px; }
.kp-section { border: 1px solid #f0e8e0; border-radius: 8px; overflow: hidden; }
.kp-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #fef9f4; border-bottom: 1px solid #f0e8e0; gap: 12px; }
.kp-title { font-size: 13px; font-weight: 600; color: #6b5344; }
.kp-tip { font-size: 12px; color: #9A8A7A; }
.kp-empty-state { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #7A6A5C; background: #fffaf4; padding: 24px; text-align: center; }
.kp-empty-title { font-weight: 700; color: #3A332E; }
.kp-empty-desc { max-width: 560px; font-size: 13px; line-height: 1.7; }
@media (max-width: 960px) {
  .cg-layout { grid-template-columns: 1fr; }
  .course-panel { min-height: auto; }
}
</style>
