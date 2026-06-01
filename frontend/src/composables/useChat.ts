import { ref } from 'vue'
import { chatStream } from '../api/chat'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export function useChat(userId: string) {
  const messages = ref<ChatMessage[]>([])
  const inputText = ref('')
  const isStreaming = ref(false)

  function send(onChunk: (text: string) => void, onDone: () => void) {
    const text = inputText.value.trim()
    if (!text || isStreaming.value) return

    messages.value.push({ role: 'user', content: text })
    inputText.value = ''

    const assistantMsg: ChatMessage = { role: 'assistant', content: '', streaming: true }
    messages.value.push(assistantMsg)
    isStreaming.value = true

    const history = messages.value
      .filter(m => !m.streaming)
      .map(m => ({ role: m.role, content: m.content }))

    chatStream(
      userId,
      text,
      history,
      (chunk) => {
        assistantMsg.content += chunk
        onChunk(chunk)
      },
      () => {
        assistantMsg.streaming = false
        isStreaming.value = false
        onDone()
      },
      (err) => {
        assistantMsg.content = `[错误] ${err.message}`
        assistantMsg.streaming = false
        isStreaming.value = false
        onDone()
      },
    )
  }

  function clear() {
    messages.value = []
  }

  return { messages, inputText, isStreaming, send, clear }
}
