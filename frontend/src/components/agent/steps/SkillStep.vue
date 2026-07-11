<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import type { AgentStep, SkillData } from '../../../types/agent'
import MarkdownIt from 'markdown-it'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import api from '../../../api'
import { useUserStore } from '../../../stores/user'
import { skillDisplayName, skillDisplayIcon } from '../../../utils/agentLabels'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

const props = defineProps<{ step: AgentStep }>()
const userStore = useUserStore()

const expanded = ref(props.step.status === 'running')

const data = computed(() => props.step.data as SkillData & { render_type?: string })
const draftResource = computed(() => data.value.draft_resource || null)
const savingDraft = ref(false)
const savedResourceId = ref<number | null>(null)
const saveError = ref('')
const savedDraftResourceId = computed(() => savedResourceId.value || (draftResource.value as any)?.saved_resource_id || null)

function draftResourceTypeLabel(type?: string) {
  const map: Record<string, string> = {
    article: '文章',
    quiz: '题库',
    code: '代码',
    anime: '动画',
    mindmap: '思维导图',
    ppt: 'PPT课件',
    video: '视频',
  }
  return map[type || ''] || type || '学习资源'
}

const displaySkillName = computed(() => skillDisplayName(data.value.skill_name))
const displaySkillIcon = computed(() => data.value.skill_icon || skillDisplayIcon(data.value.skill_name))

const chartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

const isRadialTree = computed(() => {
  return data.value.render_type === 'radial_tree' || data.value.skill_name === 'mindmap_gen'
})

const isVideoCards = computed(() => {
  return data.value.render_type === 'video_cards'
})

const isPptViewer = computed(() => {
  return data.value.render_type === 'ppt_viewer'
})

const isPptSession = computed(() => {
  return data.value.render_type === 'ppt_session'
})

const isStreamingCode = computed(() => props.step.status === 'running' && !!data.value.streaming_code)

const progressValue = computed(() => {
  const raw = Number(data.value.progress ?? 0)
  if (!Number.isFinite(raw)) return 0
  return Math.max(0, Math.min(100, raw))
})

const hasProgress = computed(() => {
  if (isStreamingCode.value) return false
  return data.value.progress !== undefined || !!data.value.current_phase || !!data.value.progress_note
})

const currentPhase = computed(() => data.value.current_phase || (props.step.status === 'running' ? '处理中' : '完成'))
const progressNote = computed(() => data.value.progress_note || '')
const isProgressIndeterminate = computed(() => props.step.status === 'running' && !!data.value.progress_indeterminate)
const progressLabel = computed(() => {
  if (data.value.progress_label) return data.value.progress_label
  if (isProgressIndeterminate.value) return '生成中...'
  return `${Math.round(progressValue.value)}%`
})

function progressStatus() {
  if (props.step.status === 'error') return 'exception'
  if (props.step.status === 'completed') return 'success'
  return undefined
}

interface VideoItem {
  title: string
  url: string
  cover: string
  duration: string
  author: string
  play_count: string
  danmaku: string
  bvid: string
}

const videoList = computed<VideoItem[]>(() => {
  if (!isVideoCards.value || !data.value.content) return []
  try {
    const parsed = JSON.parse(data.value.content)
    if (Array.isArray(parsed)) return parsed
  } catch {
    // not valid JSON
  }
  return []
})

interface PptPreviewData {
  title: string
  slides: Array<{ title: string; content: string[]; notes?: string }>
  pptx_url: string
  slide_count: number
  db_id: number | null
}

const pptData = computed<PptPreviewData | null>(() => {
  if (!isPptViewer.value || !data.value.content) return null
  try {
    const parsed = JSON.parse(data.value.content)
    if (parsed && parsed.slides) return parsed
  } catch {
    // not valid JSON
  }
  return null
})

const pptSessionPayload = computed<any | null>(() => {
  if (!isPptSession.value || !data.value.content) return null
  try {
    const parsed = JSON.parse(data.value.content)
    if (parsed?.ppt_session) return parsed
  } catch {
    // not valid JSON
  }
  return null
})

const pptSessionHref = computed(() => {
  const payload = pptSessionPayload.value
  const session = payload?.ppt_session || {}
  const params = new URLSearchParams()
  if (session.session_id && !session.pending_binding) params.set('session_id', session.session_id)
  if (session.topic || payload?.title) params.set('topic', session.topic || payload.title)
  if (session.course_name) params.set('course', session.course_name)
  if (Array.isArray(session.knowledge_points) && session.knowledge_points.length) {
    params.set('kp', session.knowledge_points.join(','))
  }
  if (session.scope === 'extension') params.set('scope', 'extension')
  return `/ppt${params.toString() ? `?${params.toString()}` : ''}`
})

const pptCurrentSlide = ref(0)

function pptPrev() {
  if (pptCurrentSlide.value > 0) pptCurrentSlide.value--
}

function pptNext() {
  const total = pptData.value?.slides.length || 1
  if (pptCurrentSlide.value < total - 1) pptCurrentSlide.value++
}

function pptUrl(): string {
  const url = pptData.value?.pptx_url || ''
  if (!url) return ''
  if (url.startsWith('http')) return url
  // 补全后端静态文件地址
  return `${window.location.protocol}//${window.location.host}${url}`
}

const treeData = computed(() => {
  const d = data.value
  if (!isRadialTree.value || !d.content) return null
  try {
    const parsed = JSON.parse(d.content)
    if (parsed && parsed.name) return parsed
  } catch {
    // 涓嶆槸 JSON锛屽彲鑳芥槸 markdown 鏍煎紡鐨勬棫鏁版嵁
  }
  return null
})

const renderedContent = computed(() => {
  const d = data.value
  if (!d.content) return ''
  if (d.language) return ''
  if (isRadialTree.value && treeData.value) return ''
  if (isVideoCards.value && videoList.value.length > 0) return ''
  // 对 Markdown 内容进行渲染
  if (d.content.startsWith('#')) {
    return md.render(d.content)
  }
  if (d.content.startsWith('{') || d.content.startsWith('[')) {
    return ''
  }
  return ''
})

function initChart() {
  if (!chartRef.value || !treeData.value) return
  if (chartInstance) {
    chartInstance.dispose()
  }
  chartInstance = echarts.init(chartRef.value)
  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'item',
      triggerOn: 'mousemove',
      formatter: (params: any) => {
        const detail = params.data?.detail || ''
        const name = params.name || ''
        if (detail) {
          return `<div style="max-width:320px;word-wrap:break-word;line-height:1.6;"><b style="color:#DBA878;font-size:14px;">${name}</b><br/><span style="color:#6B635C;font-size:12px;">${detail}</span></div>`
        }
        return `<div style="max-width:260px;word-wrap:break-word;">${name}</div>`
      },
    },
    series: [
      {
        type: 'tree',
        data: [treeData.value],
        layout: 'radial',
        roam: true,
        symbol: 'circle',
        symbolSize: 8,
        initialTreeDepth: -1,
        animationDurationUpdate: 500,
        emphasis: {
          focus: 'descendant',
          label: { fontSize: 13, fontWeight: 'bold' },
        },
        label: {
          fontSize: 10,
          color: '#444',
          position: 'right',
          verticalAlign: 'middle',
          distance: 6,
          formatter: (params: any) => {
            const name = params.name || ''
            return name.length > 12 ? name.substring(0, 11) + '…' : name
          },
        },
        leaves: {
          label: {
            fontSize: 9,
            color: '#777',
            distance: 4,
          },
        },
        lineStyle: {
          color: '#c0c8d4',
          width: 1.2,
          curveness: 0.5,
        },
        itemStyle: {
          color: '#DBA878',
          borderColor: '#DBA878',
          borderWidth: 1,
        },
        expandAndCollapse: true,
        animationDuration: 400,
      },
    ],
  }
  chartInstance.setOption(option)
}

watch(
  [treeData, expanded, chartRef],
  () => {
    if (expanded.value && treeData.value) {
      nextTick(() => {
        initChart()
      })
    }
  },
  { immediate: true },
)

function handleResize() {
  chartInstance?.resize()
}

watch(expanded, (val) => {
  if (val && treeData.value) {
    nextTick(() => initChart())
  }
})

if (typeof window !== 'undefined') {
  window.addEventListener('resize', handleResize)
}

onUnmounted(() => {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', handleResize)
  }
})

const isHtmlCode = computed(() =>
  ['html', 'htm'].includes((data.value.language || '').toLowerCase()) && !!data.value.content
)
const hasCodeContent = computed(() => !!data.value.language && (!!data.value.content || isStreamingCode.value))
const previewVisible = ref(true)
const iframeHeight = ref(700)

function onIframeLoad(e: Event) {
  const iframe = e.target as HTMLIFrameElement
  try {
    const h = iframe.contentDocument?.documentElement?.scrollHeight
    if (h && h > 200) iframeHeight.value = h + 20
  } catch {}
}

function toggleExpand() {
  expanded.value = !expanded.value
}

async function saveDraftResource() {
  const draft = draftResource.value
  if (!draft || savingDraft.value) return
  if (!userStore.userId) {
    ElMessage.error('缺少用户 ID，无法保存资源')
    return
  }
  savingDraft.value = true
  saveError.value = ''
  try {
    const resp = await api.post('/resources/save_draft', {
      ...draft,
      user_id: userStore.userId,
    })
    const resource = resp.data?.resource
    savedResourceId.value = resource?.id || null
    if (savedResourceId.value) {
      ;(props.step.data as any).draft_resource = {
        ...draft,
        save_required: false,
        saved_resource_id: savedResourceId.value,
      }
      ElMessage.success('已保存到学习资源')
    } else {
      ElMessage.warning('保存完成，但未返回资源 ID')
    }
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || err?.message || '保存失败'
    ElMessage.error(saveError.value)
  } finally {
    savingDraft.value = false
  }
}
</script>

<template>
  <div class="step-card" :class="{ expanded }">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">{{ displaySkillIcon }}</span>
      <span class="step-title">{{ step.title }}</span>
      <el-tag size="small" :type="step.status === 'completed' ? 'success' : step.status === 'running' ? 'warning' : 'danger'">
        {{ step.status === 'completed' ? '完成' : step.status === 'running' ? '执行中...' : '错误' }}
      </el-tag>
      <span class="step-arrow">{{ expanded ? '▾' : '▸' }}</span>
    </div>
    <div v-show="expanded" class="step-content">
      <div class="skill-badge">
        <span class="badge-icon">{{ displaySkillIcon }}</span>
        <span class="badge-name">{{ displaySkillName }}</span>
      </div>

      <div v-if="hasProgress" class="skill-progress">
        <div class="progress-head">
          <span class="progress-phase">{{ currentPhase }}</span>
          <span class="progress-percent">{{ progressLabel }}</span>
        </div>
        <el-progress
          :percentage="Math.round(progressValue)"
          :stroke-width="8"
          :show-text="false"
          :status="progressStatus()"
          :indeterminate="isProgressIndeterminate"
          striped
          striped-flow
        />
        <div v-if="progressNote" class="progress-note">{{ progressNote }}</div>
      </div>

      <!-- 子步骤列表 -->
      <div v-if="data.sub_steps && data.sub_steps.length > 0" class="sub-steps">
        <div
          v-for="(sub, i) in data.sub_steps"
          :key="i"
          class="sub-step-item"
          :class="{
            'sub-step-running': sub.startsWith('⏳'),
            'sub-step-success': sub.startsWith('✅'),
            'sub-step-error': sub.startsWith('❌'),
            'sub-step-warn': sub.startsWith('⚠️'),
          }"
        >{{ sub }}</div>
      </div>

      <!-- 视频卡片列表 -->
      <div v-if="videoList.length > 0 && step.status === 'completed'" class="skill-content">
        <div class="video-grid">
          <a
            v-for="(video, i) in videoList"
            :key="i"
            :href="video.url"
            class="video-card"
          >
            <div class="video-cover">
              <img v-if="video.cover" :src="video.cover" :alt="video.title" loading="lazy" referrerpolicy="no-referrer" />
              <div v-else class="cover-placeholder">
                <span>🎬</span>
              </div>
              <span v-if="video.duration" class="video-duration">{{ video.duration }}</span>
            </div>
            <div class="video-info">
              <div class="video-title" :title="video.title">{{ video.title }}</div>
              <div class="video-meta">
                <span v-if="video.author" class="meta-author">{{ video.author }}</span>
                <span v-if="video.play_count" class="meta-play">▶ {{ video.play_count }}</span>
                <span v-if="video.danmaku" class="meta-danmaku">💬 {{ video.danmaku }}</span>
              </div>
            </div>
          </a>
        </div>
      </div>

      <!-- PPT 课件预览 -->
      <div v-else-if="pptData && step.status === 'completed'" class="skill-content">
        <div class="ppt-preview">
          <div class="ppt-toolbar">
            <span class="ppt-page-title">{{ pptData.title }}</span>
            <span class="ppt-page-count">{{ pptCurrentSlide + 1 }} / {{ pptData.slides.length }}</span>
            <a
              v-if="pptData.pptx_url"
              :href="pptUrl()"
              class="ppt-download-btn"
              download
            >
              下载 .pptx
            </a>
          </div>
          <div class="ppt-slide-area">
            <div class="ppt-slide-inner">
              <h4 class="ppt-slide-title">
                {{ pptData.slides[pptCurrentSlide]?.title }}
              </h4>
              <ul class="ppt-slide-points">
                <li v-for="(point, i) in pptData.slides[pptCurrentSlide]?.content || []" :key="i">
                  {{ point }}
                </li>
              </ul>
            </div>
          </div>
          <div class="ppt-nav">
            <el-button size="small" :disabled="pptCurrentSlide === 0" @click="pptPrev">上一页</el-button>
            <el-button size="small" type="primary" :disabled="pptCurrentSlide >= pptData.slides.length - 1" @click="pptNext">下一页</el-button>
          </div>
        </div>
      </div>

      <!-- AiPPT 分步会话入口 -->
      <div v-else-if="pptSessionPayload && step.status === 'completed'" class="skill-content">
        <div class="ppt-session-card">
          <div class="ppt-session-main">
            <div class="ppt-session-title">{{ pptSessionPayload.title || 'PPT课件' }}</div>
            <div class="ppt-session-desc">
              {{ pptSessionPayload.message || '请进入 AiPPT 分步工作台确认大纲和模板。' }}
            </div>
            <div class="ppt-session-tags">
              <span v-if="pptSessionPayload.ppt_session?.pending_binding">待配置绑定</span>
              <span v-else-if="pptSessionPayload.ppt_session?.scope === 'extension'">拓展课件</span>
              <span v-else>图谱绑定课件</span>
              <span v-if="pptSessionPayload.ppt_session?.course_name">{{ pptSessionPayload.ppt_session.course_name }}</span>
              <span v-for="kp in pptSessionPayload.ppt_session?.knowledge_points || []" :key="kp">{{ kp }}</span>
            </div>
          </div>
          <a class="ppt-session-action" :href="pptSessionHref">
            进入 AiPPT 分步流程
          </a>
        </div>
      </div>

      <!-- 径向树图（思维导图可视化） -->
      <div v-else-if="treeData && step.status === 'completed'" class="skill-content">
        <div ref="chartRef" class="mindmap-chart"></div>
      </div>

      <!-- 代码块展示 -->
      <div v-else-if="hasCodeContent" class="skill-content">
        <div class="code-toolbar">
          <span class="code-lang-tag">{{ data.language }}</span>
          <span v-if="isStreamingCode" class="streaming-code-label">AI 正在输出代码...</span>
          <button v-else-if="isHtmlCode" class="preview-btn" @click.stop="previewVisible = !previewVisible">
            {{ previewVisible ? '显示代码' : '运行预览' }}
          </button>
        </div>
        <iframe v-if="step.status === 'completed' && isHtmlCode && previewVisible" :srcdoc="data.content" sandbox="allow-scripts" class="html-preview" :style="{ height: iframeHeight + 'px' }" @load="onIframeLoad" />
        <pre v-else class="code-block"><code>{{ data.content || '// 正在等待模型输出...' }}</code><span v-if="isStreamingCode" class="code-stream-cursor">▌</span></pre>
      </div>

      <!-- Markdown 渲染内容 -->
      <div v-else-if="renderedContent" class="skill-content">
        <div class="markdown-body" v-html="renderedContent"></div>
      </div>

      <!-- JSON 内容展示 -->
      <div v-else-if="data.content && (data.content.startsWith('{') || data.content.startsWith('[')) && !isRadialTree && !isVideoCards && !isPptSession" class="skill-content">
        <pre class="json-block"><code>{{ data.content }}</code></pre>
      </div>

      <!-- 纯文本内容 -->
      <div v-else-if="data.content && !isRadialTree && !isVideoCards" class="skill-content">
        <div class="text-content">{{ data.content }}</div>
      </div>

      <div v-if="draftResource && step.status === 'completed'" class="draft-save-panel">
        <div class="draft-info">
          <div class="draft-title">可保存为学习资源</div>
          <div class="draft-meta">
            <span>{{ draftResourceTypeLabel(draftResource.resource_type) }}</span>
            <span v-if="draftResource.course_name">课程：{{ draftResource.course_name }}</span>
            <span v-if="draftResource.knowledge_points?.length">知识点：{{ draftResource.knowledge_points.join('、') }}</span>
          </div>
        </div>
        <a
          v-if="savedDraftResourceId"
          class="draft-link"
          :href="`/resources?open=${savedDraftResourceId}`"
        >查看资源 →</a>
        <el-button
          v-else
          size="small"
          type="primary"
          :loading="savingDraft"
          @click.stop="saveDraftResource"
        >保存到学习资源</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.step-card { background: #FFFBF5; border-radius: 12px; border: 1px solid #EFE6DC; overflow: hidden; transition: all 0.25s cubic-bezier(.4,0,.2,1); }
.step-card:hover { box-shadow: 0 2px 10px rgba(58,51,46,0.08); transform: translateY(-1px); }
.step-header { display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 8px; user-select: none; transition: background 0.2s; }
.step-header:hover { background: #FFF5EB; }
.step-icon { font-size: 18px; flex-shrink: 0; }
.step-title { flex: 1; font-size: 14px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #3A332E; }
.step-arrow { font-size: 12px; color: #948A80; flex-shrink: 0; }
.step-content { padding: 0 14px 14px; border-top: 1px solid #EFE6DC; }
.skill-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; margin-top: 10px; background: linear-gradient(135deg, #F9D9B8 0%, #E8C29C 100%); border-radius: 20px; font-size: 12px; color: #3A332E; }
.badge-icon { font-size: 14px; }
.badge-name { font-weight: 500; }
.skill-progress {
  margin-top: 10px;
  padding: 10px 12px;
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 10px;
}
.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.progress-phase {
  font-size: 13px;
  font-weight: 600;
  color: #3A332E;
}
.progress-percent {
  font-family: var(--font-mono);
  font-size: 12px;
  color: #7C5C3C;
}
.progress-note {
  margin-top: 6px;
  font-size: 12px;
  color: #948A80;
  line-height: 1.5;
}
.sub-steps { margin-top: 10px; padding: 8px 12px; background: #FFF5EB; border-radius: 8px; border: 1px solid #EFE6DC; }
.sub-step-item { font-size: 13px; color: #6B635C; line-height: 1.8; padding: 2px 0; }
.sub-step-running { color: #FBCFA8; font-style: italic; }
.sub-step-success { color: #98C9B3; }
.sub-step-error { color: #F2B8A2; }
.sub-step-warn { color: #FBCFA8; }
.skill-content { margin-top: 10px; }
.video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.video-card { display: block; background: #FFFBF5; border: 1px solid #EFE6DC; border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; transition: all 0.25s cubic-bezier(.4,0,.2,1); }
.video-card:hover { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(58,51,46,0.12); border-color: #E8C29C; }
.video-cover { position: relative; width: 100%; padding-top: 56.25%; background: #FFF5EB; overflow: hidden; }
.video-cover img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s ease; }
.video-card:hover .video-cover img { transform: scale(1.05); }
.cover-placeholder { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #F9D9B8 0%, #E8C29C 100%); font-size: 36px; }
.video-duration { position: absolute; bottom: 6px; right: 6px; background: rgba(58,51,46,0.75); color: #FFFBF5; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); }
.video-info { padding: 10px 12px 12px; }
.video-title { font-size: 13px; font-weight: 500; line-height: 1.4; color: #3A332E; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; margin-bottom: 8px; }
.video-card:hover .video-title { color: #DBA878; }
.video-meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: #948A80; flex-wrap: wrap; }
.meta-author { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; color: #6B635C; }
.meta-play, .meta-danmaku { white-space: nowrap; }
.mindmap-chart { width: 100%; height: 500px; border: 1px solid #EFE6DC; border-radius: 12px; background: #FFFBF5; }
.text-content { font-size: 13px; line-height: 1.6; color: #6B635C; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; }
.code-block { background: #1e1e2e; color: #cdd6f4; padding: 12px; border-radius: 8px; font-size: 12px; line-height: 1.5; overflow-x: auto; max-height: 400px; overflow-y: auto; }
.code-block code { font-family: var(--font-mono); }
.code-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: #2d2d3f; border-radius: 8px 8px 0 0; }
.code-lang-tag { font-size: 11px; color: #888; }
.streaming-code-label { font-size: 12px; color: #FBCFA8; animation: streamPulse 1.2s ease-in-out infinite; }
.code-stream-cursor { display: inline-block; color: #FBCFA8; animation: streamBlink 0.8s step-end infinite; }
.preview-btn { font-size: 12px; padding: 3px 10px; border: 1px solid #98C9B3; border-radius: 6px; background: transparent; color: #98C9B3; cursor: pointer; transition: all 0.2s; }
.preview-btn:hover { background: #98C9B3; color: #fff; }
.html-preview { width: calc(100% + 28px); margin-left: -14px; min-height: 600px; height: auto; border: none; border-top: 1px solid #EFE6DC; background: #fff; display: block; border-radius: 0 0 8px 8px; }
.json-block { background: #FFF5EB; color: #6B635C; padding: 12px; border-radius: 8px; font-size: 12px; line-height: 1.5; overflow-x: auto; max-height: 400px; overflow-y: auto; border: 1px solid #EFE6DC; font-family: var(--font-mono); }
.json-block code { font-family: var(--font-mono); }
.markdown-body { font-size: 14px; line-height: 1.7; color: #6B635C; max-height: 500px; overflow-y: auto; }
.markdown-body :deep(h1) { font-size: 20px; margin: 16px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #F9D9B8; color: #3A332E; }
.markdown-body :deep(h2) { font-size: 17px; margin: 14px 0 8px; padding-left: 10px; border-left: 3px solid #F9D9B8; color: #3A332E; }
.markdown-body :deep(h3) { font-size: 15px; margin: 10px 0 6px; color: #6B635C; }
.markdown-body :deep(h4) { font-size: 13px; margin: 8px 0 4px; color: #948A80; font-weight: 500; }
.markdown-body :deep(p) { margin: 4px 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 20px; margin: 6px 0; }
.markdown-body :deep(li) { margin: 2px 0; }
.markdown-body :deep(code) { background: #FFF5EB; padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px; }
.markdown-body :deep(pre) { background: #1e1e2e; padding: 12px; border-radius: 8px; overflow-x: auto; }
.markdown-body :deep(pre code) { background: none; color: #cdd6f4; padding: 0; }
.ppt-preview { border: 1px solid #EFE6DC; border-radius: 12px; overflow: hidden; background: #FFFBF5; }
.ppt-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: #FFF5EB; border-bottom: 1px solid #EFE6DC; gap: 12px; }
.ppt-page-title { font-size: 14px; font-weight: 500; color: #3A332E; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ppt-page-count { font-size: 13px; color: #948A80; white-space: nowrap; }
.ppt-download-btn { font-size: 13px; font-weight: 500; color: #DBA878; text-decoration: none; white-space: nowrap; padding: 4px 12px; border: 1px solid #E8C29C; border-radius: 6px; transition: all 0.2s; }
.ppt-download-btn:hover { background: #F9D9B8; color: #3A332E; }
.ppt-slide-area { min-height: 250px; padding: 28px 36px; background: #FFFBF5; }
.ppt-slide-inner { max-width: 800px; }
.ppt-slide-title { font-size: 20px; color: #3A332E; margin: 0 0 20px 0; padding-bottom: 12px; border-bottom: 2px solid #F9D9B8; }
.ppt-slide-points { padding-left: 20px; margin: 0; }
.ppt-slide-points li { margin-bottom: 10px; line-height: 1.7; color: #6B635C; font-size: 15px; }
.ppt-nav { display: flex; justify-content: center; gap: 12px; padding: 12px; border-top: 1px solid #EFE6DC; background: #FFF5EB; }
.ppt-session-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid #E8C29C;
  border-radius: 12px;
  background: #FFF5EB;
}
.ppt-session-main {
  min-width: 0;
}
.ppt-session-title {
  font-size: 14px;
  font-weight: 700;
  color: #3A332E;
}
.ppt-session-desc {
  margin-top: 6px;
  font-size: 13px;
  color: #6B635C;
  line-height: 1.6;
}
.ppt-session-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.ppt-session-tags span {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 8px;
  border: 1px solid #E8C29C;
  border-radius: 999px;
  color: #8A5A28;
  background: #FFFBF5;
  font-size: 12px;
}
.ppt-session-action {
  flex-shrink: 0;
  padding: 7px 12px;
  border-radius: 8px;
  background: #DBA878;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}
.ppt-session-action:hover {
  background: #C98F5A;
}
.draft-save-panel {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #E8C29C;
  border-radius: 10px;
  background: #FFF5EB;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.draft-info { min-width: 0; }
.draft-title { font-size: 13px; font-weight: 600; color: #3A332E; }
.draft-meta { margin-top: 3px; display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #948A80; }
.draft-link { color: #409EFF; font-size: 13px; font-weight: 600; text-decoration: none; white-space: nowrap; }
.draft-link:hover { text-decoration: underline; }
@media (max-width: 600px) { .video-grid { grid-template-columns: 1fr; } }
@keyframes streamBlink { 50% { opacity: 0; } }
@keyframes streamPulse { 0%, 100% { opacity: 0.55; } 50% { opacity: 1; } }
</style>
