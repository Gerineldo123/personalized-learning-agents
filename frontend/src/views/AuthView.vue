<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import { useUserStore } from '../stores/user'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const userStore = useUserStore()

const mode = ref<'login' | 'register'>('login')
const phone = ref('')
const password = ref('')
const confirmPassword = ref('')
const educationLevel = ref('本科')
const grade = ref('')
const major = ref('')
const currentSemester = ref(1)
const majorOptions = ref<string[]>(['计算机科学与技术', '软件工程', '人工智能', '智能科学与技术'])
const loading = ref(false)

const GRADE_OPTIONS: Record<string, string[]> = {
  '本科': ['大一', '大二', '大三', '大四'],
  '硕士': ['研一', '研二', '研三'],
  '博士': ['博一', '博二', '博三'],
  '专科': ['大一', '大二', '大三'],
}
const MAJOR_OPTIONS = ['计算机科学与技术', '软件工程', '人工智能', '智能科学与技术']
const SEMESTER_BY_GRADE: Record<string, number> = {
  '大一': 1,
  '大二': 3,
  '大三': 5,
  '大四': 7,
  '研一': 1,
  '研二': 3,
  '研三': 5,
  '博一': 1,
  '博二': 3,
  '博三': 5,
}
const SEMESTER_OPTIONS = Array.from({ length: 8 }, (_, index) => index + 1)

function validPhone(v: string) {
  return /^1[3-9]\d{9}$/.test(v)
}

function validPassword(v: string) {
  return /^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]{6,14}$/.test(v)
}

function validateForm() {
  if (!validPhone(phone.value)) return '请输入正确的11位手机号'
  if (!validPassword(password.value)) return '密码需为6~14位，且仅可包含大小写字母、数字和特殊符号'
  if (mode.value === 'register') {
    if (password.value !== confirmPassword.value) return '两次输入密码不一致'
    if (!grade.value) return '请选择年级'
    if (!major.value) return '请选择专业'
  }
  return ''
}

function syncCurrentSemester() {
  currentSemester.value = SEMESTER_BY_GRADE[grade.value] || 1
}

async function loadMajors() {
  try {
    const r = await api.get('/curriculum/majors')
    const names = (r.data || []).map((item: any) => item.major_name).filter(Boolean)
    if (names.length) majorOptions.value = names
  } catch {
    majorOptions.value = MAJOR_OPTIONS
  }
}

watch(grade, syncCurrentSemester)

onMounted(loadMajors)

async function submit() {
  const err = validateForm()
  if (err) { ElMessage.warning(err); return }
  loading.value = true
  try {
    const endpoint = mode.value === 'login' ? '/auth/login' : '/auth/register'
    const params: any = { phone: phone.value, password: password.value }
    if (mode.value === 'register') {
      params.confirm_password = confirmPassword.value
      params.education_level = educationLevel.value
      params.grade = grade.value
      params.major = major.value
      params.current_semester = currentSemester.value
    }
    const r = await api.post(endpoint, null, { params })
    authStore.setAuth(r.data)
    userStore.setUserId(r.data.phone)
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
    router.push(mode.value === 'register' ? { path: '/profile', query: { onboarding: '1' } } : '/')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '请求失败'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <el-card class="auth-card">
      <template #header>
        <div class="auth-head">
          <span>账号登录</span>
          <el-radio-group v-model="mode" size="small">
            <el-radio-button value="login">登录</el-radio-button>
            <el-radio-button value="register">注册</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-form label-position="top">
        <el-form-item label="手机号">
          <el-input v-model="phone" maxlength="11" placeholder="请输入11位手机号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" show-password type="password" placeholder="6~14位，字母数字符号" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="确认密码">
          <el-input v-model="confirmPassword" show-password type="password" placeholder="请再次输入密码" />
        </el-form-item>
        <template v-if="mode === 'register'">
          <el-form-item label="学历层次">
            <el-radio-group v-model="educationLevel" @change="grade = ''; currentSemester = 1">
              <el-radio-button v-for="lv in Object.keys(GRADE_OPTIONS)" :key="lv" :value="lv">{{ lv }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="年级">
            <el-radio-group v-model="grade">
              <el-radio-button v-for="g in GRADE_OPTIONS[educationLevel]" :key="g" :value="g">{{ g }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="当前学期">
            <el-select v-model="currentSemester" placeholder="请选择当前学期" style="width:100%">
              <el-option v-for="s in SEMESTER_OPTIONS" :key="s" :value="s" :label="`第 ${s} 学期`" />
            </el-select>
          </el-form-item>
          <el-form-item label="专业">
            <el-select v-model="major" placeholder="请选择专业" style="width:100%">
              <el-option v-for="m in majorOptions" :key="m" :value="m" :label="m" />
            </el-select>
          </el-form-item>
        </template>
      </el-form>

      <el-button type="primary" :loading="loading" class="submit-btn" @click="submit">
        {{ mode === 'login' ? '登录' : '注册并登录' }}
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.auth-wrap {
  min-height: calc(100vh - 48px);
  display: grid;
  place-items: center;
  background: linear-gradient(180deg, #F9D9B8 0%, #FFF5EB 45%, #FFFBF5 100%);
}
.auth-card {
  width: 420px;
  background: #FFFBF5;
  border: 1px solid #EFE6DC;
  border-radius: 12px;
}
.auth-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #3A332E;
  font-size: 20px;
  font-weight: 500;
}
.submit-btn {
  width: 100%;
  margin-top: 8px;
  background: #F9D9B8;
  color: #3A332E;
  border-radius: 8px;
  border: none;
}
.submit-btn:hover { background: #E8C29C; }
</style>
