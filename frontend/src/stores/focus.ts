import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useUserStore } from './user'
import { reportFocusSession } from '../api/focus'

export const useFocusStore = defineStore('focus', () => {
  const state = ref<'idle' | 'selecting' | 'focusing' | 'completed'>('idle')
  const focusMinutes = ref(25)
  const focusSeconds = ref(0)
  const focusRemaining = ref(0)
  const focusTotal = ref(0)
  const timerView = ref<'hourglass' | 'digital'>('hourglass')
  const completedFocusCount = ref(0)
  const focusSessions = ref<{ date: string; minutes: number; completed: boolean }[]>([])
  let focusTimer: ReturnType<typeof setInterval> | null = null
  let beforeUnloadHandler: ((e: BeforeUnloadEvent) => void) | null = null
  let focusStartedAt = 0

  const displayMinutes = computed(() => Math.floor(focusRemaining.value / 60))
  const displaySeconds = computed(() => focusRemaining.value % 60)
  const focusProgress = computed(() =>
    focusTotal.value > 0 ? ((focusTotal.value - focusRemaining.value) / focusTotal.value) * 100 : 0,
  )
  const isFocusing = computed(() => state.value === 'focusing')

  function init() {
    const saved = localStorage.getItem('focus-completed-count')
    if (saved) completedFocusCount.value = parseInt(saved) || 0
    const sessions = localStorage.getItem('focus-sessions')
    if (sessions) focusSessions.value = JSON.parse(sessions)
  }

  function openTimePicker() {
    state.value = 'selecting'
  }

  async function startFocus() {
    focusTotal.value = focusMinutes.value * 60 + focusSeconds.value
    focusRemaining.value = focusTotal.value
    focusStartedAt = Date.now()
    state.value = 'focusing'

    try {
      await document.documentElement.requestFullscreen()
    } catch {
      // fullscreen not supported or denied — still allow focus to start
    }

    addGlobalListeners()
    startTimer()
  }

  function startTimer() {
    focusTimer = setInterval(() => {
      focusRemaining.value--
      if (focusRemaining.value <= 0) {
        completeFocus()
      }
    }, 1000)
  }

  function completeFocus() {
    stopTimer()
    removeGlobalListeners()
    exitFullscreen()
    state.value = 'completed'
    completedFocusCount.value++
    localStorage.setItem('focus-completed-count', String(completedFocusCount.value))
    const session = {
      date: new Date().toISOString(),
      minutes: focusTotal.value / 60,
      completed: true,
    }
    focusSessions.value.unshift(session)
    if (focusSessions.value.length > 50) focusSessions.value = focusSessions.value.slice(0, 50)
    localStorage.setItem('focus-sessions', JSON.stringify(focusSessions.value))

    const userId = useUserStore().userId
    if (userId) {
      reportFocusSession(userId, {
        started_at: new Date(focusStartedAt).toISOString(),
        duration_min: Math.round(focusTotal.value / 60),
        completed: true,
      }).catch(() => {})
    }
  }

  function unlockFocus() {
    stopTimer()
    removeGlobalListeners()
    exitFullscreen()
    const minutes = Math.ceil((focusTotal.value - focusRemaining.value) / 60)
    if (minutes > 0) {
      const session = {
        date: new Date().toISOString(),
        minutes,
        completed: false,
      }
      focusSessions.value.unshift(session)
      if (focusSessions.value.length > 50) focusSessions.value = focusSessions.value.slice(0, 50)
      localStorage.setItem('focus-sessions', JSON.stringify(focusSessions.value))

      const userId = useUserStore().userId
      if (userId) {
        reportFocusSession(userId, {
          started_at: new Date(focusStartedAt).toISOString(),
          duration_min: minutes,
          completed: false,
        }).catch(() => {})
      }
    }
    state.value = 'idle'
  }

  function backToIdle() {
    state.value = 'idle'
  }

  function stopTimer() {
    if (focusTimer) {
      clearInterval(focusTimer)
      focusTimer = null
    }
  }

  function exitFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {})
    }
  }

  // ── Global event listeners ──

  function handleFullscreenChange() {
    if (!document.fullscreenElement && state.value === 'focusing') {
      unlockFocus()
    }
  }

  function handleVisibilityChange() {
    if (document.hidden && state.value === 'focusing') {
      unlockFocus()
    }
  }

  function handleBeforeUnload(e: BeforeUnloadEvent) {
    if (state.value === 'focusing') {
      e.preventDefault()
      e.returnValue = ''
    }
  }

  function addGlobalListeners() {
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    beforeUnloadHandler = handleBeforeUnload
    window.addEventListener('beforeunload', beforeUnloadHandler)
  }

  function removeGlobalListeners() {
    document.removeEventListener('fullscreenchange', handleFullscreenChange)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    if (beforeUnloadHandler) {
      window.removeEventListener('beforeunload', beforeUnloadHandler)
      beforeUnloadHandler = null
    }
  }

  function cleanup() {
    stopTimer()
    removeGlobalListeners()
    exitFullscreen()
  }

  return {
    state,
    focusMinutes,
    focusSeconds,
    focusRemaining,
    focusTotal,
    timerView,
    completedFocusCount,
    focusSessions,
    displayMinutes,
    displaySeconds,
    focusProgress,
    isFocusing,
    init,
    openTimePicker,
    startFocus,
    completeFocus,
    unlockFocus,
    backToIdle,
    cleanup,
  }
})
