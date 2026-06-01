import { ref } from 'vue'
import { chatStream } from '../api/chat'

export function useSSE() {
  const text = ref('')
  const isStreaming = ref(false)
  let controller: AbortController | null = null

  function startStream(userId: string, message: string) {
    text.value = ''
    isStreaming.value = true

    controller = chatStream(
      userId,
      message,
      (chunk) => { text.value += chunk },
      () => { isStreaming.value = false },
      (err) => {
        text.value = `[错误] ${err.message}`
        isStreaming.value = false
      },
    )
  }

  function abort() {
    controller?.abort()
    isStreaming.value = false
  }

  return { text, isStreaming, startStream, abort }
}
