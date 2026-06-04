import json
from graph.state import AgentGraphState
from core.llm_client import chat_completion
from agents.registry import get_all_agents

SUPERVISOR_PROMPT = """你是个性化学习系统的总调度员。根据用户请求、已完成任务和上一个 Agent 的反馈，决定下一步执行哪个 Agent。

可用 Worker Agent：
{agent_list}

用户原始请求：{user_message}
当前任务计划：{plan}
已完成任务：{completed}
上一个 Agent 的反馈：{feedback}
已执行循环次数：{iteration}

决策规则：
1. 按 task_plan 顺序执行尚未完成的任务
2. 如果 feedback.needs_regeneration = true，重新执行上一个内容生成任务
3. 如果 feedback.needs_mindmap = true 且思维导图未生成，插入 study_mindmap
4. 如果 feedback.weaknesses_found 非空且未安排针对性练习，插入 quiz_gen
5. 所有计划任务完成 → 返回 "summary"
6. 迭代超过 8 次 → 强制返回 "summary"

返回 JSON（只返回 JSON，不含其他内容）：
{{"next_agent": "<agent名称或summary>", "updated_plan": [...], "reasoning": "..."}}"""

_VALID_WORKERS = {
    "profile_analysis", "study_content", "study_mindmap", "quiz_gen",
    "mistake_analysis", "evaluation", "profile_update", "path_suggest",
    "chat", "profile", "content_gen", "mindmap",
}


async def supervisor_node(state: AgentGraphState) -> dict:
    iteration = state.get("supervisor_iteration", 0) + 1

    if iteration > 8:
        return {
            "current_task": "summary",
            "supervisor_iteration": iteration,
            "agent_feedback": {"force_summary": True},
        }

    agents = get_all_agents()
    agent_desc = "\n".join([f"- {a.name}: {a.description}" for a in agents])
    completed_names = {t.get("agent") for t in (state.get("completed_tasks") or [])}
    plan = state.get("task_plan") or []
    remaining = [t for t in plan if t.get("agent") not in completed_names]

    resp = await chat_completion([
        {"role": "system", "content": SUPERVISOR_PROMPT.format(
            agent_list=agent_desc,
            user_message=state["user_message"],
            plan=json.dumps(remaining, ensure_ascii=False),
            completed=json.dumps(list(completed_names), ensure_ascii=False),
            feedback=json.dumps(state.get("agent_feedback", {}), ensure_ascii=False),
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
        next_agent = remaining[0]["agent"] if remaining else "summary"
        decision = {"next_agent": next_agent, "updated_plan": plan}

    next_agent = decision.get("next_agent", "summary")
    if next_agent not in _VALID_WORKERS:
        next_agent = "summary"

    # 如果上一个 worker 标记所有任务完成且无剩余计划，直接结束
    if state.get("agent_feedback", {}).get("all_tasks_done") and not remaining:
        next_agent = "summary"

    return {
        "task_plan": decision.get("updated_plan", plan),
        "current_task": next_agent,
        "supervisor_iteration": iteration,
    }
