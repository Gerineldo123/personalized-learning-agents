# LangGraph 应用方案 — 个性化学习系统多步工作流

## 概述

Phase 1 已将 LangGraph 图引擎接入系统，替代了原有的手写路由。本文档描述如何在此基础上，利用 LangGraph 的多步编排能力，实现 Agent 串联工作流，让系统从"一个请求只能调一个 Agent"进化为"一个请求自动串联多个 Agent 完成完整学习闭环"。

---

## 一、目标场景

### 场景 A：一键学习（study workflow）

用户说"我想学微积分"，系统自动完成：
1. 分析学生画像，判断当前水平
2. 生成适配难度的学习文章
3. 生成知识体系思维导图
4. 生成配套练习题
5. 给出学习建议

**用户操作**：1 次请求 → 获得完整学习包

### 场景 B：错题复习闭环（review workflow）

用户说"帮我复习错题"，系统自动完成：
1. 从错题库提取薄弱知识点
2. 针对薄弱点生成专题讲解
3. 生成同类变式练习题

**用户操作**：1 次请求 → 获得针对性复习材料

### 场景 C：评估驱动的画像更新（evaluation workflow）

用户完成评估后，系统自动：
1. 生成评估报告
2. 更新学生画像（知识评分、薄弱点）
3. 调整学习路径建议

**用户操作**：1 次评估 → 画像和路径自动更新

---

## 二、图拓扑设计

### 整体图结构

```
[START]
   │
   ▼
[intent_classifier]
   │
   ├── "chat"       → [chat_node] → END
   ├── "profile"    → [profile_node] → END
   ├── "content_gen"→ [content_gen_node] → END
   ├── "mindmap"    → [mindmap_node] → END
   ├── "evaluation" → [evaluation_node] → [profile_update_node] → [path_suggest_node] → END
   ├── "study"      → [study_workflow 子图] → END
   └── "review"     → [review_workflow 子图] → END
```

### 子图 A：study_workflow

```
[profile_analysis] → [content_gen] → [mindmap_gen] → [quiz_gen] → [study_summary] → END
```

### 子图 B：review_workflow

```
[mistake_analysis] → [content_gen] → [quiz_gen] → END
```

### 子图 C：evaluation_workflow（扩展现有 evaluation 路由）

```
[evaluation_node] → [profile_update] → [path_suggest] → END
```

---

## 三、State Schema 扩展

在 `graph/state.py` 中扩展字段以支持多步工作流中间数据传递：

```python
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class AgentGraphState(TypedDict):
    # 基础字段（Phase 1 已有）
    user_id: str
    user_message: str
    profile: Any
    history: list[dict]
    messages: Annotated[list, add_messages]
    response: str
    agent_name: str

    # Phase 2 新增：工作流中间数据
    profile_analysis: dict       # 画像分析结果（水平判断、薄弱点）
    generated_article: str       # 生成的学习文章
    generated_mindmap: str       # 生成的思维导图 markdown
    generated_quiz: dict         # 生成的练习题 JSON
    evaluation_report: dict      # 评估报告
    mistake_analysis: dict       # 错题分析结果
    path_suggestion: str         # 学习路径建议
    workflow_outputs: list[dict] # 各节点输出的聚合（用于前端分段展示）
```

---

## 四、新增节点文件

### 4.1 `graph/nodes/profile_analysis.py`

读取画像但不更新，输出水平判断供后续节点使用：

```python
from graph.state import AgentGraphState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.student import StudentProfile
import json

ANALYSIS_PROMPT = """你是一个学习诊断专家。根据学生画像，分析其当前知识水平并给出学习建议。

学生画像：{profile}
学习主题：{topic}

返回JSON：
{{
  "current_level": "初级/中级/高级",
  "relevant_knowledge": ["已掌握的相关知识点"],
  "gaps": ["需要补充的前置知识"],
  "recommended_depth": "入门/进阶/深入",
  "focus_points": ["建议重点学习的方面"]
}}
只返回JSON。"""


async def profile_analysis_node(state: AgentGraphState) -> dict:
    profile = state.get("profile")
    profile_text = json.dumps({
        "major": getattr(profile, "major", "未知"),
        "grade": getattr(profile, "grade", "未知"),
        "knowledge_base": getattr(profile, "knowledge_base", {}),
        "weak_points": getattr(profile, "weak_points", []),
    }, ensure_ascii=False) if profile else "暂无画像"

    resp = await chat_completion([
        {"role": "user", "content": ANALYSIS_PROMPT.format(
            profile=profile_text, topic=state["user_message"]
        )}
    ], temperature=0.3)

    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    analysis = json.loads(raw)
    return {
        "profile_analysis": analysis,
        "workflow_outputs": [{"stage": "profile_analysis", "data": analysis}],
    }
```

### 4.2 `graph/nodes/study_content.py`

基于画像分析结果生成适配难度的学习文章：

```python
from graph.state import AgentGraphState
from agents.content_gen_agent import ContentGenAgent
from agents.base import AgentState

_content_agent = ContentGenAgent()


async def study_content_node(state: AgentGraphState) -> dict:
    analysis = state.get("profile_analysis", {})
    depth = analysis.get("recommended_depth", "进阶")
    focus = "、".join(analysis.get("focus_points", []))

    enhanced_message = (
        f"{state['user_message']}（难度：{depth}，"
        f"重点关注：{focus or '全面覆盖'}）"
    )

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=enhanced_message,
        profile=state.get("profile"),
        resource_type="article",
    )
    result = await _content_agent.process(agent_state)
    article = result.get("response", "")

    outputs = state.get("workflow_outputs", [])
    outputs.append({"stage": "content_gen", "data": article})

    return {
        "generated_article": article,
        "workflow_outputs": outputs,
    }
```

### 4.3 `graph/nodes/study_mindmap.py`

基于学习文章生成思维导图：

```python
from graph.state import AgentGraphState
from agents.mindmap_agent import MindMapAgent
from agents.base import AgentState

_mindmap_agent = MindMapAgent()


async def study_mindmap_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
    )
    result = await _mindmap_agent.process(agent_state)
    mindmap = result.get("response", "")

    outputs = state.get("workflow_outputs", [])
    outputs.append({"stage": "mindmap", "data": mindmap})

    return {
        "generated_mindmap": mindmap,
        "workflow_outputs": outputs,
    }
```

### 4.4 `graph/nodes/quiz_gen.py`

从 ContentGenAgent 的 quiz 模式拆出为独立节点：

```python
from graph.state import AgentGraphState
from agents.content_gen_agent import ContentGenAgent
from agents.base import AgentState

_content_agent = ContentGenAgent()


async def quiz_gen_node(state: AgentGraphState) -> dict:
    analysis = state.get("profile_analysis", {})
    level = analysis.get("current_level", "中级")
    difficulty_map = {"初级": "简单", "中级": "中等", "高级": "困难"}

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        resource_type="quiz",
        difficulty=difficulty_map.get(level, "中等"),
        question_count=5,
    )
    result = await _content_agent.process(agent_state)
    quiz = result.get("response", "")

    outputs = state.get("workflow_outputs", [])
    outputs.append({"stage": "quiz", "data": quiz})

    return {
        "generated_quiz": quiz,
        "workflow_outputs": outputs,
    }
```

### 4.5 `graph/nodes/study_summary.py`

汇总各阶段输出，生成最终响应：

```python
from graph.state import AgentGraphState
import json


async def study_summary_node(state: AgentGraphState) -> dict:
    outputs = state.get("workflow_outputs", [])
    analysis = state.get("profile_analysis", {})

    summary = {
        "workflow": "study",
        "topic": state["user_message"],
        "level": analysis.get("current_level", "未知"),
        "stages": outputs,
    }

    return {
        "response": json.dumps(summary, ensure_ascii=False),
    }
```

### 4.6 `graph/nodes/mistake_analysis.py`

错题分析节点：

```python
from graph.state import AgentGraphState
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.mistake_question import MistakeQuestion
import json

MISTAKE_PROMPT = """你是一个学习诊断专家。分析以下错题记录，找出薄弱知识点。

错题记录：
{mistakes}

返回JSON：
{{
  "weak_topics": ["薄弱知识点1", "薄弱知识点2"],
  "error_patterns": ["常见错误模式"],
  "priority_topic": "最需要复习的知识点",
  "review_suggestion": "复习建议"
}}
只返回JSON。"""


async def mistake_analysis_node(state: AgentGraphState) -> dict:
    db = SessionLocal()
    try:
        mistakes = db.query(MistakeQuestion).filter(
            MistakeQuestion.user_id == state["user_id"]
        ).order_by(MistakeQuestion.created_at.desc()).limit(20).all()

        if not mistakes:
            return {
                "mistake_analysis": {"weak_topics": [], "priority_topic": ""},
                "response": json.dumps({"message": "暂无错题记录"}, ensure_ascii=False),
            }

        mistake_text = "\n".join([
            f"- 题目: {m.question[:100]}, 错误答案: {m.wrong_answer}, 正确答案: {m.correct_answer}"
            for m in mistakes
        ])

        resp = await chat_completion([
            {"role": "user", "content": MISTAKE_PROMPT.format(mistakes=mistake_text)}
        ], temperature=0.3)

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        analysis = json.loads(raw)
        return {
            "mistake_analysis": analysis,
            "user_message": analysis.get("priority_topic", state["user_message"]),
            "workflow_outputs": [{"stage": "mistake_analysis", "data": analysis}],
        }
    finally:
        db.close()
```

### 4.7 `graph/nodes/path_suggest.py`

学习路径建议节点：

```python
from graph.state import AgentGraphState
from core.llm_client import chat_completion
import json

PATH_PROMPT = """你是一个学习规划专家。根据评估结果和学生画像，建议下一步学习路径。

评估报告：{report}
学生画像：{profile}

返回简洁的学习路径建议（3-5 条），每条包含知识点和建议学习方式。"""


async def path_suggest_node(state: AgentGraphState) -> dict:
    report = state.get("evaluation_report", {})
    profile = state.get("profile")

    profile_text = json.dumps({
        "major": getattr(profile, "major", ""),
        "weak_points": getattr(profile, "weak_points", []),
        "learning_goal": getattr(profile, "learning_goal", ""),
    }, ensure_ascii=False) if profile else "暂无"

    resp = await chat_completion([
        {"role": "user", "content": PATH_PROMPT.format(
            report=json.dumps(report, ensure_ascii=False),
            profile=profile_text,
        )}
    ], temperature=0.5)

    suggestion = resp.choices[0].message.content
    return {"path_suggestion": suggestion}
```

### 4.8 `graph/nodes/profile_update.py`

评估后自动更新画像：

```python
from graph.state import AgentGraphState
from agents.profile_agent import ProfileAgent
from agents.base import AgentState

_profile_agent = ProfileAgent()


async def profile_update_node(state: AgentGraphState) -> dict:
    report = state.get("evaluation_report", {})
    summary = report.get("summary", "")
    weaknesses = ", ".join(report.get("weaknesses", []))

    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=f"根据评估更新画像：{summary}。薄弱环节：{weaknesses}",
        profile=state.get("profile"),
    )
    result = await _profile_agent.process(agent_state)
    return {
        "profile": result.get("profile"),
    }
```

---

## 五、图构建器改造 — `graph/builder.py`

```python
from langgraph.graph import StateGraph, START, END

from graph.state import AgentGraphState
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

VALID_AGENTS = {
    "chat", "profile", "content_gen", "mindmap",
    "evaluation", "study", "review",
}


def route_by_agent(state: AgentGraphState) -> str:
    agent_name = state.get("agent_name", "").lower()
    if agent_name in VALID_AGENTS:
        return agent_name
    for name in VALID_AGENTS:
        if name in agent_name or agent_name in name:
            return name
    return "chat"


def compile_graph():
    builder = StateGraph(AgentGraphState)

    # === 基础节点（Phase 1） ===
    builder.add_node("intent_classifier", classify_intent)
    builder.add_node("chat", chat_node)
    builder.add_node("profile", profile_node)
    builder.add_node("content_gen", content_gen_node)
    builder.add_node("mindmap", mindmap_node)

    # === 评估工作流节点 ===
    builder.add_node("evaluation", evaluation_node)
    builder.add_node("profile_update", profile_update_node)
    builder.add_node("path_suggest", path_suggest_node)

    # === 学习工作流节点 ===
    builder.add_node("profile_analysis", profile_analysis_node)
    builder.add_node("study_content", study_content_node)
    builder.add_node("study_mindmap", study_mindmap_node)
    builder.add_node("quiz_gen", quiz_gen_node)
    builder.add_node("study_summary", study_summary_node)

    # === 错题复习工作流节点 ===
    builder.add_node("mistake_analysis", mistake_analysis_node)

    # === 入口 ===
    builder.add_edge(START, "intent_classifier")

    # === 条件路由 ===
    builder.add_conditional_edges(
        "intent_classifier",
        route_by_agent,
        {
            "chat": "chat",
            "profile": "profile",
            "content_gen": "content_gen",
            "mindmap": "mindmap",
            "evaluation": "evaluation",
            "study": "profile_analysis",
            "review": "mistake_analysis",
        },
    )

    # === 单节点路由（Phase 1 保留） ===
    builder.add_edge("chat", END)
    builder.add_edge("profile", END)
    builder.add_edge("content_gen", END)
    builder.add_edge("mindmap", END)

    # === 评估工作流：evaluation → profile_update → path_suggest → END ===
    builder.add_edge("evaluation", "profile_update")
    builder.add_edge("profile_update", "path_suggest")
    builder.add_edge("path_suggest", END)

    # === 学习工作流：profile_analysis → study_content → study_mindmap → quiz_gen → study_summary → END ===
    builder.add_edge("profile_analysis", "study_content")
    builder.add_edge("study_content", "study_mindmap")
    builder.add_edge("study_mindmap", "quiz_gen")
    builder.add_edge("quiz_gen", "study_summary")
    builder.add_edge("study_summary", END)

    # === 错题复习工作流：mistake_analysis → study_content → quiz_gen → study_summary → END ===
    builder.add_edge("mistake_analysis", "study_content")
    # study_content → study_mindmap → quiz_gen → study_summary → END 已定义

    return builder.compile()
```

---

## 六、意图分类 Prompt 更新

在 `graph/nodes/intent.py` 中更新 `INTENT_PROMPT`，增加 `study` 和 `review` 意图：

```python
INTENT_PROMPT = """根据对话历史和用户消息，判断应调用哪个智能体。

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
- 其他对话/问答 → chat

只能返回上面列出的智能体名称本身（纯英文），不要任何其他文字、标点、解释。"""
```

---

## 七、`chat_service.py` 流式输出适配

多步工作流会产生多个节点的输出，前端需要分段展示。修改 `event_stream()` 以支持多阶段输出：

```python
async def event_stream():
    async for chunk in _graph.astream(initial_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if node_name == "intent_classifier":
                continue

            # 多步工作流：每个节点输出一个 stage 事件
            if "workflow_outputs" in update:
                outputs = update["workflow_outputs"]
                if outputs:
                    latest = outputs[-1]
                    import json
                    yield json.dumps({
                        "type": "stage",
                        "stage": latest["stage"],
                        "data": latest["data"],
                    }, ensure_ascii=False)

            # 最终响应
            response = update.get("response", "")
            if response:
                yield response
```

---

## 八、前端适配建议

前端 SSE 接收到的数据格式变化：

**Phase 1（单节点）**：
```
data: 完整的响应文本...
```

**Phase 2（多步工作流）**：
```
data: {"type":"stage","stage":"profile_analysis","data":{...}}
data: {"type":"stage","stage":"content_gen","data":"...文章内容..."}
data: {"type":"stage","stage":"mindmap","data":"...思维导图..."}
data: {"type":"stage","stage":"quiz","data":{...题目JSON...}}
data: 最终汇总响应
```

前端可根据 `type: "stage"` 判断是否为工作流中间输出，分段渲染：
- `profile_analysis` → 显示"正在分析你的知识水平..."
- `content_gen` → 渲染学习文章
- `mindmap` → 渲染思维导图
- `quiz` → 渲染练习题卡片

---

## 九、实施步骤

| 步骤 | 内容 | 预估时间 |
|---|---|---|
| 1 | 扩展 `AgentGraphState` 字段 | 0.5h |
| 2 | 实现 `profile_analysis_node` | 1h |
| 3 | 实现 `study_content_node`、`study_mindmap_node` | 1h |
| 4 | 实现 `quiz_gen_node`、`study_summary_node` | 1h |
| 5 | 实现 `mistake_analysis_node` | 1h |
| 6 | 实现 `profile_update_node`、`path_suggest_node` | 1h |
| 7 | 改造 `builder.py` 添加工作流边 | 1h |
| 8 | 更新 `intent.py` 的 prompt | 0.5h |
| 9 | 适配 `chat_service.py` 多阶段输出 | 1h |
| 10 | 前端分段渲染适配 | 2h |
| 11 | 联调测试 | 2h |
| **合计** | | **~12h（1.5 天）** |

---

## 十、后续扩展（Phase 3）

在本方案基础上可进一步引入：

### 10.1 Checkpointing（状态持久化）

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("data.db")
graph = builder.compile(checkpointer=checkpointer)

# 每次请求带 thread_id，支持断点续传
result = await graph.ainvoke(input, config={"configurable": {"thread_id": conv_id}})
```

### 10.2 Human-in-the-loop（内容审核）

在 `study_content` 和 `quiz_gen` 之后插入 interrupt 节点：

```python
from langgraph.types import interrupt

async def content_review_node(state):
    # 暂停执行，等待用户确认
    interrupt({"message": "已生成学习内容，是否继续生成练习题？", "content": state["generated_article"][:200]})
    return {}
```

### 10.3 条件分支

根据画像分析结果动态决定是否跳过某些步骤：

```python
def should_generate_mindmap(state) -> str:
    analysis = state.get("profile_analysis", {})
    level = analysis.get("current_level", "")
    # 高级学生跳过思维导图，直接出题
    if level == "高级":
        return "quiz_gen"
    return "study_mindmap"

builder.add_conditional_edges("study_content", should_generate_mindmap, {
    "study_mindmap": "study_mindmap",
    "quiz_gen": "quiz_gen",
})
```

---

## 十一、完成标准

- [ ] 用户发送"我想学微积分"→ 自动执行 5 步工作流，返回完整学习包
- [ ] 用户发送"复习错题"→ 自动分析错题并生成针对性复习材料
- [ ] 用户完成评估 → 画像和路径自动更新
- [ ] 前端能分段展示各阶段输出（带 loading 状态）
- [ ] 单节点路由（chat/profile/content_gen/mindmap）行为不变
- [ ] 无新增 lint 错误
