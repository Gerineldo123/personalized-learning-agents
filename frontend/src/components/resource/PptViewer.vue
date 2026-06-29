<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled, Refresh } from '@element-plus/icons-vue'
import api from '../../api'

interface Slide {
  title: string
  content: string[]
  notes?: string
}

interface PptPreview {
  status?: 'idle' | 'pending' | 'ready' | 'failed' | string
  images?: string[]
  total?: number
  mode?: string
  warning?: string | null
  error?: string | null
  generated_at?: string | null
}

interface PptContent {
  title?: string
  slides?: Slide[]
  pptx_file?: string
  pptx_url?: string
  preview?: PptPreview
}

const props = defineProps<{
  content: PptContent
  resourceId?: number
  userId?: string
}>()

const emit = defineEmits<{
  (event: 'updated', content: PptContent): void
}>()

const currentSlide = ref(0)
const preview = ref<PptPreview>(props.content.preview || {})
const loadingPreview = ref(false)
let pollTimer: ReturnType<typeof window.setInterval> | null = null
let pollCount = 0

const downloadUrl = computed(() => {
  const file = props.content.pptx_file || props.content.pptx_url || ''
  if (!file) return ''
  if (file.startsWith('/static/') || file.startsWith('http')) return file
  return `/static/ppt/${file}`
})

const previewImages = computed(() => (preview.value.images || []).filter(Boolean))
const hasImagePreview = computed(() => preview.value.status === 'ready' && previewImages.value.length > 0)
const previewStatus = computed(() => preview.value.status || 'idle')
const currentImageUrl = computed(() => {
  if (!hasImagePreview.value) return ''
  return fullStaticUrl(previewImages.value[currentSlide.value] || previewImages.value[0])
})
const fallbackSlide = computed(() => props.content.slides?.[currentSlide.value])
const fallbackSlideCount = computed(() => props.content.slides?.length || 0)
const displayTotal = computed(() => hasImagePreview.value ? previewImages.value.length : fallbackSlideCount.value)
const lowFidelityWarning = computed(() => {
  if (preview.value.mode !== 'python_low_fidelity') return ''
  return preview.value.warning || '当前为低保真预览，完整样式请下载 PPTX 查看'
})
const fallbackErrorNotice = computed(() => {
  if (previewStatus.value !== 'failed' || !fallbackSlide.value) return ''
  return preview.value.error || 'PPT 图片预览生成失败，当前显示结构化内容。'
})

watch(() => props.content.preview, (next) => {
  preview.value = next || {}
  clampSlide()
}, { deep: true })

watch(() => props.resourceId, () => {
  currentSlide.value = 0
  preview.value = props.content.preview || {}
  initPreview()
})

function prev() {
  if (currentSlide.value > 0) currentSlide.value--
}

function next() {
  const total = displayTotal.value
  if (currentSlide.value < total - 1) currentSlide.value++
}

function jump(index: number) {
  currentSlide.value = index
}

function clampSlide() {
  const total = displayTotal.value
  if (total <= 0) {
    currentSlide.value = 0
  } else if (currentSlide.value >= total) {
    currentSlide.value = total - 1
  }
}

function fullStaticUrl(url: string): string {
  if (!url) return ''
  if (url.startsWith('http')) return url
  if (url.startsWith('/static/') && window.location.port === '3000') {
    return `${window.location.protocol}//${window.location.hostname}:18000${url}`
  }
  return `${window.location.protocol}//${window.location.host}${url}`
}

function fullDownloadUrl(): string {
  return fullStaticUrl(downloadUrl.value)
}

function updatePreview(nextPreview: PptPreview) {
  preview.value = nextPreview || {}
  emit('updated', { ...props.content, preview: preview.value })
  clampSlide()
}

async function fetchPreviewStatus() {
  if (!props.resourceId) return
  const r = await api.get(`/resources/${props.resourceId}/ppt_preview`, {
    params: props.userId ? { user_id: props.userId } : {},
  })
  updatePreview(r.data.preview || {})
  if (preview.value.status !== 'pending') stopPolling()
}

async function requestPreview(force = true) {
  if (!props.resourceId || !downloadUrl.value) return
  loadingPreview.value = true
  try {
    const r = await api.post(`/resources/${props.resourceId}/ppt_preview`, null, {
      params: {
        ...(props.userId ? { user_id: props.userId } : {}),
        force,
      },
    })
    updatePreview(r.data.preview || { status: 'pending', images: [], total: 0 })
    startPolling()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'PPT 预览生成失败')
  } finally {
    loadingPreview.value = false
  }
}

function startPolling() {
  stopPolling()
  pollCount = 0
  pollTimer = window.setInterval(async () => {
    pollCount += 1
    try {
      await fetchPreviewStatus()
    } catch {
      if (pollCount >= 3) stopPolling()
    }
    if (pollCount >= 80) stopPolling()
  }, 2500)
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

function initPreview() {
  stopPolling()
  if (!props.resourceId || !downloadUrl.value) return
  if (preview.value.status === 'pending') {
    startPolling()
    return
  }
  if (!preview.value.status || preview.value.status === 'idle') {
    requestPreview(false)
  } else {
    fetchPreviewStatus().catch(() => {})
  }
}

onMounted(initPreview)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="ppt-viewer">
    <div class="ppt-header">
      <div>
        <h3>{{ content.title || '课件' }}</h3>
        <p v-if="preview.generated_at" class="preview-meta">预览生成时间：{{ preview.generated_at }}</p>
      </div>
      <div class="ppt-header-right">
        <span v-if="displayTotal" class="slide-count">{{ currentSlide + 1 }} / {{ displayTotal }}</span>
        <el-button
          v-if="downloadUrl && (previewStatus === 'failed' || previewStatus === 'idle')"
          size="small"
          :icon="Refresh"
          :loading="loadingPreview"
          @click="requestPreview(true)"
        >
          {{ previewStatus === 'failed' ? '重新生成预览' : '生成预览' }}
        </el-button>
        <a v-if="downloadUrl" :href="fullDownloadUrl()" class="download-btn" download>
          下载PPT
        </a>
      </div>
    </div>

    <div v-if="lowFidelityWarning" class="preview-warning">
      {{ lowFidelityWarning }}
    </div>
    <div v-if="fallbackErrorNotice" class="preview-warning error">
      {{ fallbackErrorNotice }}
    </div>

    <div v-if="hasImagePreview" class="preview-layout">
      <div class="slide-image-wrap">
        <img :src="currentImageUrl" class="slide-image" alt="PPT预览页" />
      </div>
      <div class="thumbnail-list">
        <button
          v-for="(image, index) in previewImages"
          :key="image"
          class="thumbnail"
          :class="{ active: index === currentSlide }"
          @click="jump(index)"
        >
          <img :src="fullStaticUrl(image)" :alt="`第${index + 1}页`" />
          <span>{{ index + 1 }}</span>
        </button>
      </div>
    </div>

    <div v-else-if="previewStatus === 'pending'" class="preview-state">
      <el-icon class="state-icon"><Refresh /></el-icon>
      <h4>预览生成中</h4>
      <p>系统正在把 PPTX 转换为逐页图片，完成后会自动显示。</p>
    </div>

    <div v-else-if="!downloadUrl" class="preview-state">
      <el-icon class="state-icon"><InfoFilled /></el-icon>
      <h4>暂无可预览文件</h4>
      <p>当前资源没有关联 PPTX 文件。</p>
    </div>

    <div v-else-if="fallbackSlide" class="slide-area">
      <div class="slide-content">
        <h4 class="slide-title">{{ fallbackSlide.title }}</h4>
        <ul class="slide-points">
          <li v-for="(point, i) in fallbackSlide.content" :key="i">{{ point }}</li>
        </ul>
        <div v-if="fallbackSlide.notes" class="slide-notes">
          <el-icon><InfoFilled /></el-icon> {{ fallbackSlide.notes }}
        </div>
      </div>
    </div>

    <div v-else-if="previewStatus === 'failed'" class="preview-state error">
      <el-icon class="state-icon"><InfoFilled /></el-icon>
      <h4>预览生成失败</h4>
      <p>{{ preview.error || 'PPT 图片预览生成失败，请下载 PPTX 查看完整内容。' }}</p>
    </div>

    <div v-else class="preview-state">
      <el-icon class="state-icon"><InfoFilled /></el-icon>
      <h4>尚未生成预览</h4>
      <p>点击“生成预览”后，系统会将 PPTX 转换为逐页图片。</p>
    </div>

    <div v-if="displayTotal > 1" class="ppt-controls">
      <el-button :disabled="currentSlide === 0" @click="prev">上一页</el-button>
      <el-button type="primary" :disabled="currentSlide >= displayTotal - 1" @click="next">下一页</el-button>
    </div>
  </div>
</template>

<style scoped>
.ppt-viewer {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
  overflow: hidden;
}

.ppt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: var(--bg-overlay);
  border-bottom: 1px solid var(--border-light);
}

.ppt-header h3 {
  margin: 0;
}

.preview-meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.ppt-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.slide-count {
  font-size: 14px;
  color: var(--text-secondary);
}

.download-btn {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-success);
  text-decoration: none;
  padding: 5px 14px;
  border: 1px solid var(--color-success);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.download-btn:hover {
  background: var(--color-success);
  color: #fff;
}

.preview-layout {
  padding: 20px;
}

.preview-warning {
  margin: 14px 20px 0;
  padding: 10px 12px;
  border: 1px solid #f3d38c;
  border-radius: 8px;
  background: #fff7df;
  color: #8a5c00;
  font-size: 13px;
}

.preview-warning.error {
  border-color: #f0b8b8;
  background: #fff1f1;
  color: #b34545;
}

.slide-image-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  background: #2b2b2b;
  border-radius: 12px;
  min-height: 360px;
  overflow: hidden;
}

.slide-image {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  background: #fff;
}

.thumbnail-list {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 14px 2px 2px;
}

.thumbnail {
  position: relative;
  flex: 0 0 112px;
  height: 72px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  cursor: pointer;
}

.thumbnail.active {
  border-color: var(--color-primary);
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail span {
  position: absolute;
  right: 4px;
  bottom: 4px;
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.62);
  color: #fff;
  font-size: 11px;
}

.preview-state {
  min-height: 300px;
  padding: 48px 24px;
  text-align: center;
  color: var(--text-secondary);
}

.preview-state h4 {
  margin: 12px 0 8px;
  color: var(--text-primary);
}

.preview-state p {
  margin: 0;
}

.preview-state.error p {
  color: var(--color-danger);
}

.state-icon {
  font-size: 28px;
  color: var(--color-primary);
}

.slide-area {
  min-height: 300px;
  padding: 32px 40px;
}

.slide-title {
  font-size: 20px;
  color: var(--text-primary);
  margin-bottom: 24px;
  font-weight: 700;
}

.slide-points {
  padding-left: 20px;
}

.slide-points li {
  margin-bottom: 12px;
  line-height: 1.8;
  color: var(--text-regular);
}

.slide-notes {
  margin-top: 24px;
  padding: 12px 16px;
  background: var(--color-primary-bg);
  border-left: 3px solid var(--color-primary);
  color: var(--text-regular);
  font-size: 13px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.ppt-controls {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 16px;
  border-top: 1px solid var(--border-light);
}
</style>
