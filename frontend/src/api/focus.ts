import api from './index'

export interface FocusSessionPayload {
  started_at: string
  duration_min: number
  completed: boolean
}

export function reportFocusSession(userId: string, payload: FocusSessionPayload) {
  return api.post(`/focus/session?user_id=${encodeURIComponent(userId)}`, payload)
}
