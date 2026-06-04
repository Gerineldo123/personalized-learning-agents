import json
from graph.state import AgentGraphState
from core.llm_client import chat_completion
from agents.registry import get_all_agents

# 各意图对应的初始任务计划
_INTENT_PLANS = {
    "study": [
        {"agent": "profile_analysis", "task": "分析学生当前水平", "priority": 5},
        {"agent": "study_content", "task": "生成适配难度的学习内容", "priority": 5},
        {"agent": "content_review", "task": "审核内容质量（自动并行分发思维导图+练习题）", "priority": 4},
    ],
    "review": [
        {"agent": "mistake_analysis", "task": "分析错题薄弱点", "priority": 5},
        {"agent": "study_content", "task": "针对薄弱点生成讲解内容", "priority": 5},
        {"agent": "content_review", "task": "审核内容质量（自动并行分发练习题）", "priority": 4},
    ],
    "evaluation": [
        {"agent": "evaluation", "task": "评估学习效果", "priority": 5},
        {"agent": "profile_update", "task": "更新学生画像", "priority": 4},
        {"agent": "path_suggest", "task": "推荐下一步学习路径", "priority": 4},
    ],
    "chat": [{"agent": "chat", "task": "回答用户问题", "priority": 5}],
    "profile": [{"agent": "profile", "task": "构建/更新学生画像", "priority": 5}],
    "content_gen": [{"agent": "content_gen", "task": "生成学习资源", "priority": 5}],
    "mindmap": [{"agent": "mindmap", "task": "生成思维导图", "priority": 5}],
}

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
- 如果用户要求生成思维导图/知识图谱 → mindmap
- 如果用户要求评估/测评学习效果 → evaluation
- 如果用户描述自己的信息（专业/年级/目标）用于构建画像 → profile
- 其他对话/问答 → chat

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

    plan = _INTENT_PLANS.get(agent_name, _INTENT_PLANS["chat"])

    return {
        "agent_name": agent_name,
        "task_plan": plan,
        "agent_feedback": {},
        "supervisor_iteration": 0,
        "completed_tasks": [],
    }


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
