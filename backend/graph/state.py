from typing import TypedDict, Annotated, Any
from typing_extensions import NotRequired
from langgraph.graph.message import add_messages


def append_list(left: list | None, right) -> list:
    base = list(left or [])
    if right is None:
        return base
    if isinstance(right, list):
        return base + right
    return base + [right]


def merge_dict(left: dict | None, right: dict | None) -> dict:
    merged = dict(left or {})
    if right:
        merged.update(right)
    return merged


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
    agent_events: NotRequired[Annotated[list[dict], append_list]]

    # 资源编排图
    course_name: NotRequired[str | None]
    knowledge_points: NotRequired[list[str]]
    requested_resource_types: NotRequired[list[str]]
    resource_jobs: NotRequired[list[dict]]
    current_resource_type: NotRequired[str]
    generated_resources: Annotated[list[dict], append_list]
    orchestration_failures: Annotated[list[dict], append_list]
    orchestration_events: Annotated[list[dict], append_list]
    path_info: NotRequired[dict]

    # 任务模式 skill 并行执行
    current_skill_name: NotRequired[str]
    skill_result_items: Annotated[list[dict], append_list]
    skill_workflow_outputs: Annotated[list[dict], append_list]

    # 跨模块共享
    all_modules_data: NotRequired[Annotated[dict, merge_dict]]
    _sse_queue: NotRequired[Any]   # asyncio.Queue，用于 skill 实时推送 SSE
    _session_id: NotRequired[str]  # 对应 _sse_queues 全局字典的 key
