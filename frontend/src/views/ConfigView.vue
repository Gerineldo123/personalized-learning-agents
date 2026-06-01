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
const videoForm = ref<ApiForm>({ base_url: '', api_key: '', api_secret: '', model: '' })
const mainModels = ref<string[]>([])
const videoModels = ref<string[]>([])
const loadingMain = ref(false)
const loadingVideo = ref(false)
const savingMain = ref(false)
const savingVideo = ref(false)
const activeTab = ref('main')

onMounted(() => {
  loadMainConfig()
  loadVideoConfig()
})

async function loadMainConfig() {
  try {
    const r = await api.get('/config/main')
    mainForm.value.base_url = r.data.base_url
    mainForm.value.model = r.data.model
  } catch {}
}

async function loadVideoConfig() {
  try {
    const r = await api.get('/config/video')
    videoForm.value.base_url = r.data.base_url
    videoForm.value.model = r.data.model
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

async function saveVideo() {
  savingVideo.value = true
  try {
    await api.post('/config/video', videoForm.value)
    ElMessage.success('视频 API 配置已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingVideo.value = false
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

async function fetchVideoModels() {
  if (!videoForm.value.base_url || !videoForm.value.api_key) {
    ElMessage.warning('请先填写 URL 和密钥')
    return
  }
  loadingVideo.value = true
  try {
    await saveVideo()
    const r = await api.get('/config/video/models')
    if (r.data.error) {
      ElMessage.error(`获取失败：${r.data.error}`)
      videoModels.value = []
    } else {
      videoModels.value = r.data.models || []
      if (r.data.message) {
        ElMessage.success(r.data.message)
      }
    }
  } catch {
    ElMessage.error('获取模型列表失败')
  } finally {
    loadingVideo.value = false
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

      <el-tab-pane label="视频 API" name="video">
        <el-card class="config-card">
          <p class="desc">用于生成教学视频资源的 API。讯飞 VMS 格式：BaseURL 填服务地址，API Key 填 Key，API Secret 填 Secret，模型填场景 ID</p>

          <el-form label-width="100px">
            <el-form-item label="Base URL">
              <el-input v-model="videoForm.base_url" placeholder="https://api.example.com/v1" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="videoForm.api_key" type="password" show-password placeholder="sk-..." />
            </el-form-item>
            <el-form-item label="API Secret">
              <el-input v-model="videoForm.api_secret" type="password" show-password placeholder="可选" />
            </el-form-item>

            <el-form-item label="模型">
              <el-select v-model="videoForm.model" placeholder="先获取列表或手动输入" style="width: 100%" allow-create filterable>
                <el-option v-for="m in videoModels" :key="m" :label="m" :value="m" />
              </el-select>
              <el-button :loading="loadingVideo" @click="fetchVideoModels" style="margin-left: 8px">
                获取模型
              </el-button>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="savingVideo" @click="saveVideo">保存配置</el-button>
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
