<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Close, FullScreen, ScaleToOriginal } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  html: string
  title?: string
  description?: string
  compact?: boolean
}>(), {
  title: '动画预览',
  description: '',
  compact: false,
})

const channelId = `zhitu-animation-${Math.random().toString(36).slice(2)}`
const inlineFrame = ref<HTMLIFrameElement | null>(null)
const fullscreenFrame = ref<HTMLIFrameElement | null>(null)
const inlineHeight = ref(760)
const fullscreenHeight = ref(760)
const fitToViewport = ref(true)
const fullscreen = ref(false)
const viewportHeight = ref(typeof window === 'undefined' ? 900 : window.innerHeight)
let previousBodyOverflow = ''

const instrumentedHtml = computed(() => {
  const bridge = `
<style id="zhitu-animation-host-style">
  html, body { max-width: 100% !important; overflow-x: hidden !important; }
</style>
<script id="zhitu-animation-size-bridge">
(() => {
  const channelId = ${JSON.stringify(channelId)};
  let scheduled = false;
  const report = () => {
    scheduled = false;
    const doc = document.documentElement;
    const body = document.body;
    const height = Math.max(
      doc ? doc.scrollHeight : 0,
      doc ? doc.offsetHeight : 0,
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      320
    );
    parent.postMessage({ type: 'zhitu-animation-size', channelId, height: Math.ceil(height) }, '*');
  };
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(report);
  };
  addEventListener('load', schedule);
  addEventListener('resize', schedule);
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(schedule);
    if (document.documentElement) observer.observe(document.documentElement);
    if (document.body) observer.observe(document.body);
  }
  [0, 80, 250, 800, 1600].forEach(delay => setTimeout(schedule, delay));
})();
<\/script>`
  const html = props.html || ''
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, `${bridge}</body>`)
  return `${html}${bridge}`
})

const inlineAvailableHeight = computed(() => Math.max(500, Math.min(900, viewportHeight.value - (props.compact ? 190 : 250))))
const fullscreenAvailableHeight = computed(() => Math.max(520, viewportHeight.value - 64))
const inlineScale = computed(() => fitScale(inlineHeight.value, inlineAvailableHeight.value))
const fullscreenScale = computed(() => fitScale(fullscreenHeight.value, fullscreenAvailableHeight.value))
const inlineStageHeight = computed(() => Math.ceil(inlineHeight.value * inlineScale.value))
const fullscreenStageHeight = computed(() => Math.ceil(fullscreenHeight.value * fullscreenScale.value))

function fitScale(contentHeight: number, availableHeight: number) {
  if (!fitToViewport.value || contentHeight <= availableHeight) return 1
  return availableHeight / contentHeight
}

function frameStyle(height: number, scale: number) {
  return {
    height: `${height}px`,
    transform: `scale(${scale})`,
  }
}

function handleMessage(event: MessageEvent) {
  const payload = event.data
  if (!payload || payload.type !== 'zhitu-animation-size' || payload.channelId !== channelId) return
  const nextHeight = Math.max(320, Math.min(Number(payload.height) || 0, 6000))
  if (event.source === inlineFrame.value?.contentWindow) inlineHeight.value = nextHeight
  if (event.source === fullscreenFrame.value?.contentWindow) fullscreenHeight.value = nextHeight
}

function handleResize() {
  viewportHeight.value = window.innerHeight
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && fullscreen.value) fullscreen.value = false
}

watch(() => props.html, () => {
  inlineHeight.value = 760
  fullscreenHeight.value = 760
})

watch(fullscreen, (visible) => {
  if (typeof document === 'undefined') return
  if (visible) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = previousBodyOverflow
  }
})

onMounted(() => {
  window.addEventListener('message', handleMessage)
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', handleMessage)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', handleKeydown)
  if (typeof document !== 'undefined') document.body.style.overflow = previousBodyOverflow
})
</script>

<template>
  <section class="animation-viewer" :class="{ compact }">
    <header class="animation-toolbar">
      <div class="animation-heading">
        <strong>{{ title }}</strong>
        <p v-if="description">{{ description }}</p>
      </div>
      <div class="animation-actions">
        <el-tooltip :content="fitToViewport ? '按原始尺寸显示' : '适应窗口'" placement="top">
          <button
            class="icon-action"
            :class="{ active: fitToViewport }"
            type="button"
            :aria-label="fitToViewport ? '按原始尺寸显示' : '适应窗口'"
            @click="fitToViewport = !fitToViewport"
          >
            <el-icon><ScaleToOriginal /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="全屏查看" placement="top">
          <button class="icon-action" type="button" aria-label="全屏查看" @click="fullscreen = true">
            <el-icon><FullScreen /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </header>

    <div v-if="html" class="animation-stage" :style="{ height: inlineStageHeight + 'px' }">
      <iframe
        ref="inlineFrame"
        :srcdoc="instrumentedHtml"
        sandbox="allow-scripts"
        class="animation-frame"
        :style="frameStyle(inlineHeight, inlineScale)"
        title="动画预览"
      />
    </div>
    <div v-else class="animation-empty">该动画缺少可预览的 HTML 内容。</div>

    <Teleport to="body">
      <div v-if="fullscreen" class="animation-fullscreen" role="dialog" aria-modal="true">
        <div class="fullscreen-toolbar">
          <strong>{{ title }}</strong>
          <div class="animation-actions">
            <el-tooltip :content="fitToViewport ? '按原始尺寸显示' : '适应窗口'" placement="bottom">
              <button
                class="icon-action"
                :class="{ active: fitToViewport }"
                type="button"
                :aria-label="fitToViewport ? '按原始尺寸显示' : '适应窗口'"
                @click="fitToViewport = !fitToViewport"
              >
                <el-icon><ScaleToOriginal /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="退出全屏" placement="bottom">
              <button class="icon-action" type="button" aria-label="退出全屏" @click="fullscreen = false">
                <el-icon><Close /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
        <div class="fullscreen-scroll">
          <div class="fullscreen-stage" :style="{ height: fullscreenStageHeight + 'px' }">
            <iframe
              ref="fullscreenFrame"
              :srcdoc="instrumentedHtml"
              sandbox="allow-scripts"
              class="animation-frame"
              :style="frameStyle(fullscreenHeight, fullscreenScale)"
              title="全屏动画预览"
            />
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.animation-viewer {
  overflow: hidden;
  border: 1px solid #efe6dc;
  border-radius: 8px;
  background: #fffbf5;
}
.animation-toolbar,
.fullscreen-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 58px;
  padding: 10px 14px;
  border-bottom: 1px solid #efe6dc;
  background: #fff8ef;
}
.animation-heading { min-width: 0; }
.animation-heading strong,
.fullscreen-toolbar strong { color: #3a332e; font-size: 14px; }
.animation-heading p { margin: 3px 0 0; color: #7a6a5c; font-size: 12px; }
.animation-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.icon-action {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid #e8c29c;
  border-radius: 7px;
  background: #fffbf5;
  color: #7c5c3c;
  cursor: pointer;
  transition: background 0.18s, color 0.18s, border-color 0.18s;
}
.icon-action:hover,
.icon-action.active { border-color: #dba878; background: #f9d9b8; color: #3a332e; }
.animation-stage,
.fullscreen-stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  background: #f7f8fb;
  transition: height 0.2s ease;
}
.animation-frame {
  position: absolute;
  inset: 0 auto auto 0;
  display: block;
  width: 100%;
  border: 0;
  background: #fff;
  transform-origin: top center;
  transition: transform 0.2s ease;
}
.animation-empty { padding: 48px 20px; text-align: center; color: #948a80; }
.animation-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  background: #f7f8fb;
}
.fullscreen-toolbar { flex: 0 0 58px; background: #fffbf5; }
.fullscreen-scroll { flex: 1; min-height: 0; overflow: auto; }
.fullscreen-stage { min-height: 100%; }
.compact .animation-toolbar { min-height: 50px; padding: 8px 12px; }

@media (max-width: 640px) {
  .animation-toolbar { align-items: flex-start; }
  .animation-heading p { display: none; }
  .icon-action { width: 32px; height: 32px; }
}
</style>
