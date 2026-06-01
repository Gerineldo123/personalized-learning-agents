# LangGraph 引入 — Phase 1：路由层替换

## 目标

用 `StateGraph` 替代 `services/chat_service.py` 中"LLM 意图分类 → 单 Agent 调用"的流程。

**不做功能变更**，仅将编排层从手写路由切换为 LangGraph 图引擎，验证 LangGraph 与 FastAPI + SSE 流式的兼容性。

---

## 前置准备

### 1. 安装依赖

```bash
pip install langgraph langgraph-checkpoint
```

### 2. 可选：LangSmith 追踪（调试用）

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-key>
export LANGCHAIN_PROJECT=pla-phase1
```

---

## 步骤一：创建 `backend/graph/` 目录结构

```
backend/graph/
├── __init__.py          # 导出 compile_graph
├── state.py             # AgentGraphState 类型定义
├── builder.py           # StateGraph 构建与编译
└── nodes/
    ├── __init__.py
    ├── intent.py        # classify_intent 节点
    ├── chat.py          # chat_node 包装
    ├── profile.py       # profile_node 包装
    ├── content_gen.py   # content_gen_node 包装
    ├── mindmap.py       # mindmap_node 包装
    └── evaluation.py    # evaluation_node 包装
```

---

## 步骤二：定义 State schema — `graph/state.py`

```python
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class AgentGraphState(TypedDict):
    user_id: str
    user_message: str
    profile: dict | None
    history: list[dict]
    messages: Annotated[list, add_messages]
    response: str
    agent_name: str
```

**说明**：

- `messages` 使用 `add_messages` 注解，LangGraph 会跨节点自动累加消息。
- 其余字段与现有 `AgentState(dict)` 完全对应，`Annotated` 未标注则默认用后值覆盖前值（last-write-wins）。
- `agent_name` 由 `intent_classifier` 节点写入，供条件边路由使用。

---

## 步骤三：实现节点函数 — `graph/nodes/`

### 原则

- **不修改现有 Agent 内部代码**，节点函数负责创建 `AgentState`、调用 Agent、提取结果填入 graph state。
- 每个节点函数签名：`async (state: AgentGraphState) -> dict`，返回部分 state 更新。

### `graph/nodes/intent.py`

从 `chat_service.py` 原 `route_to_agent` 中提取意图分类逻辑：

```python
from core.llm_client import chat_completion
from agents.registry import get_all_agents

INTENT_PROMPT = """根据对话历史和用户消息，判断应调用哪个智能体。

可选智能体（名称: 描述 — 必须严格返回名称列的值）：
{agent_list}

对话历史：{history}
用户消息：{message}

只能返回上面列出的智能体名称本身（纯英文），不要任何其他文字、标点、解释。"""


async def classify_intent(state: AgentGraphState) -> dict:
    agents = get_all_agents()
    agent_desc = "\n".join([f"'{a.name}': {a.description}" for a in agents])
    history_text = _format_history(state.get("history", []))

    resp = await chat_completion([
        {"role": "system", "content": INTENT_PROMPT.format(
            agent_list=agent_desc, history=history_text, message=state["user_message"]
        )},
        {"role": "user", "content": state["user_message"]}
    ])

    raw = resp.choices[0].message.content
    agent_name = _clean_agent_name(raw)

    return {"agent_name": agent_name}


def _clean_agent_name(raw: str) -> str:
    name = raw.strip().strip('"').strip("'").strip("`").strip(".")
    name = name.split("\n")[0].split(":")[0].split("：")[0].strip()
    return name


def _format_history(history: list[dict]) -> str:
    if not history:
        return "（无历史对话）"
    recent = history[-10:]
    lines = []
    for h in recent:
        role = "用户" if h.get("role") == "user" else "助手"
        content = h.get("content", "")[:200]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
```

### `graph/nodes/chat.py`

```python
from agents.chat_agent import ChatAgent
from agents.base import AgentState

chat_agent = ChatAgent()


async def chat_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await chat_agent.process(agent_state)
    response = result.get("response", "")
    return {
        "response": response,
        "messages": [{"role": "assistant", "content": response}],
    }
```

### `graph/nodes/profile.py`

```python
from agents.profile_agent import ProfileAgent
from agents.base import AgentState

profile_agent = ProfileAgent()


async def profile_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await profile_agent.process(agent_state)
    response = result.get("response", "")
    return {
        "response": response,
        "profile": result.get("profile"),
        "messages": [{"role": "assistant", "content": response}],
    }
```

### `graph/nodes/content_gen.py`、`mindmap.py`、`evaluation.py`

与 `profile.py` 结构一致，替换对应的 Agent 类名即可。

---

## 步骤四：构建图 — `graph/builder.py`

```python
from langgraph.graph import StateGraph, START, END

from graph.state import AgentGraphState
from graph.nodes.intent import classify_intent
from graph.nodes.chat import chat_node
from graph.nodes.profile import profile_node
from graph.nodes.content_gen import content_gen_node
from graph.nodes.mindmap import mindmap_node
from graph.nodes.evaluation import evaluation_node


def route_by_agent(state: AgentGraphState) -> str:
    agent_name = state.get("agent_name", "").lower()
    valid = {"chat", "profile", "content_gen", "mindmap", "evaluation"}
    if agent_name in valid:
        return agent_name

    # 模糊匹配
    for name in valid:
        if name in agent_name or agent_name in name:
            return name

    return "chat"


def compile_graph():
    builder = StateGraph(AgentGraphState)

    # 注册节点
    builder.add_node("intent_classifier", classify_intent)
    builder.add_node("chat", chat_node)
    builder.add_node("profile", profile_node)
    builder.add_node("content_gen", content_gen_node)
    builder.add_node("mindmap", mindmap_node)
    builder.add_node("evaluation", evaluation_node)

    # 边
    builder.add_edge(START, "intent_classifier")
    builder.add_conditional_edges(
        "intent_classifier",
        route_by_agent,
        {
            "chat": "chat",
            "profile": "profile",
            "content_gen": "content_gen",
            "mindmap": "mindmap",
            "evaluation": "evaluation",
        },
    )

    # 所有 Agent 节点执行完即结束
    for name in ["chat", "profile", "content_gen", "mindmap", "evaluation"]:
        builder.add_edge(name, END)

    return builder.compile()
```

---

## 步骤五：重写路由层 — `services/chat_service.py`

```python
from fastapi.responses import StreamingResponse
from core.sse import sse_stream
from services.safety_service import check_text_input, check_text
from graph.builder import compile_graph


async def route_to_agent(user_id: str, message: str, history: list[dict] | None = None):
    safe_message, ok = check_text_input(message)
    if not ok:
        async def deny():
            yield "抱歉，您的输入包含不当内容，请重新提问。"

        return StreamingResponse(
            sse_stream(deny()),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    graph = compile_graph()
    initial_state = {
        "user_id": user_id,
        "user_message": safe_message,
        "history": history or [],
    }

    # 使用 astream_events 获取流式输出
    async def event_stream():
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

    return StreamingResponse(
        sse_stream(event_stream()),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

> **注意**：`astream_events` 的 `on_chat_model_stream` 事件需要 LLM 客户端支持 LangChain 兼容的流式接口。如果当前 `core/llm_client.py` 使用自定义 HTTP 调用（例如讯飞 Spark），则需改为从 graph state 中提取最终的 `response` 字段来流式输出：

```python
    async def event_stream():
        async for chunk in graph.astream(initial_state, stream_mode="values"):
            if "response" in chunk:
                diff = chunk["response"][len(prev):]
                if diff:
                    yield diff
                prev = chunk["response"]
```

选择哪种方式取决于 `core/llm_client.py` 是否兼容 LangChain。优先尝试 `astream_events`；若不行，回退到 `astream + stream_mode="values"`。

---

## 步骤六：更新 `main.py`

```python
# main.py 中，保留 Agent 注册（节点中 get_all_agents() 依赖它），其余不变

from agents.registry import register, get_all_agents
from agents.profile_agent import ProfileAgent
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.evaluation_agent import EvaluationAgent
from agents.chat_agent import ChatAgent

register(ProfileAgent())
register(ContentGenAgent())
register(MindMapAgent())
register(EvaluationAgent())
register(ChatAgent())

print("Registered agents:", [a.name for a in get_all_agents()])
```

---

## 步骤七：事件系统兼容

`profile_agent.py:83` 和 `evaluation_agent.py:113` 中的 `emit()` 调用保持不变，在节点执行过程中仍然生效。

LangGraph 节点内创建 `asyncio.create_task(emit(...))` 是安全的，但需注意：如果后续要启用 checkpointing，fire-and-forget 任务不会被 replayed。Phase 1 不涉及 checkpointing，无需处理。

---

## 测试验证

### 功能测试

```python
# test_graph.py
import asyncio
from graph.builder import compile_graph

async def test():
    graph = compile_graph()
    result = await graph.ainvoke({
        "user_id": "test_user",
        "user_message": "什么是Python装饰器？",
        "history": [],
    })
    print("agent_name:", result.get("agent_name"))
    print("response:", result.get("response", "")[:200])

asyncio.run(test())
```

预期：`agent_name` 为 `chat`，`response` 包含装饰器解释。

### 流式端点测试

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","message":"写一个Python快速排序","history":[]}'
```

预期：逐 token 流式返回 JSON，行为与改造前一致。

### 回归测试

- `chat` 路由不走 graph 的其他端点（`/explain-term`、`/mark-terms`）功能不受影响
- `profile`、`content_gen`、`mindmap`、`evaluation` 各 Agent 的独立路由保持正常
- 前端 SSE 事件流正常连接，无明显延迟增加（增加应 < 100ms）

---

## 完成标准

- [ ] 5 个 Graph 节点可正常执行，agent_name 路由正确
- [ ] SSE 流式输出行为与改造前一致
- [ ] 现有 Agent 内部代码未被修改（除导入路径外）
- [ ] `services/chat_service.py` 不再直接调用 Agent 或 registry
- [ ] 所有非 `/api/chat/stream` 端点功能正常
- [ ] 无新增 lint 错误
