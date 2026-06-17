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
const loadingMain = ref(false)
const savingMain = ref(false)
const savingTavily = ref(false)
const testingTavily = ref(false)
const savingPpt = ref(false)
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
    mainForm.value.base_url = r.data.base_url
    mainForm.value.model = r.data.model
    mainConfigured.value = !!r.data.has_key
  } catch { /* ignore */ }
}

async function saveMain() {
  savingMain.value = true
  try {
    await api.post('/config/main', mainForm.value)
    ElMessage.success('主 API 配置已保存')
    mainConfigured.value = true
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingMain.value = false
  }
}

async function loadTavilyConfig() {
  try {
    const r = await api.get('/config/tavily')
    tavilyForm.value.api_key = ''
    tavilyConfigured.value = !!r.data.has_key
  } catch { /* ignore */ }
}

async function loadPptConfig() {
  try {
    const r = await api.get('/config/ppt')
    pptForm.value.base_url = r.data.base_url
    pptForm.value.model = r.data.model
    pptConfigured.value = !!r.data.has_key
  } catch { /* ignore */ }
}

async function savePpt() {
  savingPpt.value = true
  try {
    await api.post('/config/ppt', pptForm.value)
    ElMessage.success('PPT 模型配置已保存')
    pptConfigured.value = true
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingPpt.value = false
  }
}

async function saveTavily() {
  if (tavilyForm.value.api_key && !tavilyForm.value.api_key.startsWith('tvly-')) {
    ElMessage.warning('Tavily API Key 应以 tvly- 开头，请检查是否填入了正确的密钥')
    return
  }
  savingTavily.value = true
  try {
    await api.post('/config/tavily', tavilyForm.value)
    ElMessage.success('Tavily API 配置已保存')
    tavilyConfigured.value = true
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingTavily.value = false
  }
}

async function testTavily() {
  if (!tavilyForm.value.api_key) {
    ElMessage.warning('请先填写 API Key')
    return
  }
  testingTavily.value = true
  try {
    await saveTavily()
    const r = await api.post('/config/tavily/test')
    if (r.data.ok) {
      ElMessage.success(`Tavily 连接成功，返回 ${r.data.result_count} 条结果`)
    } else {
      ElMessage.error(`Tavily 连接失败：${r.data.error || '未知错误'}`)
    }
  } catch {
    ElMessage.error('Tavily 测试失败')
  } finally {
    testingTavily.value = false
  }
}

async function fetchMainModels() {
  if (!mainForm.value.base_url || !mainForm.value.api_key) {
    ElMessage.warning('请先填写 URL 和密钥')
    return
  }
  loadingMain.value = true
  try {
    await saveMain()
    const r = await api.get('/config/main/models')
    if (r.data.error) {
      ElMessage.error(`获取失败：${r.data.error}`)
      mainModels.value = []
    } else {
      mainModels.value = r.data.models || []
      if (mainModels.value.length === 0) {
        ElMessage.warning('未能获取模型列表，接口可能不支持此功能')
      }
    }
  } catch {
    ElMessage.error('获取模型列表失败')
  } finally {
    loadingMain.value = false
  }
}
</script>

<template>
  <div class="config-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">API 配置</h2>
        <p class="page-subtitle">管理 AI 大模型与搜索服务的连接参数</p>
      </div>
      <div class="status-summary">
        <span class="status-dot" :class="{ active: mainConfigured }"></span>
        <span class="status-dot" :class="{ active: tavilyConfigured }"></span>
        <span class="status-dot" :class="{ active: pptConfigured }"></span>
        <span class="status-text">
          {{ [mainConfigured, tavilyConfigured, pptConfigured].filter(Boolean).length }} / 3 项已配置
        </span>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="config-tabs">
      <el-tab-pane name="main">
        <template #label>
          <span class="tab-label">
            主 API
            <el-tag v-if="mainConfigured" size="small" type="success" effect="plain" class="tab-tag">已配置</el-tag>
            <el-tag v-else size="small" type="info" effect="plain" class="tab-tag">未配置</el-tag>
          </span>
        </template>

        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="card-header-left">
                <h3 class="card-title">主 API 配置</h3>
                <p class="card-desc">作为 AI 对话、画像构建、资源生成及学习路径规划的默认大模型接口</p>
              </div>
              <el-tag v-if="mainConfigured" type="success" effect="light" size="small">已连接</el-tag>
              <el-tag v-else type="warning" effect="light" size="small">待配置</el-tag>
            </div>
          </template>

          <el-form label-position="top" class="config-form">
            <el-row :gutter="24">
              <el-col :span="12">
                <el-form-item label="Base URL">
                  <el-input v-model="mainForm.base_url" placeholder="https://api.openai.com/v1" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="模型">
                  <el-select
                    v-model="mainForm.model"
                    placeholder="选择或输入模型名称"
                    style="width: 100%"
                    allow-create
                    filterable
                    clearable
                  >
                    <el-option v-for="m in mainModels" :key="m" :label="m" :value="m" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="24">
              <el-col :span="12">
                <el-form-item label="API Key">
                  <el-input v-model="mainForm.api_key" type="password" show-password placeholder="sk-..." clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="API Secret">
                  <el-input v-model="mainForm.api_secret" type="password" show-password placeholder="部分平台需要（如讯飞）" clearable />
                </el-form-item>
              </el-col>
            </el-row>

            <div class="form-footer">
              <el-button type="primary" :loading="savingMain" @click="saveMain">保存配置</el-button>
              <el-button :loading="loadingMain" @click="fetchMainModels">获取模型列表</el-button>
            </div>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane name="tavily">
        <template #label>
          <span class="tab-label">
            Tavily 搜索
            <el-tag v-if="tavilyConfigured" size="small" type="success" effect="plain" class="tab-tag">已配置</el-tag>
            <el-tag v-else size="small" type="info" effect="plain" class="tab-tag">未配置</el-tag>
          </span>
        </template>

        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="card-header-left">
                <h3 class="card-title">Tavily 搜索配置</h3>
                <p class="card-desc">
                  用于 Agent 任务执行时的互联网搜索引擎，
                  <a href="https://app.tavily.com" target="_blank">获取 API Key</a>
                </p>
              </div>
              <el-tag v-if="tavilyConfigured" type="success" effect="light" size="small">已连接</el-tag>
              <el-tag v-else type="warning" effect="light" size="small">待配置</el-tag>
            </div>
          </template>

          <el-form label-position="top" class="config-form">
            <el-form-item label="API Key">
              <el-input v-model="tavilyForm.api_key" type="password" show-password placeholder="tvly-..." clearable />
            </el-form-item>

            <div class="form-footer">
              <el-button type="primary" :loading="savingTavily" @click="saveTavily">保存配置</el-button>
              <el-button :loading="testingTavily" @click="testTavily">测试连接</el-button>
            </div>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane name="ppt">
        <template #label>
          <span class="tab-label">
            PPT 模型
            <el-tag v-if="pptConfigured" size="small" type="success" effect="plain" class="tab-tag">已配置</el-tag>
            <el-tag v-else size="small" type="info" effect="plain" class="tab-tag">未配置</el-tag>
          </span>
        </template>

        <el-card class="config-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="card-header-left">
                <h3 class="card-title">PPT 课件模型配置</h3>
                <p class="card-desc">PPT 课件生成的专用大模型接口 — 不配置则自动回退到主 API 生成</p>
              </div>
              <el-tag v-if="pptConfigured" type="success" effect="light" size="small">已连接</el-tag>
              <el-tag v-else type="warning" effect="light" size="small">待配置</el-tag>
            </div>
          </template>

          <el-form label-position="top" class="config-form">
            <el-row :gutter="24">
              <el-col :span="12">
                <el-form-item label="Base URL">
                  <el-input v-model="pptForm.base_url" placeholder="https://api.openai.com/v1" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="模型">
                  <el-select
                    v-model="pptForm.model"
                    placeholder="输入模型名称"
                    style="width: 100%"
                    allow-create
                    filterable
                    clearable
                  >
                    <el-option v-for="m in mainModels" :key="m" :label="m" :value="m" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="24">
              <el-col :span="12">
                <el-form-item label="API Key">
                  <el-input v-model="pptForm.api_key" type="password" show-password placeholder="sk-..." clearable />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="API Secret">
                  <el-input v-model="pptForm.api_secret" type="password" show-password placeholder="如不需要可留空" clearable />
                </el-form-item>
              </el-col>
            </el-row>

            <div class="form-footer">
              <el-button type="primary" :loading="savingPpt" @click="savePpt">保存配置</el-button>
            </div>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.config-view {
  max-width: 880px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 4px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.status-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-base);
  transition: background var(--transition-fast);
}

.status-dot.active {
  background: var(--color-success);
}

.status-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 4px;
}

.config-tabs {
  margin-top: 8px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 0;
}

.tab-tag {
  margin-left: 8px;
  font-size: 11px;
}

.config-card {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  margin-top: 16px;
  transition: box-shadow var(--transition-base);
}

.config-card:hover {
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.card-header-left {
  flex: 1;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 4px 0 0;
}

.card-desc a {
  color: var(--color-primary);
  font-weight: 500;
}

.config-form {
  margin-top: 4px;
}

.config-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.config-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  padding-bottom: 4px;
}

.config-form :deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 1px var(--border-light);
  transition: box-shadow var(--transition-fast), border-color var(--transition-fast);
}

.config-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--border-base);
}

.config-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--color-primary-border);
}

.form-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
  margin-top: 4px;
}

/* Element Plus tab overrides */
:deep(.el-tabs__header) {
  margin-bottom: 0;
}

:deep(.el-tabs__nav-wrap::after) {
  background-color: var(--border-light);
}

:deep(.el-tabs__item) {
  font-size: 14px;
  padding: 0 20px;
  height: 42px;
  line-height: 42px;
  color: var(--text-secondary);
}

:deep(.el-tabs__item.is-active) {
  color: var(--color-primary);
  font-weight: 600;
}

:deep(.el-tabs__item:hover) {
  color: var(--color-primary);
}

:deep(.el-tabs__active-bar) {
  background-color: var(--color-primary);
}

:deep(.el-card__header) {
  padding: 18px 24px;
  border-bottom-color: var(--border-light);
}

:deep(.el-card__body) {
  padding: 20px 24px 24px;
}
</style>
