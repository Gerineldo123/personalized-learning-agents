import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useEventStore = defineStore('event', () => {
  const lastEvent = ref<{ event: string; data: any } | null>(null)
  const connected = ref(false)
  let eventSource: EventSource | null = null

  function connect(userId: string) {
    if (eventSource) return
    eventSource = new EventSource(`/api/events/stream?user_id=${userId}`)
    eventSource.onopen = () => { connected.value = true }
    eventSource.onmessage = (e) => {
      if (!e.data.trim()) return
      try {
        const payload = JSON.parse(e.data)
        lastEvent.value = payload
      } catch {}
    }
    eventSource.onerror = () => { connected.value = false }
  }

  function disconnect() {
    eventSource?.close()
    eventSource = null
    connected.value = false
  }

  return { lastEvent, connected, connect, disconnect }
})
