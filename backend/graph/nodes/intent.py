from graph.state import AgentGraphState
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
