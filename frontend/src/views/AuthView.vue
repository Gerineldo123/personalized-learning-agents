<script setup lang="ts">
import { ref } from 'vue'
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
const loading = ref(false)

function validPhone(v: string) {
  return /^1[3-9]\d{9}$/.test(v)
}

function validPassword(v: string) {
  return /^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]{6,14}$/.test(v)
}

function validateForm() {
  if (!validPhone(phone.value)) return '请输入正确的11位手机号'
  if (!validPassword(password.value)) return '密码需为6~14位，且仅可包含大小写字母、数字和特殊符号'
  if (mode.value === 'register' && password.value !== confirmPassword.value) return '两次输入密码不一致'
  return ''
}

async function submit() {
  const err = validateForm()
  if (err) {
    ElMessage.warning(err)
    return
  }
  loading.value = true
  try {
    const endpoint = mode.value === 'login' ? '/auth/login' : '/auth/register'
    const params: any = { phone: phone.value, password: password.value }
    if (mode.value === 'register') params.confirm_password = confirmPassword.value
    const r = await api.post(endpoint, null, { params })
    authStore.setAuth(r.data)
    userStore.setUserId(r.data.phone)
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
    if (r.data.first_login) {
      router.push({ path: '/profile', query: { first: '1' } })
    } else {
      router.push('/')
    }
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
