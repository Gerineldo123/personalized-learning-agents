# LangGraph 多 Agent 协作改造方案

## 概述

当前系统采用「一次意图分类 → 一条静态节点链 → 一个结果」的路由分发模式——Agent 之间零通信，工作流链硬编码，无法根据中间结果动态调整策略。

本文档描述如何基于 LangGraph 的核心图原语（`StateGraph` + `conditional_edges` + 状态驱动通信），将系统升级为真正的 **Supervisor-Worker 多 Agent 协作架构**。

### 当前架构 vs 目标架构

```
【当前：路由式单 Agent 分发】          【目标：Supervisor-Worker 协作】

START                                   START
  │                                       │
intent_classifier (一次分类)           supervisor (制定计划)
  │                                       │
  ├→ chat → END                       ┌───▼──dispatch──┐
  ├→ profile → END                    │  profile_analysis│────┐
  ├→ content_gen → END                └──────────────────┘    │
  ├→ mindmap → END                         │                  │
  ├→ evaluation → ...固定链...          反馈写入 state         │
  ├→ study → ...固定链...              ◄─────────────────────┘
  └→ review → ...固定链...                   │
                                    ┌──────▼──dispatch──┐
Agent之间：零通信                     │   study_content   │────┐
路由：硬编码                           └──────────────────┘    │
状态：仅用于节点间传递                      │                  │
                                    反馈写入 state (含质量信号)  │
                                    ◄─────────────────────────┘
                                              │
                                    ┌──────▼──决策────────┐
                                    │ supervisor 读取反馈  │
                                    │ 质量不够？→ 重新生成  │
                                    │ 有薄弱点？→ 补充练习  │
                                    │ 全部完成？→ summary  │
                                    └──────┬─────────────┘
                                       ...循环直至完成...

Agent之间：通过共享 State 字段通信
路由：supervisor 根据实时反馈动态决策
状态：Agent 既是消费者也是生产者
```

### 设计原则

1. **零 LangChain 依赖**——项目使用原生 `openai` SDK + 讯飞星火 API，不引入 LangChain chat model，所有 Agent 逻辑用 LangGraph 的 `StateGraph` 节点 + 标准异步函数实现。
2. **渐进式改造**——现有 5 个 Agent 类的 `process()` 方法保持不变，仅改造图拓扑 + 节点适配层 + State 结构。
3. **状态驱动的通信**——Agent 之间不直接调用，通过写入/读取 `AgentGraphState` 的特定字段完成信息传递和信号下发。

---

## 第一阶段：基础改造

### 1.1 State 扩展 — `graph/state.py`

新增多 Agent 协作所需的字段。Agent 之间通过 State 字段隐式通信——worker 写入反馈信号，supervisor 读取后决策下一步。

```python
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class AgentGraphState(TypedDict):
    # ===================== 现有字段（保留） =====================
    user_id: str
    user_message: str
    profile: Any
    history: list[dict]
    messages: Annotated[list, add_messages]
    response: str
    agent_name: str

    # Phase 2 工作流中间数据
    profile_analysis: dict
    generated_article: str
    generated_mindmap: str
    generated_quiz: dict
    evaluation_report: dict
    mistake_analysis: dict
    path_suggestion: str
    workflow_outputs: list[dict]

    # ===================== Phase 3 新增：多 Agent 协作 =====================
    # supervisor 制定的执行计划
    task_plan: list[dict]
    # 当前正在执行的任务标识
    current_task: str
    # worker agent 完成后写入的反馈信号
    # 例：{"content_quality": 0.8, "needs_mindmap": True, "weaknesses_found": [...], "errors_detected": True}
    agent_feedback: dict
    # supervisor 循环计数（防止无限循环）
    supervisor_iteration: int
    # 已完成的任务列表 [{"agent": "profile_analysis", "result_summary": "..."}, ...]
    completed_tasks: list[dict]
```

**`agent_feedback` 字段设计说明**

这是 Agent 间通信的核心载体。每个 worker 节点完成后向 State 写入一个结构化的反馈字典，supervisor 根据其中的标志位决定下一步调度。

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `content_generated` | `bool` | 内容已生成 | `true` |
| `content_quality` | `float` | 内容质量评分 0-1 | `0.7` |
| `needs_regeneration` | `bool` | 需要重新生成（质量太低） | `false` |
| `needs_mindmap` | `bool` | 建议生成思维导图（初级学生） | `true` |
| `needs_deep_dive` | `bool` | 有前置知识缺口需要深入 | `false` |
| `weaknesses_found` | `list[str]` | 发现的薄弱知识点 | `["导数","极限"]` |
| `gaps_in_content` | `list[str]` | 内容中未覆盖的前置知识 | `["集合论"]` |
| `level_recommendation` | `str` | 建议的难度 | `"进阶"` |
| `task_completed` | `bool` | 当前任务是否成功 | `true` |

---

### 1.2 改造意图分类节点 — 让 Agent 写入反馈

当前 `graph/nodes/intent.py` 中的 `classify_intent` 只输出 `agent_name`。改造为不仅输出 `agent_name`，还生成初始的 `task_plan` 和 `agent_feedback` 初始值：

```python
# graph/nodes/intent.py

from graph.state import AgentGraphState
from core.llm_client import chat_completion
from agents.registry import get_all_agents
import json

INTENT_PROMPT = """根据对话历史和用户消息，判断应调用哪个智能体和工作流。

可选智能体（名称: 描述 — 必须严格返回名称列的值）：
{agent_list}
'study': 用户想系统学习某个知识点/主题（如"我想学XX"、"帮我学XX"、"教我XX"）
'review': 用户想复习错题或薄弱知识点（如"复习错题"、"帮我巩固"、"哪里不会复习哪里"）

对话历史：{history}
用户消息：{message}

判断规则：
- 如果用户明确表达"想学/学习/教我"某个主题 → study
- 如果用户提到"错题/复习/巩固/薄弱" → review
- 如果用户要求生成特定资源（PPT/题目/文章）但不是系统学习 → content_gen
- 如果用户要求生成思维导图/知识图谱 → mindmap
- 如果用户要求评估/测评学习效果 → evaluation
- 如果用户描述自己的信息（专业/年级/目标）用于构建画像 → profile
- 其他对话/问答 → chat

同时生成初始任务计划：
{{
  "agent_name": "study",
  "initial_plan": [
    {{"agent": "profile_analysis", "task": "分析学生当前水平", "priority": 5}},
    {{"agent": "study_content", "task": "生成适配内容", "priority": 5}}
  ]
}}

只能返回上述 JSON，不要任何其他文字、标点、解释。"""


async def classify_intent(state: AgentGraphState) -> dict:
    agents = get_all_agents()
    agent_desc = "\n".join([f"'{a.name}': {a.description}" for a in agents])
    history_text = _format_history(state.get("history", []))

    resp = await chat_completion([
        {"role": "system", "content": INTENT_PROMPT.format(
            agent_list=agent_desc, history=history_text, message=state["user_message"]
        )},
        {"role": "user", "content": state["user_message"]}
    ], temperature=0.3)

    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"agent_name": "chat", "initial_plan": []}

    return {
        "agent_name": parsed.get("agent_name", "chat"),
        "task_plan": parsed.get("initial_plan", []),
        "agent_feedback": {},
        "supervisor_iteration": 0,
        "completed_tasks": [],
    }
```

---

### 1.3 新增 Supervisor 节点 — `graph/nodes/supervisor.py`

Supervisor 是多 Agent 协作的总调度器，替代原 `builder.py` 中硬编码的 `route_by_agent` 函数。它的职责：

1. 读取当前 State（画像分析结果、已完成任务、agent_feedback）
2. 根据反馈信号动态调整任务计划
3. 决定下一个要执行的 worker agent
4. 防止无限循环（最大迭代次数保护）

```python
import json
from graph.state import AgentGraphState
from core.llm_client import chat_completion
from agents.registry import get_all_agents

SUPERVISOR_PROMPT = """你是一个个性化学习系统的总调度员。你的任务是：根据用户请求、学生画像和已完成步骤的结果，动态规划下一步应执行哪个 Agent。

可用 Worker Agent：
{agent_list}

学生画像分析：{profile_analysis}
最近完成的任务：{completed}
上一个 Agent 的反馈：{feedback}
当前任务计划：{plan}
已执行循环次数：{iteration}

决策规则：
1. 如果 task_plan 为空且无画像，先执行 profile_analysis 了解学生水平
2. 如果 content_quality < 0.5，标记 needs_regeneration = true
3. 如果学生是初级且未生成思维导图，追加 study_mindmap
4. 如果反馈中 weaknesses_found 非空且未安排针对性练习，插入 quiz_gen
5. 如果有 gaps_in_content（前置知识缺失），追加新的 study_content 任务
6. 如果所有任务完成 → 返回 "summary"
7. 如果迭代超过 8 次 → 强制返回 "summary"（安全阀）

返回 JSON：
{{
  "next_agent": "profile_analysis | study_content | study_mindmap | quiz_gen | mistake_analysis | evaluation | chat | content_gen | profile | mindmap | summary",
  "updated_plan": [...],
  "reasoning": "为什么选择这个 Agent"
}}
只返回 JSON。"""


async def supervisor_node(state: AgentGraphState) -> dict:
    agents = get_all_agents()
    agent_desc = "\n".join([f"- {a.name}: {a.description}" for a in agents])

    iteration = state.get("supervisor_iteration", 0) + 1

    # 安全阀：超过最大迭代次数强制结束
    if iteration > 8:
        return {
            "current_task": "summary",
            "supervisor_iteration": iteration,
            "agent_feedback": {"force_summary": True},
        }

    resp = await chat_completion([
        {"role": "system", "content": SUPERVISOR_PROMPT.format(
            agent_list=agent_desc,
            profile_analysis=json.dumps(state.get("profile_analysis", {}), ensure_ascii=False),
            completed=json.dumps(state.get("completed_tasks", []), ensure_ascii=False),
            feedback=json.dumps(state.get("agent_feedback", {}), ensure_ascii=False),
            plan=json.dumps(state.get("task_plan", []), ensure_ascii=False),
            iteration=iteration,
        )},
        {"role": "user", "content": state["user_message"]}
    ], temperature=0.2)

    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        decision = {"next_agent": "summary", "reasoning": "JSON 解析失败，安全终止"}

    return {
        "task_plan": decision.get("updated_plan", state.get("task_plan", [])),
        "current_task": decision.get("next_agent", "summary"),
        "supervisor_iteration": iteration,
    }
```

---

### 1.4 Worker 节点改造 — 让 Agent 写入反馈信号

每个 worker 节点完成后需向 State 写入结构化反馈，供 supervisor 决策下一步。以下以 `study_content_node` 为例：

```python
# graph/nodes/study_content.py

import json
from graph.state import AgentGraphState
from agents.content_gen_agent import ContentGenAgent
from agents.base import AgentState

_content_agent = ContentGenAgent()


async def study_content_node(state: AgentGraphState) -> dict:
    analysis = state.get("profile_analysis", {})
    mistake = state.get("mistake_analysis", {})

    if analysis:
        depth = analysis.get("recommended_depth", "进阶")
        focus = "、".join(analysis.get("focus_points", []))
        gaps = analysis.get("gaps", [])
    elif mistake:
        weak_topics = mistake.get("weak_topics", [])
        focus = "、".join(weak_topics)
        depth = "进阶"
        gaps = []
    else:
        depth = "进阶"
        focus = ""
        gaps = []

    enhanced_message = (
        f"{state['user_message']}（难度：{depth}，"
        f"重点关注：{focus or '全面覆盖'}，"
        f"前置知识：{'、'.join(gaps) if gaps else '无'}）"
    )

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=enhanced_message,
        profile=state.get("profile"),
        resource_type="article",
    )
    result = await _content_agent.process(agent_state)
    article = result.get("response", "")

    # ==== 核心改造：写入反馈信号 ====
    feedback = {
        "content_generated": bool(article),
        "content_quality": _estimate_quality(article),
        "needs_regeneration": len(article) < 100,
        "needs_mindmap": depth in ("入门", "进阶"),
        "gaps_in_content": gaps,
        "level_recommendation": depth,
        "task_completed": True,
    }

    outputs = list(state.get("workflow_outputs") or [])
    outputs.append({"stage": "content_gen", "data": article})

    completed = list(state.get("completed_tasks") or [])
    completed.append({
        "agent": "study_content",
        "result_summary": f"生成 {len(article)} 字的{depth}级别内容",
        "quality": feedback["content_quality"],
    })

    return {
        "generated_article": article,
        "agent_feedback": feedback,
        "workflow_outputs": outputs,
        "completed_tasks": completed,
    }


def _estimate_quality(text: str) -> float:
    """简单的内容质量估算（可替换为 LLM 评估）"""
    if not text:
        return 0.0
    score = 0.5
    if len(text) > 200:
        score += 0.2
    if "##" in text:  # 有 Markdown 结构
        score += 0.15
    if "```" in text:  # 有代码块
        score += 0.1
    if len(text) > 500:
        score += 0.05
    return min(score, 1.0)
```

类似地，改造 `quiz_gen_node`、`study_mindmap_node` 等，在返回的 dict 中加入 `agent_feedback` 和 `completed_tasks`。

---

### 1.5 图拓扑改造 — `graph/builder.py`

核心变化：
- **去掉** `intent_classifier → 各 Agent → END` 的静态链
- **引入** `supervisor ⇄ workers` 循环——worker 完成后回到 supervisor，而非直接走向 END 或下一个 worker

```python
from langgraph.graph import StateGraph, START, END

from graph.state import AgentGraphState
from graph.nodes.supervisor import supervisor_node
from graph.nodes.intent import classify_intent
from graph.nodes.chat import chat_node
from graph.nodes.profile import profile_node
from graph.nodes.content_gen import content_gen_node
from graph.nodes.mindmap import mindmap_node
from graph.nodes.evaluation import evaluation_node
from graph.nodes.profile_analysis import profile_analysis_node
from graph.nodes.study_content import study_content_node
from graph.nodes.study_mindmap import study_mindmap_node
from graph.nodes.quiz_gen import quiz_gen_node
from graph.nodes.study_summary import study_summary_node
from graph.nodes.mistake_analysis import mistake_analysis_node
from graph.nodes.profile_update import profile_update_node
from graph.nodes.path_suggest import path_suggest_node


def should_continue(state: AgentGraphState) -> str:
    """Supervisor 循环的条件路由函数

    根据 supervisor_node 写入的 current_task 字段动态决策下一步：
    - 返回 worker agent 名称 → 调度该 worker 执行
    - 返回 "summary" → 跳出循环，结束图
    - 安全阀：迭代次数超限时强制结束
    """
    current = state.get("current_task", "")
    iteration = state.get("supervisor_iteration", 0)
    feedback = state.get("agent_feedback", {})

    # 安全阀
    if iteration >= 8 or feedback.get("force_summary"):
        return "summary"

    # 直接路由目标
    valid_targets = {
        "profile_analysis", "study_content", "study_mindmap", "quiz_gen",
        "mistake_analysis", "evaluation", "profile_update", "path_suggest",
        "chat", "profile", "content_gen", "mindmap",
    }

    if current in valid_targets:
        return current

    return "summary"


def compile_graph():
    builder = StateGraph(AgentGraphState)

    # ============ 节点注册 ============

    # 入口 & 调度
    builder.add_node("intent_classifier", classify_intent)
    builder.add_node("supervisor", supervisor_node)

    # Worker Agents
    builder.add_node("profile_analysis", profile_analysis_node)
    builder.add_node("study_content", study_content_node)
    builder.add_node("study_mindmap", study_mindmap_node)
    builder.add_node("quiz_gen", quiz_gen_node)
    builder.add_node("mistake_analysis", mistake_analysis_node)
    builder.add_node("evaluation", evaluation_node)
    builder.add_node("profile_update", profile_update_node)
    builder.add_node("path_suggest", path_suggest_node)

    # 单节点直通（兼容 Phase 1 行为）
    builder.add_node("chat", chat_node)
    builder.add_node("profile", profile_node)
    builder.add_node("content_gen", content_gen_node)
    builder.add_node("mindmap", mindmap_node)

    # 汇总出口
    builder.add_node("summary", study_summary_node)

    # ============ 边定义 ============

    # 入口：START → intent_classifier
    builder.add_edge(START, "intent_classifier")

    # intent_classifier 完成后 → supervisor（而不是直接 route_by_agent）
    builder.add_edge("intent_classifier", "supervisor")

    # ==== Supervisor 循环 ★ 核心模式 ====
    builder.add_conditional_edges(
        "supervisor",
        should_continue,
        {
            "profile_analysis": "profile_analysis",
            "study_content": "study_content",
            "study_mindmap": "study_mindmap",
            "quiz_gen": "quiz_gen",
            "mistake_analysis": "mistake_analysis",
            "evaluation": "evaluation",
            "profile_update": "profile_update",
            "path_suggest": "path_suggest",
            "chat": "chat",
            "profile": "profile",
            "content_gen": "content_gen",
            "mindmap": "mindmap",
            "summary": "summary",
        },
    )

    # 所有 Worker 完成后 → 回到 supervisor（不直接走向下一个节点或 END）
    worker_nodes = [
        "profile_analysis", "study_content", "study_mindmap", "quiz_gen",
        "mistake_analysis", "evaluation", "profile_update", "path_suggest",
        "chat", "profile", "content_gen", "mindmap",
    ]
    for node_name in worker_nodes:
        builder.add_edge(node_name, "supervisor")

    # 汇总节点 → END
    builder.add_edge("summary", END)

    return builder.compile()
```

**图拓扑示意**

```
START
  │
  ▼
intent_classifier
  │
  ▼
supervisor ◄──────────────────────────┐
  │ (conditional)                      │
  ├─→ profile_analysis ──────反馈──────┘
  ├─→ study_content ─────────反馈──────┘
  ├─→ study_mindmap ─────────反馈──────┘
  ├─→ quiz_gen ──────────────反馈──────┘
  ├─→ mistake_analysis ──────反馈──────┘
  ├─→ evaluation ────────────反馈──────┘
  ├─→ chat / profile / etc ──反馈──────┘
  └─→ summary → END
```

每个 worker 执行完后 **返回 supervisor**，由 supervisor 根据 worker 写入 State 的 `agent_feedback` 决定是继续调度下一个 worker、重新执行某个 worker、还是结束流程。

---

### 1.6 chat_service.py 适配

流式输出层需要适配 supervisor 循环产生的多轮节点输出：

```python
# services/chat_service.py（修改 event_stream 部分）

async def event_stream():
    async for chunk in _graph.astream(initial_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if node_name in ("intent_classifier", "supervisor"):
                continue

            # 多步工作流：每个节点输出一个 stage 事件
            if "workflow_outputs" in update:
                outputs = update["workflow_outputs"]
                if outputs:
                    latest = outputs[-1] if isinstance(outputs, list) else outputs
                    yield json.dumps({
                        "type": "stage",
                        "stage": latest.get("stage", node_name),
                        "data": latest.get("data", ""),
                    }, ensure_ascii=False)

            response = update.get("response", "")
            if response:
                yield response
```

---

## 第二阶段：高级模式

### 2.1 Checkpointing — 工作流状态持久化

LangGraph 的 checkpointing 允许将图执行的中间状态持久化，支持断点续传和会话恢复。

```python
# graph/builder.py

from langgraph.checkpoint.sqlite import SqliteSaver

_checkpointer = SqliteSaver.from_conn_string("checkpoints.db")


def compile_graph():
    builder = StateGraph(AgentGraphState)
    # ...节点和边定义同上...
    return builder.compile(checkpointer=_checkpointer)
```

调用时传入 `thread_id`：

```python
# services/chat_service.py

async def route_to_agent(user_id: str, message: str, history: list[dict] | None = None,
                         session_id: str | None = None):
    # ...
    async def event_stream():
        config = {"configurable": {"thread_id": session_id or user_id}}
        async for chunk in _graph.astream(initial_state, config, stream_mode="updates"):
            # ...
```

**效果**：
- 用户中断学习流程后，下次请求同一 `thread_id` 可从上次断点继续
- 长工作流（5-8 步）无需一次完成，支持跨请求执行
- 每个 checkpoint 记录完整的 State 快照

### 2.2 Human-in-the-Loop — 关键节点人工审核

在内容生成节点后插入审核步骤，让用户确认后再继续：

```python
# graph/nodes/content_review.py

from langgraph.types import interrupt
from graph.state import AgentGraphState


async def content_review_node(state: AgentGraphState) -> dict:
    article = state.get("generated_article", "")
    quality = state.get("agent_feedback", {}).get("content_quality", 0)

    if quality >= 0.8:
        # 高质量内容自动通过，无需人工审核
        return {"agent_feedback": {"review_passed": True}}

    # 低质量内容暂停执行，等待用户确认
    user_decision = interrupt({
        "action": "review_content",
        "preview": article[:300],
        "quality": quality,
        "question": "内容质量偏低，是否继续？选择 'retry' 重新生成，'accept' 接受。",
        "options": ["accept", "retry"],
    })

    if user_decision == "retry":
        return {"agent_feedback": {"needs_regeneration": True}}
    return {"agent_feedback": {"review_passed": True}}
```

在 `builder.py` 中插入审核节点：

```python
builder.add_node("content_review", content_review_node)
# study_content → review → supervisor
builder.add_edge("study_content", "content_review")
builder.add_edge("content_review", "supervisor")
```

**注意**：`interrupt()` 会暂停图执行。前端需调用 LangGraph 的 resume API 传入用户决策后，图才会继续。

目前项目使用 FastAPI + SSE，后续需增加 resume 端点：

```python
# api/routes/chat.py

@router.post("/stream/resume")
async def resume_stream(req: ResumeRequest):
    """恢复被 interrupt 暂停的工作流"""
    # 使用 LangGraph 的 Command.resume() 机制
    ...
```

### 2.3 并行 Agent 执行

当多个 Agent 任务无依赖关系时，可以用 LangGraph 的 `Send` API 并行分发：

```python
from langgraph.constants import Send


def parallel_dispatch(state: AgentGraphState) -> list[Send]:
    """Supervisor 将独立任务并行分发给多个 worker"""
    plan = state.get("task_plan", [])
    sends = []

    # 找出最高优先级的独立任务
    tasks = [t for t in plan if not t.get("depends_on")]
    for task in tasks:
        sends.append(Send(task["agent"], {"task": task}))

    return sends if sends else ["summary"]


# 在 builder 中使用
builder.add_conditional_edges("supervisor", parallel_dispatch, {
    "profile_analysis": "profile_analysis",
    "study_content": "study_content",
    "study_mindmap": "study_mindmap",
    "quiz_gen": "quiz_gen",
})
```

**适用场景**：在同一学习请求中，`study_mindmap`（生成思维导图）和 `quiz_gen`（生成练习题）无依赖关系，可并行执行以减少总耗时。

### 2.4 条件跳过 — 根据画像动态调整工作流

```python
def should_generate_mindmap(state: AgentGraphState) -> str:
    """高级学生可直接跳过思维导图，进入练习阶段"""
    analysis = state.get("profile_analysis", {})
    level = analysis.get("current_level", "中级")
    feedback = state.get("agent_feedback", {})

    if level == "高级" and not feedback.get("needs_mindmap"):
        return "quiz_gen"
    return "study_mindmap"


# 在 supervisor 的 conditional_edges 之后，对特定节点增加条件跳转
builder.add_conditional_edges("study_content", should_generate_mindmap, {
    "study_mindmap": "study_mindmap",
    "quiz_gen": "quiz_gen",
})
```

---

## 第三阶段：Agent 改造（提升每个 Worker 的自治能力）

当前 Agent 的 `process()` 方法本质上是「构造 Prompt → LLM 调用 → 返回结果」。若要进一步提升效果，可引入 **Tool 系统**，让每个 Worker Agent 在内部循环中自主调用工具。

### 3.1 提取工具接口

```python
# agents/tools.py

from typing import Callable
from dataclasses import dataclass


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable


def search_learning_resources(query: str, user_id: str) -> list[dict]:
    """搜索学习资源库"""
    from services.rag_service import search_rag
    result = search_rag(query, user_id, top_k=5)
    docs = result.get("documents", [])
    return [{"content": d[:500], "id": id_} for d, id_ in zip(docs, result.get("ids", []))]


def query_mistake_history(user_id: str, topic: str = "") -> list[dict]:
    """查询错题记录"""
    from core.database import SessionLocal
    from models.mistake_question import MistakeQuestion

    db = SessionLocal()
    try:
        query = db.query(MistakeQuestion).filter(MistakeQuestion.user_id == user_id)
        if topic:
            query = query.filter(MistakeQuestion.topic == topic)
        records = query.order_by(MistakeQuestion.created_at.desc()).limit(20).all()
        return [{
            "question": r.question,
            "user_answer": r.user_answer,
            "correct_answer": r.correct_answer,
            "topic": r.topic,
        } for r in records]
    finally:
        db.close()


def get_profile(user_id: str) -> dict:
    """获取学生画像"""
    from core.database import SessionLocal
    from models.student import StudentProfile

    db = SessionLocal()
    try:
        p = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        if not p:
            return {}
        return {
            "major": p.major,
            "grade": p.grade,
            "knowledge_base": p.knowledge_base,
            "weak_points": p.weak_points,
            "learning_goal": p.learning_goal,
        }
    finally:
        db.close()


TOOLS = [
    Tool(
        name="search_resources",
        description="搜索与指定查询相关的学习资源",
        parameters={"query": "string", "user_id": "string"},
        handler=search_learning_resources,
    ),
    Tool(
        name="query_mistake_history",
        description="查询学生的错题历史记录",
        parameters={"user_id": "string", "topic": "string"},
        handler=query_mistake_history,
    ),
    Tool(
        name="get_profile",
        description="获取学生画像信息",
        parameters={"user_id": "string"},
        handler=get_profile,
    ),
]
```

### 3.2 Agent 基类增加 Tool 调用能力

```python
# agents/base.py

from abc import ABC, abstractmethod
from typing import AsyncGenerator
import json
from agents.tools import TOOLS

TOOL_MAP = {t.name: t.handler for t in TOOLS}
TOOL_DESC = "\n".join([f"- {t.name}: {t.description}" for t in TOOLS])


class BaseAgent(ABC):
    name: str = ""
    description: str = ""
    tools: list[str] = []  # 子类声明自己可用的工具名列表

    @abstractmethod
    async def process(self, state: "AgentState") -> "AgentState":
        ...

    async def stream(self, state: "AgentState") -> AsyncGenerator[str, None]:
        result = await self.process(state)
        yield result.get("response", "")

    async def use_tool(self, tool_name: str, **kwargs):
        """Agent 内部调用工具"""
        handler = TOOL_MAP.get(tool_name)
        if not handler:
            return {"error": f"Tool not found: {tool_name}"}
        try:
            result = handler(**kwargs)
            if hasattr(result, '__await__'):
                result = await result
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_loop(self, messages: list, state: "AgentState") -> str:
        """工具调用循环：Agent 可以多次调用工具直到得到满意结果

        使用 LLM 来判断是否需要调用工具。
        由于项目使用原生 openai SDK 而非 LangChain，这里采用
        JSON 输出来驱动工具调用（function-calling 的简化替代）。
        """
        from core.llm_client import chat_completion
        max_iterations = 5

        tool_prompt = f"""你可以调用以下工具来获取信息：
{TOOL_DESC}

如果需要调用工具，返回 JSON：
{{"tool_call": "工具名", "arguments": {{"param": "value"}}}}

如果不需调用工具，直接回答用户问题。"""

        for _ in range(max_iterations):
            resp = await chat_completion(
                [{"role": "system", "content": tool_prompt}] + messages,
                temperature=0.3,
            )
            content = resp.choices[0].message.content.strip()

            # 尝试解析为工具调用
            try:
                if content.startswith("{"):
                    call_data = json.loads(content)
                    tool_name = call_data.get("tool_call")
                    if tool_name and tool_name in TOOL_MAP:
                        tool_result = await self.use_tool(tool_name, **call_data.get("arguments", {}))
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": f"工具调用结果：{json.dumps(tool_result, ensure_ascii=False)}"
                        })
                        continue
            except (json.JSONDecodeError, KeyError):
                pass

            # 不是工具调用，返回结果
            return content

        return "无法在有限次数内完成任务"
```

### 3.3 ChatAgent 使用 Tool

```python
# agents/chat_agent.py

class ChatAgent(BaseAgent):
    name = "chat"
    description = "通用 AI 对话助手，回答学习问题、提供知识讲解"
    tools = ["search_resources", "get_profile"]  # 声明可用工具

    async def stream(self, state: AgentState) -> AsyncGenerator[str, None]:
        profile_text = self._profile_text(state)
        history = state.get("history", [])[-20:]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(
                profile=profile_text,
                hallu=hallu_rules(),
                rag_context="",
            )},
        ]
        for h in history:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": state.user_message})

        # 使用工具循环获取增强信息
        response = await self._tool_loop(messages, state)

        safe_response, _ = await check_text(response)
        state["response"] = safe_response
        yield safe_response
```

---

## 改造步骤总结

| 步骤 | 内容 | 涉及文件 | 复杂度 |
|------|------|----------|--------|
| 1 | 扩展 `AgentGraphState` 增加协作字段 | `graph/state.py` | 低 |
| 2 | 改造 `classify_intent` 输出 `task_plan` | `graph/nodes/intent.py` | 低 |
| 3 | 新建 `supervisor_node` | `graph/nodes/supervisor.py`（新文件） | 中 |
| 4 | 改造所有 worker 节点，写入 `agent_feedback` | `graph/nodes/*.py` | 中 |
| 5 | 改造 `builder.py`，引入 supervisor 循环 | `graph/builder.py` | 高 |
| 6 | 适配 `chat_service.py` 多轮输出 | `services/chat_service.py` | 低 |
| 7 | 更新 `graph/nodes/__init__.py` 导出 | `graph/nodes/__init__.py` | 低 |
| 8 | 更新 `test_graph.py` 测试新拓扑 | `test_graph.py` | 中 |
| 9 | 前端 SSE 适配多轮 stage 事件 | 前端 | 中 |
| 10 | 联调 + 回归测试 | 全局 | 中 |

---

## 关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| supervisor LLM 决策不准 | 调度错误，循环死锁 | `supervisor_iteration` 上限（8 次）；模糊匹配回退到 `summary` |
| 长工作流用户等待时间过长 | 用户体验差 | 前端分段渲染 + loading 状态；并行 Agent 执行（2.3） |
| worker 反馈信号可靠性不足 | supervisor 做出错误决策 | `_estimate_quality()` 可替换为 LLM 评估；增加人工审核节点（2.2） |
| 讯飞 Spark API 不支持 function-calling | Tool 循环依赖 JSON 解析 | 当前设计的 JSON 输出模式与 Spark API 兼容；后续可升级 |
| 原有 chat/profile 单节点路由行为被破坏 | 用户简单问答变慢 | supervisor 对 `chat`/`profile` 意图直接一次性路由，不走循环 |

---

## 完成标准

- [ ] 用户发送"我想学微积分"→ supervisor 自动调度 profile_analysis → study_content → quiz_gen → summary，各阶段正确执行
- [ ] 用户发送"复习错题"→ supervisor 调度 mistake_analysis → study_content → quiz_gen → summary
- [ ] 用户发送一个简单问题 → supervisor 路由到 chat 节点，单次完成（不回环）
- [ ] 低质量内容触发 `needs_regeneration`，supervisor 重新调度 study_content
- [ ] `supervisor_iteration` 超过 8 次强制终止，不产生死循环
- [ ] 前端 SSE 分段展示各阶段输出（含 stage 事件）
- [ ] 现有 `/health`、`/api/chat/explain-term`、`/api/chat/mark-terms` 等端点不受影响
- [ ] `test_graph.py` 中新增 supervisor 循环测试用例
