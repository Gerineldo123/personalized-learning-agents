export function chatStream(
  userId: string,
  message: string,
  history: { role: string; content: string }[],
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onStage?: (stage: string, data: any) => void,
  sessionId?: string,
) {
  const controller = new AbortController()

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, message, history, session_id: sessionId }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        let eventEnd: number
        while ((eventEnd = buffer.indexOf('\n\n')) !== -1) {
          const event = buffer.slice(0, eventEnd)
          buffer = buffer.slice(eventEnd + 2)

          const dataLines = event.split('\n')
            .filter(l => l.startsWith('data: '))
            .map(l => l.slice(6))

          if (dataLines.length > 0) {
            const raw = dataLines.join('\n')
            // 尝试解析 stage 事件
            try {
              const parsed = JSON.parse(raw)
              if (parsed.type === 'stage' && onStage) {
                onStage(parsed.stage, parsed.data)
                continue
              }
            } catch {}
            onChunk(raw)
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err)
    })

  return controller
}
