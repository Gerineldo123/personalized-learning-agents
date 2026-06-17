import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { AgentTask, AgentStep } from '../types/agent'

const STORAGE_KEY = 'agent_tasks'
const STORAGE_CURRENT_KEY = 'agent_current_task_id'

function loadTasks(): AgentTask[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return []
}

function saveTasks(tasks: AgentTask[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks))
  } catch {}
}

function loadCurrentTaskId(): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_CURRENT_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return null
}

function saveCurrentTaskId(id: number | null) {
  try {
    localStorage.setItem(STORAGE_CURRENT_KEY, JSON.stringify(id))
  } catch {}
}

export const useAgentStore = defineStore('agent', () => {
  const tasks = ref<AgentTask[]>(loadTasks())
  const currentTaskId = ref<number | null>(loadCurrentTaskId())
  const isExecuting = ref(false)
  const abortController = ref<AbortController | null>(null)

  const currentTask = computed(() =>
    tasks.value.find((t) => t.id === currentTaskId.value) || null,
  )

  // 持久化：监听 tasks 和 currentTaskId 变化自动保存
  watch(tasks, (val) => saveTasks(val), { deep: true })
  watch(currentTaskId, (val) => saveCurrentTaskId(val))

  function createTask(title: string): AgentTask {
    const task: AgentTask = {
      id: Date.now(),
      title,
      status: 'idle',
      steps: [],
      createdAt: new Date().toISOString(),
    }
    tasks.value.unshift(task)
    currentTaskId.value = task.id
    return task
  }

  function setTaskStatus(taskId: number, status: AgentTask['status']) {
    const task = tasks.value.find((t) => t.id === taskId)
    if (task) task.status = status
  }

  function addStep(taskId: number, step: AgentStep) {
    const task = tasks.value.find((t) => t.id === taskId)
    if (task) task.steps.push(step)
  }

  function upsertStep(taskId: number, step: AgentStep) {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return
    const idx = task.steps.findIndex((s) => s.stepId === step.stepId)
    if (idx >= 0) {
      task.steps[idx] = { ...task.steps[idx], ...step, data: { ...task.steps[idx].data, ...step.data } as AgentStep['data'] }
    } else {
      task.steps.push(step)
    }
  }

  function updateStep(taskId: number, stepId: string, partial: Partial<AgentStep>) {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return
    const step = task.steps.find((s) => s.stepId === stepId)
    if (step) {
      Object.assign(step, partial)
    }
  }

  function appendStepContent(taskId: number, stepId: string, delta: string) {
    const task = tasks.value.find((t) => t.id === taskId)
    if (!task) return
    const step = task.steps.find((s) => s.stepId === stepId)
    if (step) {
      (step.data as any).content = ((step.data as any).content || '') + delta
    }
  }

  function cancelExecution() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    isExecuting.value = false
  }

  function setAbortController(ctrl: AbortController) {
    abortController.value = ctrl
  }

  return {
    tasks,
    currentTaskId,
    isExecuting,
    currentTask,
    createTask,
    setTaskStatus,
    addStep,
    upsertStep,
    updateStep,
    appendStepContent,
    cancelExecution,
    setAbortController,
  }
})
