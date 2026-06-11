# AI Agent 任务执行面板开发步骤

> 基于现有 Vue 3 + Element Plus + Pinia 技术栈，在现有 AI 对话模块基础上新增 Agent 任务执行面板。
> 原则：每一步可独立验证，逐步替换/增强现有 ChatView。

---

## 总体架构

```
┌─────────────────────────────────────────────────────────┐
│  AgentPanelView.vue                                     │
│  ┌──────────────┐  ┌────────────────────────────────┐   │
│  │ 左侧面板      │  │ 主工作区                        │   │
│  │ - 任务列表    │  │ ┌────────────────────────────┐ │   │
│  │ - 新建任务    │  │ │ 任务标题栏                  │ │   │
│  │ - 历史会话    │  │ ├────────────────────────────┤ │   │
│  │              │  │ │ 时间线/步骤流               │ │   │
│  │              │  │ │  ├─ ThinkingStep            │ │   │
│  │              │  │ │  ├─ SearchStep (Tavily)     │ │   │
│  │              │  │ │  ├─ MemoryStep              │ │   │
│  │              │  │ │  ├─ CodeStep (Sandbox)      │ │   │
│  │              │  │ │  └─ ResultStep              │ │   │
│  │              │  │ ├────────────────────────────┤ │   │
│  │              │  │ │ 输入区                      │ │   │
│  │              │  │ └────────────────────────────┘ │   │
│  └──────────────┘  └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**新增依赖：**
- `mermaid` — 流程图/时序图渲染
- `@codemirror/view` + `@codemirror/lang-javascript` + `@codemirror/lang-python` — 代码编辑器
- `@codemirror/theme-one-dark` — 深色代码主题
- `tavily` (后端 Python 包) — Tavily 搜索 API

---

## 第一阶段：后端 — Agent 工具扩展与结构化输出（预计 2 天）

### 1.1 集成 Tavily 搜索工具

**文件：** `backend/agents/tools.py`

```python
# 新增 Tavily 搜索工具
import httpx

async def tavily_search(query: str, max_results: int = 5) -> dict:
    """调用 Tavily Search API"""
    api_key = os.getenv("TAVILY_API_KEY")
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://api.tavily.com/search", json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": True,
        })
        return resp.json()
```

**操作步骤：**
1. 在 `backend/.env` 中添加 `TAVILY_API_KEY=tvly-xxx`
2. 在 `tools.py` 中新增 `tavily_search` 函数
3. 在 `TOOLS` 列表中注册该工具
4. `pip install tavily-python` 并更新 `requirements.txt`

**验证：** 编写 `backend/tests/test_tavily.py`，调用 `tavily_search("fibonacci sequence")` 确认返回结构

---

### 1.2 新增网页抓取工具

**文件：** `backend/agents/tools.py`

```python
async def web_scrape(url: str) -> dict:
    """抓取网页内容摘要"""
    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        resp = await client.get(url)
        # 简单提取纯文本前 2000 字符
        from html.parser import HTMLParser
        # ... 解析逻辑
        return {"url": url, "content": extracted_text[:2000], "status": resp.status_code}
```

**验证：** 测试抓取一个公开网页，确认返回内容

---

### 1.3 重构 Workflow Streaming 输出协议

**目标：** 让前端能区分不同类型的步骤事件，统一 SSE 消息格式。

**文件：** `backend/core/sse.py`（新建或修改现有 `sse_stream`）

**统一事件格式：**
```json
{
  "type": "step",
  "step_type": "thinking | search | memory | code | scrape | result",
  "step_id": "uuid",
  "status": "running | completed | error",
  "title": "步骤标题",
  "data": { ... }
}
```

各 step_type 的 data 结构：
- `thinking`: `{ "content": "流式文本（增量）" }`
- `search`: `{ "query": "...", "results": [{ "title", "url", "snippet" }], "answer": "..." }`
- `memory`: `{ "action": "read | write", "key": "...", "value": "..." }`
- `code`: `{ "language": "javascript | python", "code": "...", "output": "...", "status": "running | completed | error" }`
- `scrape`: `{ "url": "...", "content": "..." }`
- `result`: `{ "content": "Markdown 最终结果" }`

**操作步骤：**
1. 定义 `StepEvent` Pydantic schema
2. 修改 `_stream_subgraph` 函数，在每个 node 执行前后发送对应事件
3. 对 `thinking` 类型支持增量推送（每产生一段文本就推送一次）

**验证：** 用 curl 调用 `/api/workflow/study/stream`，确认输出符合新协议格式

---

### 1.4 新建 Agent 执行路由

**文件：** `backend/api/routes/agent_panel.py`

```python
router = APIRouter(prefix="/api/agent", tags=["Agent面板"])

@router.post("/execute/stream")
async def execute_stream(req: AgentExecuteRequest):
    """执行一个 Agent 任务，流式返回步骤"""
    # 编排工具调用顺序，每个步骤通过 SSE 推送
    ...
```

**操作步骤：**
1. 新建路由文件，注册到 `main.py`
2. 定义请求 schema: `{ user_id, task_description, conversation_id? }`
3. 实现编排逻辑：thinking → search → memory → code → result

**验证：** Postman/curl 调用 `/api/agent/execute/stream`，确认多步骤 SSE 输出

---

## 第二阶段：前端 — 基础布局与组件（预计 2 天）

### 2.1 新建路由和页面骨架

**文件：** `frontend/src/views/AgentPanelView.vue`

**操作步骤：**
1. 在 `router.ts` 中添加 `/agent` 路由指向 `AgentPanelView.vue`
2. 在 `App.vue` 侧边导航中添加 "Agent 面板" 入口
3. 实现基础三栏布局：左侧任务列表 + 右侧主工作区（标题栏 + 时间线 + 输入区）

**骨架结构：**
```vue
<template>
  <div class="agent-panel">
    <aside class="task-sidebar"><!-- 任务列表 --></aside>
    <main class="work-area">
      <header class="task-header"><!-- 任务标题 --></header>
      <div class="timeline-container"><!-- 步骤时间线 --></div>
      <div class="input-area"><!-- 用户输入 --></div>
    </main>
  </div>
</template>
```

**验证：** 访问 `/agent` 页面，确认布局正确渲染

---

### 2.2 定义前端数据类型

**文件：** `frontend/src/types/agent.ts`（新建）

```typescript
export type StepType = 'thinking' | 'search' | 'memory' | 'code' | 'scrape' | 'result'
export type StepStatus = 'running' | 'completed' | 'error'

export interface AgentStep {
  stepId: string
  stepType: StepType
  status: StepStatus
  title: string
  data: ThinkingData | SearchData | MemoryData | CodeData | ScrapeData | ResultData
  expanded: boolean
  timestamp: number
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
  content: string  // Markdown
}

export interface AgentTask {
  id: number
  title: string
  status: 'idle' | 'running' | 'completed'
  steps: AgentStep[]
  createdAt: string
}
```

**验证：** TypeScript 编译无报错

---

### 2.3 创建 Pinia Store

**文件：** `frontend/src/stores/agent.ts`（新建）

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentTask, AgentStep } from '../types/agent'

export const useAgentStore = defineStore('agent', () => {
  const tasks = ref<AgentTask[]>([])
  const currentTaskId = ref<number | null>(null)
  const isExecuting = ref(false)

  // CRUD 操作
  function createTask(title: string): AgentTask { ... }
  function addStep(taskId: number, step: AgentStep) { ... }
  function updateStep(taskId: number, stepId: string, partial: Partial<AgentStep>) { ... }

  return { tasks, currentTaskId, isExecuting, createTask, addStep, updateStep }
})
```

**验证：** 在 Vue DevTools 中确认 store 正确初始化

---

### 2.4 实现 SSE 通信层

**文件：** `frontend/src/api/agent.ts`（新建）

```typescript
export function agentExecuteStream(
  userId: string,
  taskDescription: string,
  onStep: (step: StepEvent) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  // 类似现有 workflowStream，但解析新的 step 协议
  ...
}
```

**验证：** 配合后端 `/api/agent/execute/stream` 接口，确认事件正确解析

---

## 第三阶段：前端 — 步骤组件实现（预计 3 天）

### 3.1 时间线容器组件

**文件：** `frontend/src/components/agent/AgentTimeline.vue`

- 竖线时间轴连接各步骤
- 每个步骤渲染为一个卡片，左侧带状态图标
- 步骤图标映射：🦉 thinking, 🔍 search, 💻 code, 📝 memory, 🌐 scrape, ✅ result
- 支持展开/收起

**验证：** 传入 mock 步骤数据，确认时间线渲染正确

---

### 3.2 思考步骤组件 — 流式打字机效果

**文件：** `frontend/src/components/agent/steps/ThinkingStep.vue`

```vue
<template>
  <div class="thinking-step">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">🦉</span>
      <span class="step-title">{{ title }}</span>
      <el-icon><ArrowDown v-if="!expanded" /><ArrowUp v-else /></el-icon>
    </div>
    <div v-show="expanded" class="step-content typewriter">
      {{ displayedContent }}
      <span v-if="status === 'running'" class="cursor-blink">|</span>
    </div>
  </div>
</template>
```

**关键实现：**
- 通过 `watch` 监听 `data.content` 变化，逐字符追加到 `displayedContent`
- 使用 CSS 动画实现光标闪烁
- status 为 running 时显示光标，completed 时隐藏

**验证：** 模拟增量文本推送，确认打字机效果流畅

---

### 3.3 搜索步骤组件（Tavily 结果展示）

**文件：** `frontend/src/components/agent/steps/SearchStep.vue`

```vue
<template>
  <div class="search-step">
    <div class="step-header" @click="toggleExpand">
      <span class="step-icon">🔍</span>
      <span class="step-title">Tavily Search: {{ data.query }}</span>
      <el-tag size="small" :type="status === 'completed' ? 'success' : 'info'">
        {{ status === 'completed' ? 'done' : 'searching...' }}
      </el-tag>
    </div>
    <div v-show="expanded" class="step-content">
      <div v-if="data.answer" class="search-answer">{{ data.answer }}</div>
      <div class="search-results">
        <div v-for="r in data.results" :key="r.url" class="result-item">
          <a :href="r.url" target="_blank" rel="noopener">{{ r.title }}</a>
          <p class="snippet">{{ r.snippet }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
```

**验证：** 传入模拟搜索结果数据，确认链接可点击跳转新标签页

---

### 3.4 代码执行步骤组件（Code Sandbox）

**文件：** `frontend/src/components/agent/steps/CodeStep.vue`

**功能：**
- 顶部标签页切换语言（JavaScript / Python）
- 代码区使用 CodeMirror 深色主题，带行号和语法高亮
- 下方分栏：Output / Console
- 右上角复制按钮、折叠按钮
- 执行状态指示器（Running 旋转图标 / Completed 绿色 / Error 红色）

**依赖安装：**
```bash
cd frontend
npm install @codemirror/view @codemirror/state @codemirror/lang-javascript @codemirror/lang-python @codemirror/theme-one-dark
```

**验证：** 渲染一段 Python 代码，确认语法高亮、行号、复制功能正常

---

### 3.5 记忆更新步骤组件

**文件：** `frontend/src/components/agent/steps/MemoryStep.vue`

- 展示记忆操作类型（Read / Write）
- 展示 key-value 对
- Write 操作用绿色标记，Read 操作用蓝色标记

**验证：** 传入 mock 数据确认渲染

---

### 3.6 网页抓取步骤组件

**文件：** `frontend/src/components/agent/steps/ScrapeStep.vue`

- 展示目标 URL（可点击）
- 展示提取的内容片段（截断 + 展开更多）

**验证：** 传入 mock 数据确认渲染

---

### 3.7 最终结果步骤组件

**文件：** `frontend/src/components/agent/steps/ResultStep.vue`

- 使用现有 `markdown-it` + KaTeX 渲染 Markdown 内容
- 新增 Mermaid 图表渲染支持
- 支持表格、列表、引用块、代码块

**Mermaid 集成：**
```bash
npm install mermaid
```

在 Markdown 渲染流程中，识别 ` ```mermaid ` 代码块，替换为 Mermaid 渲染容器。

**验证：** 渲染包含 KaTeX 公式 + Mermaid 流程图的 Markdown 内容

---

## 第四阶段：交互增强与主题（预计 1.5 天）

### 4.1 深色/浅色模式切换

**操作步骤：**
1. 在 `stores/` 中新建 `theme.ts`，管理主题状态
2. 利用 Element Plus 内置 dark mode：`document.documentElement.classList.toggle('dark')`
3. 在顶部工具栏添加切换按钮
4. 为 Agent 面板的自定义样式编写 `.dark` 变体

**验证：** 切换主题，确认所有组件样式正确响应

---

### 4.2 响应式布局

**操作步骤：**
1. 左侧面板在移动端默认隐藏，通过汉堡菜单触发
2. 步骤卡片在窄屏下全宽展示
3. CodeMirror 编辑器自适应宽度

**CSS 断点：**
```css
@media (max-width: 768px) {
  .agent-panel { flex-direction: column; }
  .task-sidebar { position: fixed; z-index: 100; transform: translateX(-100%); }
  .task-sidebar.visible { transform: translateX(0); }
}
```

**验证：** 在 Chrome DevTools 模拟移动端，确认布局自适应

---

### 4.3 步骤卡片交互优化

- 默认所有步骤收起，只显示标题 + 状态图标
- 当前正在执行的步骤自动展开
- 点击切换展开/收起，带平滑过渡动画
- 新步骤出现时自动滚动到底部

**验证：** 执行一个完整任务流，确认交互流畅

---

## 第五阶段：Mock 数据流演示（预计 1 天）

### 5.1 模拟完整 Agent 任务数据

**文件：** `frontend/src/mock/agentDemo.ts`（新建）

模拟"斐波那契数列跨学科分析"任务，包含以下步骤序列：

```typescript
export const demoSteps: AgentStep[] = [
  // 1. 思考 — 提取任务清单
  { stepType: 'thinking', title: '分析任务需求', data: { content: '用户请求分析斐波那契数列...' } },
  // 2. 搜索 — Tavily 调用
  { stepType: 'search', title: 'Tavily Search: Fibonacci sequence applications', data: { query: '...', results: [...] } },
  // 3. 记忆更新
  { stepType: 'memory', title: '更新知识库', data: { action: 'write', key: 'fibonacci_research', value: '...' } },
  // 4. 代码执行 — Node.js 计算
  { stepType: 'code', title: '计算斐波那契数列', data: { language: 'javascript', code: '...', output: '...' } },
  // 5. 网页抓取 — 论文提取
  { stepType: 'scrape', title: '提取论文内容', data: { url: 'https://...', content: '...' } },
  // 6. 最终结果汇总
  { stepType: 'result', title: '分析报告', data: { content: '## 斐波那契数列跨学科分析\n...' } },
]
```

### 5.2 实现前端演示模式

在 `AgentPanelView.vue` 中添加"演示模式"按钮：
- 点击后按时间间隔逐步推送 mock 步骤数据
- 思考步骤使用逐字符推送模拟打字机效果
- 各步骤间隔 1-2 秒

**验证：** 点击演示按钮，确认完整流程动画展示正常

---

## 第六阶段：后端 Agent 编排逻辑完善（预计 2 天）

### 6.1 创建 Agent 执行子图

**文件：** `backend/graph/subgraphs/agent_execute.py`（新建）

使用 LangGraph 编排以下节点：
1. `plan_node` — LLM 分析用户请求，生成执行计划
2. `search_node` — 调用 Tavily 搜索
3. `memory_node` — 读写 ChromaDB 知识库
4. `code_node` — 执行代码（预设安全沙箱或模拟）
5. `scrape_node` — 抓取网页
6. `summarize_node` — 汇总最终结果

每个节点执行时通过 `workflow_outputs` 推送 StepEvent。

**验证：** 单元测试各节点，集成测试完整子图流程

---

### 6.2 代码执行沙箱（安全方案）

**初期方案：** 仅支持预定义代码模板的执行结果展示（模拟）

**后续可选：**
- 接入 Jupyter kernel（通过 `jupyter_client`）
- Docker 容器隔离执行
- 限制执行时间和资源

**当前实现：** 后端将代码和预期输出一起返回给前端，前端只做展示，不执行。

---

## 第七阶段：联调与测试（预计 1.5 天）

### 7.1 前后端联调

1. 启动后端 `uvicorn main:app --reload`
2. 启动前端 `npm run dev`
3. 在 `/agent` 页面输入任务描述
4. 确认 SSE 流式推送到前端，各步骤组件正确渲染
5. 测试异常情况：网络断开、API 超时、工具调用失败

### 7.2 验收清单

- [ ] 左侧任务列表正确显示历史任务
- [ ] 时间线步骤按顺序展示，竖线连接
- [ ] 思考步骤有打字机效果
- [ ] 搜索结果链接在新标签页打开
- [ ] 代码块有语法高亮、行号、复制按钮
- [ ] KaTeX 公式正确渲染（行内 + 块级）
- [ ] Mermaid 图表正确渲染
- [ ] 深色/浅色模式切换正常
- [ ] 移动端响应式布局正常
- [ ] 步骤卡片展开/收起动画流畅
- [ ] 演示模式完整运行无报错

---

## 文件变更清单

### 后端新增/修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/.env` | 修改 | 添加 TAVILY_API_KEY |
| `backend/requirements.txt` | 修改 | 添加 tavily-python, beautifulsoup4 |
| `backend/agents/tools.py` | 修改 | 添加 tavily_search, web_scrape 工具 |
| `backend/api/routes/agent_panel.py` | 新建 | Agent 执行流式接口 |
| `backend/main.py` | 修改 | 注册 agent_panel 路由 |
| `backend/schemas/agent.py` | 新建 | StepEvent, AgentExecuteRequest 等 schema |
| `backend/graph/subgraphs/agent_execute.py` | 新建 | Agent 执行子图 |

### 前端新增/修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/package.json` | 修改 | 添加 mermaid, codemirror 依赖 |
| `frontend/src/router.ts` | 修改 | 添加 /agent 路由 |
| `frontend/src/App.vue` | 修改 | 侧边栏添加 Agent 面板入口 |
| `frontend/src/types/agent.ts` | 新建 | 类型定义 |
| `frontend/src/stores/agent.ts` | 新建 | Agent 状态管理 |
| `frontend/src/stores/theme.ts` | 新建 | 主题状态管理 |
| `frontend/src/api/agent.ts` | 新建 | Agent SSE 通信层 |
| `frontend/src/views/AgentPanelView.vue` | 新建 | 页面入口 |
| `frontend/src/components/agent/AgentTimeline.vue` | 新建 | 时间线容器 |
| `frontend/src/components/agent/steps/ThinkingStep.vue` | 新建 | 思考步骤 |
| `frontend/src/components/agent/steps/SearchStep.vue` | 新建 | 搜索步骤 |
| `frontend/src/components/agent/steps/CodeStep.vue` | 新建 | 代码步骤 |
| `frontend/src/components/agent/steps/MemoryStep.vue` | 新建 | 记忆步骤 |
| `frontend/src/components/agent/steps/ScrapeStep.vue` | 新建 | 网页抓取步骤 |
| `frontend/src/components/agent/steps/ResultStep.vue` | 新建 | 最终结果步骤 |
| `frontend/src/mock/agentDemo.ts` | 新建 | 演示数据 |

---

## 预估工时

| 阶段 | 内容 | 工时 |
|------|------|------|
| 第一阶段 | 后端工具扩展与结构化输出 | 2 天 |
| 第二阶段 | 前端基础布局与组件骨架 | 2 天 |
| 第三阶段 | 步骤组件实现 | 3 天 |
| 第四阶段 | 交互增强与主题 | 1.5 天 |
| 第五阶段 | Mock 数据流演示 | 1 天 |
| 第六阶段 | 后端 Agent 编排完善 | 2 天 |
| 第七阶段 | 联调与测试 | 1.5 天 |
| **合计** | | **约 13 天** |

> 建议开发顺序：第二阶段 → 第三阶段 → 第五阶段（先做前端 + mock 验证 UI），然后第一阶段 → 第六阶段（后端），最后第四阶段 → 第七阶段。这样可以前后端并行开发。
