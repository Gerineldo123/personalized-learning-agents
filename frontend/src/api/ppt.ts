import api from './index'

export interface CreateSessionParams {
  user_id: string
  topic: string
  course_name?: string
  knowledge_points?: string[]
}

export interface CreateSessionResult {
  session_id: string
  token: string
  expires_at: string
  topic?: string
  course_name?: string
  knowledge_points?: string[]
  scope?: 'graph' | 'extension'
  embed_config: {
    base_url: string
    token: string
    sdk_url?: string
    domain?: string
  }
}

export interface PptBindingCandidate {
  course_name: string
  knowledge_points: string[]
  source: string
  confidence: number
}

export interface PptBindingResult {
  status: 'auto_bound' | 'needs_choice' | 'extension_confirm'
  topic: string
  binding: PptBindingCandidate | null
  candidates: PptBindingCandidate[]
  message?: string
}

export interface LaunchSessionResult {
  found: boolean
  session_id: string
  status: string
  topic: string
  course_name?: string
  knowledge_points?: string[]
  scope?: 'graph' | 'extension'
  resource_id?: number
  embed_config?: CreateSessionResult['embed_config']
}

export interface CompleteSessionParams {
  user_id: string
  ppt_id: string
  subject?: string
  cover_url?: string
  template_id?: string
}

export interface PptResource {
  id: number
  title: string
  resource_type: string
  course_name: string
  knowledge_points: string[]
  pptx_url: string
  cover_url?: string
}

export interface CompleteSessionResult {
  ok: boolean
  resource?: PptResource
  resource_id?: number
  status?: string
}

export interface SessionStatus {
  found: boolean
  session_id: string
  status: string
  ppt_id?: string
  cover_url?: string
  template_id?: string
  resource_id?: number
  error_message?: string
  created_at?: string
  updated_at?: string
}

export function createPptSession(params: CreateSessionParams): Promise<CreateSessionResult> {
  return api.post('/ppt/sessions', params).then(r => r.data)
}

export function resolvePptBinding(params: { user_id: string; topic: string; context?: string }): Promise<PptBindingResult> {
  return api.post('/ppt/resolve-binding', params).then(r => r.data)
}

export function completePptSession(sessionId: string, params: CompleteSessionParams): Promise<CompleteSessionResult> {
  return api.post(`/ppt/sessions/${sessionId}/complete`, params).then(r => r.data)
}

export function launchPptSession(sessionId: string, userId: string): Promise<LaunchSessionResult> {
  return api.get(`/ppt/sessions/${sessionId}/launch`, { params: { user_id: userId } }).then(r => r.data)
}

export function getPptSessionStatus(sessionId: string, userId: string): Promise<SessionStatus> {
  return api.get(`/ppt/sessions/${sessionId}/status`, { params: { user_id: userId } }).then(r => r.data)
}
