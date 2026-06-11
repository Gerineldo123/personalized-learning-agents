import type { StepEvent } from '../types/agent'

export async function uploadFile(file: File): Promise<{ ok: boolean; file_name: string; content: string; size: number; error?: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await fetch('/api/agent/upload', { method: 'POST', body: formData })
  return resp.json()
}

export function agentExecuteStream(
  userId: string,
  taskDescription: string,
  onStep: (step: StepEvent) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  fileContent?: string,
  fileName?: string,
): AbortController {
  const controller = new AbortController()

  fetch('/api/agent/execute/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      task_description: taskDescription,
      file_content: fileContent || null,
      file_name: fileName || null,
    }),
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
          const dataLines = event
            .split('\n')
            .filter((l) => l.startsWith('data: '))
            .map((l) => l.slice(6))
          if (dataLines.length > 0) {
            const raw = dataLines.join('\n')
            try {
              const parsed = JSON.parse(raw)
              if (parsed.type === 'step') {
                onStep(parsed as StepEvent)
              }
            } catch {
              console.warn('Failed to parse SSE data:', raw)
            }
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
