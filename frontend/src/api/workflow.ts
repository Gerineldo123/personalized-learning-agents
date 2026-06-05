export type WorkflowType = 'study' | 'review' | 'evaluation' | 'video'

export function workflowStream(
  type: WorkflowType,
  userId: string,
  topic: string,
  history: { role: string; content: string }[],
  onChunk: (text: string) => void,
  onStage: (stage: string, data: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
) {
  const controller = new AbortController()

  fetch(`/api/workflow/${type}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, topic, history }),
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
          const dataLines = event.split('\n').filter(l => l.startsWith('data: ')).map(l => l.slice(6))
          if (dataLines.length > 0) {
            const raw = dataLines.join('\n')
            try {
              const parsed = JSON.parse(raw)
              if (parsed.type === 'stage') { onStage(parsed.stage, parsed.data); continue }
            } catch {}
            onChunk(raw)
          }
        }
      }
      onDone()
    })
    .catch((err) => { if (err.name !== 'AbortError') onError(err) })

  return controller
}
