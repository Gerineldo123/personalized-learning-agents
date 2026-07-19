import json
import uuid
from datetime import datetime, timezone
from typing import Any


RESOURCE_AGENT_META: dict[str, dict[str, str]] = {
    "article": {"agent_key": "content_article", "agent_name": "内容生成智能体", "role": "生成课程讲解文章"},
    "mindmap": {"agent_key": "mindmap", "agent_name": "思维导图智能体", "role": "梳理知识结构"},
    "quiz": {"agent_key": "quiz", "agent_name": "出题智能体", "role": "生成诊断与练习题"},
    "code": {"agent_key": "code", "agent_name": "代码案例智能体", "role": "生成实操代码案例"},
    "anime": {"agent_key": "anime", "agent_name": "动画智能体", "role": "生成可视化动画"},
    "ppt": {"agent_key": "ppt", "agent_name": "课件智能体", "role": "创建 AiPPT 分步课件任务"},
    "video": {"agent_key": "video", "agent_name": "视频智能体", "role": "检索与推荐教学视频"},
    "evaluation": {"agent_key": "evaluation", "agent_name": "评估智能体", "role": "评估学习效果"},
}

STAGE_META: dict[str, dict[str, str]] = {
    "profile_analyzed": {"agent_key": "profile", "agent_name": "画像智能体", "role": "读取画像与学习偏好"},
    "diagnosis_done": {"agent_key": "diagnosis", "agent_name": "诊断智能体", "role": "定位课程与知识点"},
    "resource_planned": {"agent_key": "planner", "agent_name": "规划智能体", "role": "拆解资源生成任务"},
    "safety_reviewed": {"agent_key": "review", "agent_name": "审查智能体", "role": "检查生成结果安全性"},
    "knowledge_tagged": {"agent_key": "knowledge_graph", "agent_name": "知识图谱智能体", "role": "绑定课程与知识点标签"},
    "path_updated": {"agent_key": "path", "agent_name": "路径智能体", "role": "同步学习路径"},
    "done": {"agent_key": "summary", "agent_name": "汇总智能体", "role": "汇总协作结果"},
}

EVENT_TYPE_BY_STATUS = {
    "running": "agent_started",
    "completed": "agent_completed",
    "error": "agent_failed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(value: Any, limit: int = 180) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def _base_event(meta: dict[str, str], stage: str, status: str, data: Any) -> dict:
    return {
        "type": EVENT_TYPE_BY_STATUS.get(status, "agent_progress"),
        "event_id": str(uuid.uuid4()),
        "agent_key": meta["agent_key"],
        "agent_name": meta["agent_name"],
        "role": meta["role"],
        "stage": stage,
        "status": status,
        "timestamp": _now(),
        "input_summary": "",
        "output_summary": _short(data),
    }


def collaboration_event(stage: str, data: Any) -> dict:
    status = "completed"
    meta = STAGE_META.get(stage, {"agent_key": stage, "agent_name": "协作智能体", "role": "执行协作步骤"})

    if stage == "resource_started":
        resource_type = data.get("resource_type") if isinstance(data, dict) else ""
        meta = RESOURCE_AGENT_META.get(resource_type or "", meta)
        status = "running"
    elif stage == "resource_created":
        resource_type = data.get("resource_type") if isinstance(data, dict) else ""
        meta = RESOURCE_AGENT_META.get(resource_type or "", meta)
        status = "completed"
    elif stage == "resource_failed":
        resource_type = data.get("resource_type") if isinstance(data, dict) else ""
        meta = RESOURCE_AGENT_META.get(resource_type or "", meta)
        status = "error"
    elif stage == "done":
        status = "completed"

    event = _base_event(meta, stage, status, data)
    if isinstance(data, dict):
        resource_type = data.get("resource_type")
        if resource_type:
            event["resource_type"] = resource_type
        if data.get("resource_id"):
            event["resource_id"] = data.get("resource_id")
        if data.get("title"):
            event["resource_title"] = data.get("title")
        if data.get("error"):
            event["error"] = data.get("error")
        if data.get("course_name"):
            event["course_name"] = data.get("course_name")
        if data.get("knowledge_points"):
            event["knowledge_points"] = data.get("knowledge_points")
        if data.get("focus_knowledge_points"):
            event["knowledge_points"] = data.get("focus_knowledge_points")
        if data.get("task"):
            event["input_summary"] = data.get("task")
            if stage == "resource_started":
                event["output_summary"] = _short(data.get("task"))
        if data.get("ppt_session"):
            event["ppt_session"] = data.get("ppt_session")
            event["output_summary"] = "已创建 AiPPT 分步生成任务，等待大纲确认和模板选择"
    elif isinstance(data, list) and stage == "resource_planned":
        event["output_summary"] = "计划生成：" + "、".join(
            str(item.get("resource_type", "")) for item in data if isinstance(item, dict)
        )
    if stage == "done":
        event["type"] = "graph_done"
    return event


def collaboration_events_from_workflow(items: list[dict] | None) -> list[dict]:
    events: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if "agent_key" in item and "stage" in item:
            events.append(item)
            continue
        stage = item.get("stage")
        if stage:
            events.append(collaboration_event(stage, item.get("data")))
    return events


def collaboration_sse_payload(event: dict) -> str:
    return json.dumps({"type": "agent_event", "event": event}, ensure_ascii=False, default=str)
