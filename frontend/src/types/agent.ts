export type StepType = 'user' | 'thinking' | 'search' | 'memory' | 'code' | 'scrape' | 'skill' | 'result'
export type StepStatus = 'running' | 'completed' | 'error'

export interface UserData {
  content: string
  fileName?: string
}

export interface ThinkingData {
  content: string
}

export interface SearchData {
  query: string
  results: Array<{ title: string; url: string; snippet: string }>
  answer?: string
}

export interface MemoryData {
  action: 'read' | 'write'
  key: string
  value: string
}

export interface CodeData {
  language: 'javascript' | 'python' | 'cpp' | 'c' | 'java' | string
  code: string
  output: string
  status: 'running' | 'completed' | 'error'
}

export interface ScrapeData {
  url: string
  content: string
}

export interface SkillData {
  skill_name: string
  skill_icon: string
  content: string
  sub_steps: string[]
  language?: string
  render_type?: string
  progress?: number
  current_phase?: string
  progress_note?: string
  progress_indeterminate?: boolean
  progress_label?: string
  streaming_code?: boolean
  draft_resource?: {
    client_draft_id: string
    resource_type: string
    title: string
    content: unknown
    course_name?: string | null
    knowledge_points?: string[]
    kp_weights?: Record<string, number>
    save_required?: boolean
  } | null
}

export interface ResultData {
  content: string
}

export interface AgentStep {
  stepId: string
  stepType: StepType
  status: StepStatus
  title: string
  agentName?: string
  data: UserData | ThinkingData | SearchData | MemoryData | CodeData | ScrapeData | SkillData | ResultData
  expanded: boolean
  timestamp: number
}

export interface AgentTask {
  id: number
  title: string
  status: 'idle' | 'running' | 'completed'
  steps: AgentStep[]
  createdAt: string
}

export interface StepEvent {
  type: string
  step_type: StepType
  step_id: string
  status: StepStatus
  title: string
  agent_name?: string
  data: Record<string, unknown>
}

export interface UploadedFile {
  fileName: string
  content: string
  size: number
}
