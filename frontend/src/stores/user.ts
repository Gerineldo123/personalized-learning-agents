import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const userId = ref(localStorage.getItem('learning_user_id') || '')

  function setUserId(id: string) {
    userId.value = id
    localStorage.setItem('learning_user_id', id)
  }

  function clearUserId() {
    userId.value = ''
    localStorage.removeItem('learning_user_id')
  }

  return { userId, setUserId, clearUserId }
})
