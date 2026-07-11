<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

interface ApiForm {
  base_url: string
  api_key: string
  api_secret: string
  model: string
}

const mainForm = ref<ApiForm>({ base_url: '', api_key: '', api_secret: '', model: '' })
const tavilyForm = ref<ApiForm>({ base_url: '', api_key: '', api_secret: '', model: '' })
const pptForm = ref<ApiForm>({ base_url: '', api_key: '', api_secret: '', model: '' })
const mainModels = ref<string[]>([])
const pptModels = ref<string[]>([])
const loadingMain = ref(false)
const loadingPpt = ref(false)
const savingMain = ref(false)
const savingTavily = ref(false)
const testingTavily = ref(false)
const savingPpt = ref(false)
const testingPpt = ref(false)
const activeTab = ref('main')

const mainConfigured = ref(false)
const tavilyConfigured = ref(false)
const pptConfigured = ref(false)

onMounted(() => {
  loadMainConfig()
  loadTavilyConfig()
  loadPptConfig()
})

async function loadMainConfig() {
  try {
    const r = await api.get('/config/main')
    mainForm.value.base_url = r.data.base_url || ''
    mainForm.value.model = r.data.model || ''
    mainConfigured.value = !!r.data.has_key
  } catch {}
}

async function saveMain() {
  savingMain.value = true
  try {
    await api.post('/config/main', mainForm.value)
    ElMessage.success('主模型 API 配置已保存')
    mainConfigured.value = true
  } catch {
    ElMessage.error('主模型 API 配置保存失败')
  } finally {
    savingMain.value = false
  }
}

async function loadTavilyConfig() {
  try {
    const r = await api.get('/config/tavily')
    tavilyForm.value.api_key = ''
    tavilyConfigured.value = !!r.data.has_key
  } catch {}
}

async function saveTavily() {
  if (tavilyForm.value.api_key && !tavilyForm.value.api_key.startsWith('tvly-')) {
    ElMessage.warning('Tavily API Key 通常以 tvly- 开头，请检查后再保存')
    return
  }
  savingTavily.value = true
  try {
    await api.post('/config/tavily', tavilyForm.value)
    ElMessage.success('Tavily 搜索配置已保存')
    tavilyConfigured.value = true
  } catch {
    ElMessage.error('Tavily 搜索配置保存失败')
  } finally {
    savingTavily.value = false
  }
}

async function testTavily() {
  if (!tavilyForm.value.api_key) {
    ElMessage.warning('请先填写 Tavily API Key')
    return
  }
  testingTavily.value = true
  try {
    await saveTavily()
    const r = await api.post('/config/tavily/test')
    r.data.ok ? ElMessage.success('Tavily 连接测试通过') : ElMessage.error('Tavily 连接测试失败')
  } catch {
    ElMessage.error('Tavily 连接测试失败')
  } finally {
    testingTavily.value = false
  }
}

async function loadPptConfig() {
  try {
    const r = await api.get('/config/ppt')
    pptForm.value.base_url = r.data.base_url || ''
    pptForm.value.model = r.data.model || ''
    pptConfigured.value = !!r.data.has_key
  } catch {}
}

async function savePpt() {
  savingPpt.value = true
  try {
    if (pptForm.value.api_key) {
      if (!pptForm.value.base_url) pptForm.value.base_url = 'https://docmee.cn'
      if (!pptForm.value.model) pptForm.value.model = 'docmee-aippt'
    }
    await api.post('/config/ppt', pptForm.value)
    ElMessage.success('PPT 模型配置已保存')
    pptConfigured.value = true
  } catch {
    ElMessage.error('PPT 模型配置保存失败')
  } finally {
    savingPpt.value = false
  }
}

async function fetchMainModels() {
  if (!mainForm.value.base_url || !mainForm.value.api_key) {
    ElMessage.warning('请先填写 Base URL 和 API Key')
    return
  }
  loadingMain.value = true
  try {
    await saveMain()
    const r = await api.get('/config/main/models')
    if (r.data.error) {
      mainModels.value = []
      ElMessage.error('获取模型列表失败')
    } else {
      mainModels.value = r.data.models || []
      if (mainModels.value.length === 0) ElMessage.warning('未获取到可用模型')
    }
  } catch {
    ElMessage.error('获取模型列表失败')
  } finally {
    loadingMain.value = false
  }
}

async function fetchPptModels() {
  if (!pptForm.value.base_url || !pptForm.value.api_key) {
    ElMessage.warning('请先填写 Base URL 和 API Key')
    return
  }
  loadingPpt.value = true
  try {
    await savePpt()
    const r = await api.get('/config/ppt/models')
    if (r.data.error) {
      pptModels.value = []
      ElMessage.error('获取 PPT 模型列表失败')
    } else {
      pptModels.value = r.data.models || []
      if (pptModels.value.length === 0) ElMessage.warning('未获取到可用 PPT 模型')
    }
  } catch {
    ElMessage.error('获取 PPT 模型列表失败')
  } finally {
    loadingPpt.value = false
  }
}

async function testPpt() {
  if (!pptForm.value.base_url || !pptForm.value.api_key || !pptForm.value.model) {
    ElMessage.warning('请先填写 Base URL、API Key 和模型')
    return
  }
  testingPpt.value = true
  try {
    await savePpt()
    const r = await api.post('/config/ppt/test')
    r.data.ok ? ElMessage.success('PPT 模型连接测试通过') : ElMessage.error('PPT 模型连接测试失败')
  } catch {
    ElMessage.error('PPT 模型连接测试失败')
  } finally {
    testingPpt.value = false
  }
}
</script>

<template>
  <div class="config-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">API 配置</h2>
        <p class="page-subtitle">管理主模型、搜索服务与 PPT 生成服务。</p>
      </div>
      <div class="status-summary">
        <span class="status-dot" :class="{ active: mainConfigured }"></span>
        <span class="status-dot" :class="{ active: tavilyConfigured }"></span>
        <span class="status-dot" :class="{ active: pptConfigured }"></span>
        <span class="status-text">{{ [mainConfigured, tavilyConfigured, pptConfigured].filter(Boolean).length }} / 3 项已配置</span>
      </div>
    </div>

    <details class="compliance-panel">
      <summary>开源与 AI 工具说明</summary>
      <p>赛题要求在提交文档显著位置标注开源项目、AI 工具/框架及协议。本系统保留此说明入口，最终提交前仍需团队人工复核版本和协议。</p>
      <div class="compliance-grid">
        <span>Vue / Vite / Element Plus：前端框架与 UI，MIT</span>
        <span>ECharts：图表可视化，Apache-2.0</span>
        <span>FastAPI / SQLAlchemy：后端 API 与 ORM，MIT</span>
        <span>ChromaDB：向量检索与 RAG，Apache-2.0</span>
        <span>LangGraph：多智能体编排，MIT</span>
        <span>OpenAI SDK / 兼容模型 API：大模型能力，按服务商条款</span>
        <span>Docmee / veasion AiPPT：PPT 分步生成，按仓库协议与服务条款</span>
        <span>python-pptx / Pillow：课件与图片处理，MIT / HPND</span>
      </div>
      <p class="compliance-note">完整清单见 <code>docs/第三方依赖与AI工具说明.md</code>。</p>
    </details>

    <el-tabs v-model="activeTab" class="config-tabs">
      <el-tab-pane name="main">
        <template #label>
          <span class="tab-label">主模型 API<el-tag v-if="mainConfigured" size="small" type="success" effect="plain" class="tab-tag">已配置</el-tag><el-tag v-else size="small" type="info" effect="plain" class="tab-tag">未配置</el-tag></span>
        </template>
        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="card-header-left">
                <h3 class="card-title">主模型 API 配置</h3>
                <p class="card-desc">用于 AI 对话、画像构建、资源生成与学习路径规划。</p>
              </div>
              <el-tag v-if="mainConfigured" type="success" effect="light" size="small">已连接</el-tag>
              <el-tag v-else type="warning" effect="light" size="small">待配置</el-tag>
            </div>
          </template>
          <el-form label-position="top" class="config-form">
            <el-row :gutter="24">
              <el-col :span="12"><el-form-item label="Base URL"><el-input v-model="mainForm.base_url" placeholder="https://api.openai.com/v1" clearable /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="模型"><el-select v-model="mainForm.model" placeholder="选择或输入模型名称" style="width: 100%" allow-create filterable clearable><el-option v-for="m in mainModels" :key="m" :label="m" :value="m" /></el-select></el-form-item></el-col>
            </el-row>
            <el-row :gutter="24">
              <el-col :span="12"><el-form-item label="API Key"><el-input v-model="mainForm.api_key" type="password" show-password placeholder="sk-..." clearable /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="API Secret"><el-input v-model="mainForm.api_secret" type="password" show-password placeholder="部分平台需要，可留空" clearable /></el-form-item></el-col>
            </el-row>
            <div class="form-footer"><el-button type="primary" :loading="savingMain" @click="saveMain">保存配置</el-button><el-button :loading="loadingMain" @click="fetchMainModels">获取模型列表</el-button></div>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane name="tavily">
        <template #label>
          <span class="tab-label">Tavily 搜索<el-tag v-if="tavilyConfigured" size="small" type="success" effect="plain" class="tab-tag">已配置</el-tag><el-tag v-else size="small" type="info" effect="plain" class="tab-tag">未配置</el-tag></span>
        </template>
        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header"><div class="card-header-left"><h3 class="card-title">Tavily 搜索配置</h3><p class="card-desc">用于智能体任务中的互联网搜索。<a href="https://app.tavily.com">获取 API Key</a></p></div><el-tag v-if="tavilyConfigured" type="success" effect="light" size="small">已连接</el-tag><el-tag v-else type="warning" effect="light" size="small">待配置</el-tag></div>
          </template>
          <el-form label-position="top" class="config-form">
            <el-form-item label="API Key"><el-input v-model="tavilyForm.api_key" type="password" show-password placeholder="tvly-..." clearable /></el-form-item>
            <div class="form-footer"><el-button type="primary" :loading="savingTavily" @click="saveTavily">保存配置</el-button><el-button :loading="testingTavily" @click="testTavily">测试连接</el-button></div>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane name="ppt">
        <template #label>
          <span class="tab-label">PPT 模型<el-tag v-if="pptConfigured" size="small" type="success" effect="plain" class="tab-tag">已配置</el-tag><el-tag v-else size="small" type="info" effect="plain" class="tab-tag">未配置</el-tag></span>
        </template>
        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header"><div class="card-header-left"><h3 class="card-title">PPT 课件模型配置</h3><p class="card-desc">用于 Docmee / AiPPT 分步生成。未配置时无法进入完整 PPT 生成流程。</p></div><el-tag v-if="pptConfigured" type="success" effect="light" size="small">已连接</el-tag><el-tag v-else type="warning" effect="light" size="small">待配置</el-tag></div>
          </template>
          <el-form label-position="top" class="config-form">
            <el-row :gutter="24">
              <el-col :span="12"><el-form-item label="Base URL"><el-input v-model="pptForm.base_url" placeholder="https://docmee.cn" clearable /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="模型"><el-select v-model="pptForm.model" placeholder="docmee-aippt" style="width: 100%" allow-create filterable clearable><el-option v-for="m in pptModels" :key="m" :label="m" :value="m" /></el-select></el-form-item></el-col>
            </el-row>
            <el-row :gutter="24">
              <el-col :span="12"><el-form-item label="API Key"><el-input v-model="pptForm.api_key" type="password" show-password placeholder="Docmee API Key" clearable /></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="API Secret"><el-input v-model="pptForm.api_secret" type="password" show-password placeholder="如不需要可留空" clearable /></el-form-item></el-col>
            </el-row>
            <div class="form-footer"><el-button type="primary" :loading="savingPpt" @click="savePpt">保存配置</el-button><el-button :loading="loadingPpt" @click="fetchPptModels">获取模型列表</el-button><el-button :loading="testingPpt" @click="testPpt">测试连接</el-button></div>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.config-view { max-width: 880px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 4px; }
.page-title { font-size: 24px; font-weight: 600; color: var(--text-primary); margin: 0 0 4px; }
.page-subtitle { font-size: 14px; color: var(--text-secondary); margin: 0; }
.status-summary { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border-base); transition: background var(--transition-fast); }
.status-dot.active { background: var(--color-success); }
.status-text { font-size: 12px; color: var(--text-secondary); margin-left: 4px; }
.config-tabs { margin-top: 8px; }
.compliance-panel { margin: 16px 0 8px; padding: 14px 16px; border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--bg-card); color: var(--text-secondary); }
.compliance-panel summary { cursor: pointer; font-weight: 600; color: var(--text-primary); }
.compliance-panel p { margin: 10px 0 0; line-height: 1.6; font-size: 13px; }
.compliance-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; margin-top: 12px; }
.compliance-grid span { padding: 8px 10px; border-radius: var(--radius-md); background: var(--bg-soft); font-size: 12px; color: var(--text-primary); }
.compliance-note code { color: var(--color-primary); }
.tab-label { display: inline-flex; align-items: center; gap: 0; }
.tab-tag { margin-left: 8px; font-size: 11px; }
.config-card { border: 1px solid var(--border-light); border-radius: var(--radius-lg); background: var(--bg-card); margin-top: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.card-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin: 0 0 4px; }
.card-desc { font-size: 13px; color: var(--text-secondary); margin: 0; line-height: 1.6; }
.card-desc a { color: var(--color-primary); text-decoration: none; }
.config-form { padding-top: 8px; }
.form-footer { display: flex; gap: 12px; justify-content: flex-end; margin-top: 8px; }
@media (max-width: 720px) { .page-header, .card-header { flex-direction: column; align-items: flex-start; } .compliance-grid { grid-template-columns: 1fr; } }
</style>
