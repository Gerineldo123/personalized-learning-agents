<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

interface Slide {
  title: string
  content: string[]
  notes?: string
}

const props = defineProps<{
  content: { title?: string; slides?: Slide[]; _pptx_path?: string; _slide_html?: string[] }
  resourceId?: number
  userId?: string | null
}>()

const currentSlide = ref(0)
const previewRef = ref<HTMLIFrameElement | null>(null)

const slides = computed(() => props.content._slide_html || [])
const totalSlides = computed(() => slides.value.length)

function prev() {
  if (currentSlide.value > 0) currentSlide.value--
}

function next() {
  if (currentSlide.value < totalSlides.value - 1) currentSlide.value++
}

function updateIframe() {
  const iframe = previewRef.value
  if (!iframe || !slides.value[currentSlide.value]) return
  const doc = iframe.contentDocument || iframe.contentWindow?.document
  if (doc) {
    doc.open()
    doc.write(slides.value[currentSlide.value])
    doc.close()
  }
}

watch(currentSlide, () => nextTick(updateIframe), { immediate: false })

const pptDownloadUrl = computed(() => {
  if (props.content._pptx_path && props.resourceId && props.userId) {
    return `/api/resources/${props.resourceId}/download?user_id=${props.userId}`
  }
  return null
})
</script>

<template>
  <div class="ppt-viewer">
    <div class="ppt-header">
      <h3>{{ content.title || '课件' }}</h3>
      <div class="ppt-header-right">
        <span class="slide-count">{{ currentSlide + 1 }} / {{ totalSlides }}</span>
        <a v-if="pptDownloadUrl" :href="pptDownloadUrl" class="ppt-download-btn">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          下载 PPT
        </a>
      </div>
    </div>

    <div class="slide-area">
      <div v-if="slides.length > 0" class="slide-frame-wrapper">
        <iframe
          ref="previewRef"
          class="slide-iframe"
          sandbox="allow-same-origin"
          title="Slide Preview"
          @load="updateIframe"
        />
      </div>

      <!-- fallback when no _slide_html available (old PPT resources) -->
      <div v-else-if="content.slides?.length" class="slide-content">
        <h4 class="slide-title">{{ content.slides[currentSlide]?.title }}</h4>
        <ul class="slide-points">
          <li v-for="(point, i) in content.slides[currentSlide]?.content || []" :key="i">{{ point }}</li>
        </ul>
        <div v-if="content.slides[currentSlide]?.notes" class="slide-notes">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#409eff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          {{ content.slides[currentSlide]?.notes }}
        </div>
      </div>

      <el-empty v-else description="暂无内容" />
    </div>

    <div class="ppt-controls">
      <el-button :disabled="currentSlide === 0" @click="prev">上一页</el-button>
      <el-button type="primary" :disabled="currentSlide >= totalSlides - 1" @click="next">下一页</el-button>
    </div>
  </div>
</template>

<style scoped>
.ppt-viewer {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}

.ppt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}

.ppt-header h3 { margin: 0; color: #303133; }

.ppt-header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.slide-count { font-size: 14px; color: #909399; }

.ppt-download-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 14px; background: #409eff; color: #fff;
  border-radius: 4px; text-decoration: none; font-size: 13px;
  transition: background 0.2s;
}
.ppt-download-btn:hover { background: #337ecc; }

.slide-area { padding: 0; }

.slide-frame-wrapper {
  width: 100%; aspect-ratio: 16 / 9; overflow: hidden;
}

.slide-iframe {
  width: 100%; height: 100%; border: none;
  display: block; transform-origin: top left;
}

/* fallback plain rendering for old PPT resources */
.slide-content { padding: 32px 40px; min-height: 300px; }
.slide-title { font-size: 20px; color: #303133; margin-bottom: 24px; }
.slide-points { padding-left: 20px; }
.slide-points li { margin-bottom: 12px; line-height: 1.8; color: #606266; }
.slide-notes {
  margin-top: 24px; padding: 12px 16px; background: #ecf5ff;
  border-left: 3px solid #409eff; color: #606266; font-size: 13px;
  display: flex; align-items: flex-start; gap: 6px;
}

.ppt-controls {
  display: flex; justify-content: center; gap: 16px;
  padding: 16px; border-top: 1px solid #ebeef5;
}
</style>
