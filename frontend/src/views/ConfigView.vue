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
const mainModels = ref<string[]>([])
const loadingMain = ref(false)
const savingMain = ref(false)
const savingTavily = ref(false)
const testingTavily = ref(false)
const activeTab = ref('main')

onMounted(() => {
  loadMainConfig()
  loadTavilyConfig()
})

async function loadMainConfig() {
  try {
    const r = await api.get('/config/main')
    mainForm.value.base_url = r.data.base_url
    mainForm.value.model = r.data.model
  } catch {}
}

async function saveMain() {
  savingMain.value = true
  try {
    await api.post('/config/main', mainForm.value)
    ElMessage.success('主 API 配置已保存')
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
  } catch {}
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
    <h2 class="page-title">API 配置</h2>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="主 API" name="main">
        <el-card class="config-card">
          <p class="desc">用于 AI 对话、画像构建、资源生成、路径规划的 API</p>

          <el-form label-width="100px">
            <el-form-item label="Base URL">
              <el-input v-model="mainForm.base_url" placeholder="https://api.openai.com/v1" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="mainForm.api_key" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="API Secret">
              <el-input v-model="mainForm.api_secret" type="password" show-password placeholder="讯飞等需填充" />
            </el-form-item>

            <el-form-item label="模型">
              <el-select v-model="mainForm.model" placeholder="先获取列表或手动输入" style="width: 100%" allow-create filterable>
                <el-option v-for="m in mainModels" :key="m" :label="m" :value="m" />
              </el-select>
              <el-button :loading="loadingMain" @click="fetchMainModels" style="margin-left: 8px">
                获取模型
              </el-button>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="savingMain" @click="saveMain">保存配置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="Tavily 搜索" name="tavily">
        <el-card class="config-card">
          <p class="desc">用于 Agent 任务执行面板的互联网搜索 API。<a href="https://app.tavily.com" target="_blank">获取 API Key</a></p>

          <el-form label-width="100px">
            <el-form-item label="API Key">
              <el-input v-model="tavilyForm.api_key" type="password" show-password placeholder="tvly-..." />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="savingTavily" @click="saveTavily">保存配置</el-button>
              <el-button :loading="testingTavily" @click="testTavily" style="margin-left: 8px">测试连接</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.config-view { max-width: 700px; }
.page-title { margin-bottom: 24px; color: #303133; }
.config-card { margin-top: 16px; }
.desc { color: #909399; font-size: 13px; margin-bottom: 20px; }
</style>
