import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('learning_token') || '')
  const phone = ref(localStorage.getItem('learning_phone') || '')
  const firstLogin = ref(localStorage.getItem('learning_first_login') === '1')

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(data: { token: string; phone: string; first_login?: boolean }) {
    token.value = data.token
    phone.value = data.phone
    firstLogin.value = !!data.first_login
    localStorage.setItem('learning_token', token.value)
    localStorage.setItem('learning_phone', phone.value)
    localStorage.setItem('learning_first_login', firstLogin.value ? '1' : '0')
  }

  function markFirstLoginDone() {
    firstLogin.value = false
    localStorage.setItem('learning_first_login', '0')
  }

  function clearAuth() {
    token.value = ''
    phone.value = ''
    firstLogin.value = false
    localStorage.removeItem('learning_token')
    localStorage.removeItem('learning_phone')
    localStorage.removeItem('learning_first_login')
  }

  return { token, phone, firstLogin, isLoggedIn, setAuth, markFirstLoginDone, clearAuth }
})
