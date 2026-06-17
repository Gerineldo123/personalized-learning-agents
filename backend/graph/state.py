from typing import TypedDict, Annotated, Any, NotRequired
from langgraph.graph.message import add_messages


class AgentGraphState(TypedDict):
    # 基础
    user_id: str
    user_message: str
    profile: Any
    history: list[dict]
    messages: Annotated[list, add_messages]
    response: str
    agent_name: str

    # 工作流控制
    task_plan: list[dict]
    agent_feedback: dict
    completed_tasks: list[dict]

    # 各模块产出
    profile_analysis: NotRequired[dict]
    generated_article: NotRequired[str]
    generated_mindmap: NotRequired[str]
    generated_quiz: NotRequired[dict]
    evaluation_report: NotRequired[dict]
    mistake_analysis: NotRequired[dict]
    path_suggestion: NotRequired[str]
    workflow_outputs: NotRequired[list[dict]]

    # 跨模块共享
    all_modules_data: NotRequired[dict]
    _sse_queue: NotRequired[Any]   # asyncio.Queue，用于 skill 实时推送 SSE
    _session_id: NotRequired[str]  # 对应 _sse_queues 全局字典的 key
