export const skillNameMap: Record<string, string> = {
  deep_search: '搜索智能体',
  code_analysis: '代码分析智能体',
  code_gen: '代码/动画智能体',
  article_gen: '文章智能体',
  mindmap_gen: '导图智能体',
  quiz_gen: '出题智能体',
  video_search: '视频智能体',
  ppt_gen: '课件智能体',
  resource_orchestration: '资源编排',
}

export const skillIconMap: Record<string, string> = {
  deep_search: '🔎',
  code_analysis: '💻',
  code_gen: '💻',
  article_gen: '📄',
  mindmap_gen: '🧠',
  quiz_gen: '📝',
  video_search: '🎬',
  ppt_gen: '📊',
  resource_orchestration: '📦',
}

export function skillDisplayName(skillName?: string, fallback = '任务智能体') {
  if (!skillName) return fallback
  return skillNameMap[skillName] || skillName
}

export function skillDisplayIcon(skillName?: string, fallback = '🔧') {
  if (!skillName) return fallback
  return skillIconMap[skillName] || fallback
}

export function normalizeAgentName(name?: string) {
  if (!name) return ''
  const map: Record<string, string> = {
    OrchestratorAgent: '资源编排智能体',
    ContentGenAgent: '内容生成智能体',
    MindMapAgent: '导图智能体',
    VideoAgent: '视频智能体',
    EvaluationAgent: '评价智能体',
    ProfileAgent: '画像智能体',
  }
  return map[name] || name
}
