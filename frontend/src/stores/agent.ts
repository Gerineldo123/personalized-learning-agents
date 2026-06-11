import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { AgentTask, AgentStep } from '../types/agent'

export const useAgentStore = defineStore('agent', () => {
  const tasks = ref<AgentTask[]>([])
  const currentTaskId = ref<number | null>(null)
  const isExecuting = ref(false)
  const abortController = ref<AbortController | null>(null)

  const currentTask = computed(() =>
    tasks.value.find((t) => t.id === currentTaskId.value) || null,
  )

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
    cancelExecution,
    setAbortController,
  }
})
