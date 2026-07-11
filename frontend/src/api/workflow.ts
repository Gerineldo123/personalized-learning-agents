import type { AgentCollaborationEvent } from '../types/agent'

export type WorkflowType = 'study' | 'review' | 'evaluation' | 'video'

export interface ResourceEvent {
  resource_id?: number | null
  resource_type: string
  title: string
  ppt_session?: any
  status?: string
}

export function workflowStream(
  type: WorkflowType,
  userId: string,
  topic: string,
  history: { role: string; content: string }[],
  onChunk: (text: string) => void,
  onStage: (stage: string, data: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onResource?: (resource: ResourceEvent) => void,
  onAgentEvent?: (event: AgentCollaborationEvent) => void,
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
              if (parsed.type === 'agent_event' && onAgentEvent) {
                onAgentEvent(parsed.event as AgentCollaborationEvent)
                continue
              }
              if (parsed.type === 'resource' && onResource) {
                onResource({
                  resource_id: parsed.resource_id,
                  resource_type: parsed.resource_type,
                  title: parsed.title,
                  ppt_session: parsed.ppt_session,
                  status: parsed.status,
                })
                continue
              }
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
