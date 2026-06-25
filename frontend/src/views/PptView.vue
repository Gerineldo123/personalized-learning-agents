<script setup lang="ts">
import { computed, nextTick, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useUserStore } from '../stores/user'
import { createPptSession, completePptSession, oneClickGeneratePpt } from '../api/ppt'
import type { PptResource } from '../api/ppt'

const router = useRouter()

const userStore = useUserStore()

const pptConfigured = ref(false)
const loadingConfig = ref(true)
const loadingSession = ref(false)
const loadingOneClick = ref(false)
const topic = ref('')
const courseName = ref('')
const knowledgePoints = ref<string[]>([])
const curriculumCourses = ref<any[]>([])
const kpOptions = ref<any[]>([])
const profile = ref<any>(null)

const sessionId = ref('')
const docmeeToken = ref('')
const docmeeDomain = ref('')
const docmeeSdkUrl = ref('')
const docmeeContainer = ref<HTMLElement | null>(null)
const docmeeInstance = ref<any>(null)
const iframeLoading = ref(false)
const iframeVisible = ref(false)
const completionSubmitted = ref(false)

const resultResource = ref<PptResource | null>(null)
const showResult = ref(false)

declare global {
  interface Window {
    DocmeeUI?: any
    __docmeeSdkLoading?: Promise<void>
  }
}

function loadDocmeeSdk(scriptUrl: string): Promise<void> {
  if (window.DocmeeUI) return Promise.resolve()
  if (window.__docmeeSdkLoading) return window.__docmeeSdkLoading

  window.__docmeeSdkLoading = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-docmee-sdk="true"]')
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('文多多 AiPPT SDK 加载失败')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = scriptUrl
    script.async = true
    script.dataset.docmeeSdk = 'true'
    script.onload = () => {
      if (window.DocmeeUI) resolve()
      else reject(new Error('文多多 AiPPT SDK 未正确初始化'))
    }
    script.onerror = () => reject(new Error('文多多 AiPPT SDK 加载失败'))
    document.head.appendChild(script)
  })

  return window.__docmeeSdkLoading
}

function destroyDocmeeUI() {
  const instance = docmeeInstance.value
  if (instance?.destroy) instance.destroy()
  else if (instance?.close) instance.close()
  docmeeInstance.value = null
}

async function checkConfig() {
  loadingConfig.value = true
  try {
    const r = await api.get('/config/ppt')
    pptConfigured.value = !!r.data.has_key && r.data.is_docmee !== false
  } catch {
    pptConfigured.value = false
  } finally {
    loadingConfig.value = false
  }
}

async function loadCurriculumCourses() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/curriculum/graph', {
      params: { user_id: userStore.userId, major: profile.value?.major || '' },
    })
    curriculumCourses.value = r.data?.nodes || []
  } catch {
    curriculumCourses.value = []
  }
}

async function loadProfile() {
  if (!userStore.userId) return
  try {
    const r = await api.get('/profile', { params: { user_id: userStore.userId } })
    if (r.data?.found) profile.value = r.data.profile
  } catch {
    profile.value = null
  }
}

async function fetchCourseKps(course: string) {
  if (!course) return []
  try {
    const r = await api.get(`/curriculum/kp/${encodeURIComponent(course)}`)
    return r.data?.nodes || []
  } catch {
    return []
  }
}

async function onCourseChange() {
  knowledgePoints.value = []
  kpOptions.value = await fetchCourseKps(courseName.value)
}

const canGenerate = computed(() =>
  !!userStore.userId
  && !!topic.value.trim()
  && !!courseName.value
  && knowledgePoints.value.length > 0
)

function validatePptForm(): boolean {
  if (!userStore.userId) {
    ElMessage.warning('请先登录')
    return false
  }
  if (!topic.value.trim()) {
    ElMessage.warning('请输入 PPT 主题')
    return false
  }
  if (!courseName.value) {
    ElMessage.warning('请选择课程节点')
    return false
  }
  if (knowledgePoints.value.length === 0) {
    ElMessage.warning('请选择至少一个知识点节点')
    return false
  }
  return true
}

async function handleCompletion(pptId: string, subject: string, coverUrl: string, templateId: string) {
  completionSubmitted.value = true
  iframeLoading.value = true
  try {
    const result = await completePptSession(sessionId.value, {
      user_id: userStore.userId,
      ppt_id: pptId,
      subject: subject || topic.value,
      cover_url: coverUrl || undefined,
      template_id: templateId || undefined,
    })
    if (result.ok && result.resource) {
      resultResource.value = result.resource
      showResult.value = true
      ElMessage.success('PPT 已生成并保存到学习资源库')
    }
  } catch (e: any) {
    completionSubmitted.value = false
    const msg = e?.response?.data?.detail || e?.message || '保存 PPT 失败'
    ElMessage.error(msg)
  } finally {
    iframeLoading.value = false
    iframeVisible.value = false
  }
}

function extractPptInfo(payload: any) {
  const data = payload?.data || payload || {}
  const ppt = data.pptInfo || data.ppt || data
  return {
    pptId: ppt.id || ppt.pptId || ppt.ppt_id,
    subject: ppt.subject || ppt.name || ppt.title || topic.value || '',
    coverUrl: ppt.coverUrl || ppt.cover_url || '',
    templateId: ppt.templateId || ppt.template_id || '',
  }
}

function bindDocmeeEvents(instance: any) {
  if (!instance?.on) return
  instance.on('afterGenerate', (payload: any) => {
    const info = extractPptInfo(payload)
    if (info.pptId && !completionSubmitted.value) {
      handleCompletion(info.pptId, info.subject, info.coverUrl, info.templateId)
    }
  })
  instance.on('manuallySavePPT', (payload: any) => {
    const info = extractPptInfo(payload)
    if (info.pptId && !completionSubmitted.value) {
      handleCompletion(info.pptId, info.subject, info.coverUrl, info.templateId)
    }
  })
  instance.on('automaticSavePPT', (payload: any) => {
    const info = extractPptInfo(payload)
    if (info.pptId && !completionSubmitted.value) {
      handleCompletion(info.pptId, info.subject, info.coverUrl, info.templateId)
    }
  })
}

async function mountDocmeeUI() {
  if (!docmeeContainer.value) throw new Error('AiPPT 容器未就绪')
  if (!docmeeToken.value) throw new Error('AiPPT token 为空')

  await loadDocmeeSdk(docmeeSdkUrl.value)
  destroyDocmeeUI()

  const DocmeeUI = window.DocmeeUI
  if (!DocmeeUI) throw new Error('文多多 AiPPT SDK 不可用')

  const instance = new DocmeeUI({
    token: docmeeToken.value,
    container: docmeeContainer.value,
    page: 'creator',
    creatorVersion: 'v2',
    mode: 'light',
    lang: 'zh',
    DOMAIN: docmeeDomain.value || undefined,
    targetOrigin: window.location.origin,
    creatorData: {
      type: 1,
      subject: topic.value.trim(),
    },
    isMobile: false,
  })

  docmeeInstance.value = instance
  bindDocmeeEvents(instance)
}

async function openStepByStep() {
  if (!validatePptForm()) return

  loadingSession.value = true
  try {
    const result = await createPptSession({
      user_id: userStore.userId,
      topic: topic.value.trim(),
      course_name: courseName.value,
      knowledge_points: knowledgePoints.value,
    })
    sessionId.value = result.session_id
    docmeeToken.value = result.embed_config.token
    docmeeDomain.value = result.embed_config.domain || result.embed_config.base_url
    docmeeSdkUrl.value = result.embed_config.sdk_url || 'https://oss.docmee.cn/ajax/libs/docmee/sdk-ui/dist/index.global.js'
    iframeVisible.value = true
    completionSubmitted.value = false
    await nextTick()
    await mountDocmeeUI()
    ElMessage.success('已打开 AiPPT 分步生成界面')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '创建会话失败'
    ElMessage.error(msg)
    iframeVisible.value = false
  } finally {
    loadingSession.value = false
  }
}

async function handleOneClick() {
  if (!validatePptForm()) return

  loadingOneClick.value = true
  try {
    const result = await oneClickGeneratePpt({
      user_id: userStore.userId,
      topic: topic.value.trim(),
      course_name: courseName.value,
      knowledge_points: knowledgePoints.value,
    })
    if (result.ok && result.resource) {
      resultResource.value = result.resource
      showResult.value = true
      ElMessage.success('PPT 一键生成完成，已保存到学习资源库')
    }
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '一键生成失败'
    ElMessage.error(msg)
  } finally {
    loadingOneClick.value = false
  }
}

function closeResult() {
  showResult.value = false
  resultResource.value = null
}

function getFullPptxUrl(url: string): string {
  if (!url) return ''
  if (url.startsWith('http')) return url
  const base = window.location.origin
  if (base.includes(':3000')) return base.replace(':3000', ':18000') + url
  return url
}

function navigateToResources() {
  router.push({ path: '/resources', query: { type: 'ppt' } })
}

function closeDocmeeSection() {
  iframeVisible.value = false
  iframeLoading.value = false
  destroyDocmeeUI()
}

onMounted(() => {
  checkConfig()
  loadProfile()
  if (userStore.userId) loadCurriculumCourses()
})

onUnmounted(() => {
  destroyDocmeeUI()
})

watch(() => userStore.userId, (newId) => {
  if (newId) loadCurriculumCourses()
})
</script>

<template>
  <div class="ppt-workspace">
    <div class="workspace-header">
      <h1 class="workspace-title">PPT 课件生成</h1>
      <p class="workspace-desc">输入主题，选择课程和知识点，使用文多多 AiPPT 生成课件并自动保存到学习资源库</p>
    </div>

    <div v-if="loadingConfig" class="config-status">
      <el-icon class="is-loading"><component :is="'Loading'" /></el-icon>
      <span>检查 PPT API 配置...</span>
    </div>

    <div v-else-if="!pptConfigured" class="config-status config-warn">
      <el-icon><component :is="'WarningFilled'" /></el-icon>
      <span>PPT API 未配置，请先在</span>
      <a href="/config" class="config-link">API 配置</a>
      <span>页面设置 Docmee AiPPT 密钥和 Base URL</span>
    </div>

    <template v-else>
      <div class="form-card">
        <div class="form-row">
          <label class="form-label">PPT 主题 <span class="required">*</span></label>
          <el-input
            v-model="topic"
            placeholder="输入 PPT 主题，如：数据结构——二叉树遍历"
            size="large"
            maxlength="100"
            show-word-limit
          />
        </div>

        <div class="form-row columns-2">
          <div class="form-col">
            <label class="form-label">绑定课程 <span class="required">*</span></label>
            <el-select
              v-model="courseName"
              placeholder="选择课程"
              clearable
              filterable
              style="width: 100%"
              @change="onCourseChange"
            >
              <el-option
                v-for="c in curriculumCourses"
                :key="c.id"
                :label="c.id"
                :value="c.id"
              />
            </el-select>
          </div>
          <div class="form-col">
            <label class="form-label">绑定知识点（可多选） <span class="required">*</span></label>
            <el-select
              v-model="knowledgePoints"
              placeholder="选择知识点"
              multiple
              filterable
              clearable
              style="width: 100%"
              :disabled="!courseName"
            >
              <el-option
                v-for="kp in kpOptions"
                :key="kp.id"
                :label="kp.id"
                :value="kp.id"
              />
            </el-select>
          </div>
        </div>

        <div class="form-actions">
          <el-button
            type="primary"
            size="large"
            :loading="loadingSession"
            :disabled="!canGenerate"
            @click="openStepByStep"
          >
            <el-icon style="margin-right:6px"><component :is="'EditPen'" /></el-icon>
            打开 AiPPT 分步生成
          </el-button>
          <el-button
            type="success"
            size="large"
            :loading="loadingOneClick"
            :disabled="!canGenerate"
            @click="handleOneClick"
          >
            <el-icon style="margin-right:6px"><component :is="'MagicStick'" /></el-icon>
            一键生成并保存
          </el-button>
        </div>

        <p class="form-hint">
          分步生成：打开文多多 AiPPT 官方界面，可自定义大纲和模板后生成。<br />
          一键生成：直接生成 PPT 并保存，无需手动操作。
        </p>
      </div>

      <div v-if="iframeVisible" class="iframe-section">
        <div class="iframe-header">
          <h3>文多多 AiPPT 分步生成</h3>
          <div class="iframe-header-right">
            <span v-if="iframeLoading" class="iframe-status generating">
              <el-icon class="is-loading"><component :is="'Loading'" /></el-icon>
              正在保存...
            </span>
            <span v-else class="iframe-status ready">等待生成完成...</span>
            <el-button size="small" text @click="closeDocmeeSection">关闭</el-button>
          </div>
        </div>
        <div class="iframe-wrapper">
          <div id="docmee-ppt-container" ref="docmeeContainer" class="ppt-iframe"></div>
        </div>
      </div>

      <div v-if="showResult && resultResource" class="result-card">
        <div class="result-header">
          <h3>
            <el-icon style="color:var(--color-success)"><component :is="'CircleCheckFilled'" /></el-icon>
            PPT 生成完成
          </h3>
          <el-button size="small" text @click="closeResult">
            <el-icon><component :is="'Close'" /></el-icon>
          </el-button>
        </div>
        <div class="result-body">
          <div class="result-info">
            <div class="result-info-item">
              <span class="info-label">标题</span>
              <span class="info-value">{{ resultResource.title }}</span>
            </div>
            <div class="result-info-item" v-if="resultResource.course_name">
              <span class="info-label">关联课程</span>
              <span class="info-value">{{ resultResource.course_name }}</span>
            </div>
            <div class="result-info-item" v-if="resultResource.knowledge_points?.length">
              <span class="info-label">知识点</span>
              <span class="info-value">
                <el-tag
                  v-for="kp in resultResource.knowledge_points"
                  :key="kp"
                  size="small"
                  type="info"
                  style="margin-right:4px"
                >{{ kp }}</el-tag>
              </span>
            </div>
          </div>
          <div class="result-actions">
            <el-button type="primary" @click="navigateToResources">
              <el-icon style="margin-right:4px"><component :is="'FolderOpened'" /></el-icon>
              查看学习资源库
            </el-button>
            <a
              v-if="resultResource.pptx_url"
              :href="getFullPptxUrl(resultResource.pptx_url)"
              target="_blank"
              class="download-link"
            >
              <el-button>
                <el-icon style="margin-right:4px"><component :is="'Download'" /></el-icon>
                下载 PPTX
              </el-button>
            </a>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ppt-workspace {
  max-width: 900px;
  margin: 0 auto;
}

.workspace-header {
  margin-bottom: 28px;
}

.workspace-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-body);
  margin: 0 0 8px 0;
}

.workspace-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.config-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  background: var(--page-white);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  font-size: 14px;
  color: var(--text-secondary);
}

.config-warn {
  border-color: var(--color-warning);
  background: rgba(230, 162, 60, 0.06);
  color: var(--color-warning);
}

.config-link {
  color: var(--link);
  text-decoration: underline;
  font-weight: 500;
}

.form-card {
  background: var(--page-white);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  padding: 24px;
  margin-bottom: 20px;
}

.form-row {
  margin-bottom: 16px;
}

.form-row.columns-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-col {
  display: flex;
  flex-direction: column;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-body);
  margin-bottom: 6px;
}

.required {
  color: var(--color-danger);
}

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.form-hint {
  font-size: 12px;
  color: var(--text-aux);
  margin: 12px 0 0 0;
  line-height: 1.6;
}

.iframe-section {
  background: var(--page-white);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  overflow: hidden;
  margin-bottom: 20px;
}

.iframe-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--brand-bg);
}

.iframe-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-body);
}

.iframe-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.iframe-status {
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.iframe-status.generating {
  color: var(--link);
}

.iframe-status.ready {
  color: var(--text-secondary);
}

.iframe-wrapper {
  width: 100%;
  height: 600px;
}

.ppt-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.result-card {
  background: var(--page-white);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  overflow: hidden;
  margin-bottom: 20px;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  background: rgba(103, 194, 58, 0.06);
}

.result-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.result-body {
  padding: 20px;
}

.result-info {
  margin-bottom: 16px;
}

.result-info-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 14px;
}

.info-label {
  color: var(--text-secondary);
  min-width: 70px;
  flex-shrink: 0;
}

.info-value {
  color: var(--text-body);
  word-break: break-all;
}

.result-actions {
  display: flex;
  gap: 10px;
}

.download-link {
  text-decoration: none;
  color: inherit;
}
</style>
