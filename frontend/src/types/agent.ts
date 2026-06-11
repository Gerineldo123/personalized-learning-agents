export type StepType = 'thinking' | 'search' | 'memory' | 'code' | 'scrape' | 'result'
export type StepStatus = 'running' | 'completed' | 'error'

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
  language: 'javascript' | 'python'
  code: string
  output: string
  status: 'running' | 'completed' | 'error'
}

export interface ScrapeData {
  url: string
  content: string
}

export interface ResultData {
  content: string
}

export interface AgentStep {
  stepId: string
  stepType: StepType
  status: StepStatus
  title: string
  data: ThinkingData | SearchData | MemoryData | CodeData | ScrapeData | ResultData
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
  data: Record<string, unknown>
}

export interface UploadedFile {
  fileName: string
  content: string
  size: number
}
