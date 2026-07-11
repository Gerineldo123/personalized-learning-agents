import json
from datetime import datetime, timezone

from langgraph.config import get_stream_writer
from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.evaluation_agent import EvaluationAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from core.database import SessionLocal
from graph.state import AgentGraphState
from models.course_path import CoursePath
from services.agent_collaboration_service import collaboration_event, collaboration_events_from_workflow
from services.curriculum_service import course_name_map, get_course_kp_graph, load_curriculum_by_major
from services.kp_service import default_focus_kps, infer_course_from_text


RESOURCE_PLAN = {
    "article": ("content_gen", "概念讲解"),
    "mindmap": ("mindmap", "知识结构化"),
    "quiz": ("content_gen", "掌握度检测"),
    "code": ("content_gen", "算法实践"),
    "ppt": ("content_gen", "课件沉淀"),
    "video": ("video", "外部视频推荐"),
    "evaluation": ("evaluation", "学习评估"),
}

DEFAULT_RESOURCE_TYPES = ["article", "mindmap", "quiz", "code", "ppt", "video"]
MIN_COURSE_PATH_KPS = 3


def _profile_snapshot(profile) -> dict:
    if not profile:
        return {
            "major": "未知",
            "grade": "未知",
            "knowledge_base": {},
            "weak_points": [],
            "learning_goal": "扎实掌握课程核心知识点",
        }
    return {
        "major": profile.major or "未知",
        "grade": profile.grade or "未知",
        "knowledge_base": profile.knowledge_base or {},
        "weak_points": profile.weak_points or [],
        "learning_goal": profile.learning_goal or "扎实掌握课程核心知识点",
        "preferred_format": profile.preferred_format or [],
    }


def _event(stage: str, data) -> dict:
    return {"stage": stage, "data": data}


def _write_agent_event(stage: str, data) -> None:
    try:
        get_stream_writer()({"type": "agent_event", "event": collaboration_event(stage, data)})
    except Exception:
        pass


def _resource_info(resource_type: str, state: AgentState) -> dict:
    info = {
        "resource_type": resource_type,
        "resource_id": state.get("resource_db_id"),
        "title": state.get("resource_title") or state.get("user_message") or resource_type,
    }
    if state.get("ppt_session"):
        info["ppt_session"] = state.get("ppt_session")
        info["status"] = "pending_step_by_step"
    return info


def _article_content(state: AgentGraphState) -> str:
    for resource in reversed(state.get("generated_resources") or []):
        if resource.get("resource_type") == "article":
            return str(resource.get("content_preview") or "")
    return ""


def _extract_content_preview(agent_state: AgentState) -> str:
    try:
        raw = json.loads(agent_state.get("response", "{}"))
        content = raw.get("content", "")
        return json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
    except Exception:
        return ""


def _profile_major(profile) -> str:
    return str(getattr(profile, "major", "") or "")


def _curriculum_course(course_name: str | None, major: str = "") -> dict | None:
    if not course_name:
        return None
    try:
        curriculum = load_curriculum_by_major(major or "")
    except Exception:
        return None
    courses = course_name_map(curriculum)
    return courses.get(course_name) or next(
        (course for course in curriculum.get("courses", []) if course.get("name") == course_name),
        None,
    )


def _course_graph_kps(course_name: str | None, major: str = "") -> list[str]:
    if not course_name:
        return []
    graph = get_course_kp_graph(course_name, major or "")
    return [str(node.get("id")).strip() for node in graph.get("nodes", []) if node.get("id")]


def _classify_study_scope(
    *,
    topic: str,
    explicit_course: str | None,
    course_name: str | None,
    focus_kps: list[str],
    profile,
) -> tuple[str, list[str], list[str], str]:
    major = _profile_major(profile)
    course = _curriculum_course(course_name, major)
    course_kps = _course_graph_kps(course_name, major) if course and course.get("kp_file") else []
    allowed = set(course_kps)
    bound_kps = [kp for kp in focus_kps if kp in allowed] if allowed else []

    if course and course_kps:
        course_text_match = bool(course_name and course_name in (topic or ""))
        if explicit_course or course_text_match:
            if len(bound_kps) < MIN_COURSE_PATH_KPS:
                bound_kps = course_kps[:4]
            return "course", bound_kps, course_kps, "matched_curriculum_course"
        if bound_kps:
            return "knowledge_point", bound_kps, course_kps, "matched_course_knowledge_point"

    if course and not course_kps:
        return "extension", [], [], "course_has_no_kp_file"
    if course_name and focus_kps:
        return "extension", [], [], "matched_outside_user_curriculum"
    return "extension", [], [], "not_bound_to_curriculum_graph"


def _upsert_learning_path(
    user_id: str,
    course_name: str | None,
    focus_kps: list[str],
    resources: list[dict],
    *,
    study_scope: str = "",
    course_kps: list[str] | None = None,
) -> dict:
    if not course_name:
        return {"skipped": True, "reason": "未识别课程节点，未更新学习路径"}

    if study_scope != "course":
        return {"skipped": True, "reason": "知识点专项或拓展学习不生成课程学习路径", "study_scope": study_scope}

    allowed = set(course_kps or focus_kps)
    valid_kps = [kp for kp in focus_kps if kp in allowed]
    if len(valid_kps) < MIN_COURSE_PATH_KPS:
        return {
            "skipped": True,
            "reason": f"课程路径至少需要覆盖 {MIN_COURSE_PATH_KPS} 个课程知识点，当前覆盖不足",
            "study_scope": study_scope,
            "covered_knowledge_points": valid_kps,
        }

    now = datetime.now(timezone.utc).isoformat()
    typed_resources = [
        {"id": r.get("resource_id"), "type": r.get("resource_type"), "title": r.get("title")}
        for r in resources if r.get("resource_id")
    ]
    path_titles = valid_kps[:6]
    steps = []
    for idx, title in enumerate(path_titles, start=1):
        steps.append({
            "order": idx,
            "title": title,
            "description": f"围绕“{title}”完成讲解、导图、练习和代码/PPT资源学习。",
            "duration_estimate": "30-45分钟",
            "resource_queries": [course_name, title],
            "checkpoint": f"能说明“{title}”的核心概念，并完成至少一道相关练习。",
            "status": "pending",
            "mastery_status": "unverified",
            "completed_at": None,
            "course_name": course_name,
            "knowledge_points": [title],
            "resource_types": ["article", "mindmap", "quiz"],
            "resource_ids": [r["id"] for r in typed_resources],
            "resources": typed_resources,
            "path_scope": "course",
        })

    db = SessionLocal()
    try:
        path = db.query(CoursePath).filter(
            CoursePath.user_id == user_id,
            CoursePath.course_name == course_name,
            CoursePath.status == "active",
        ).first()
        if not path:
            path = CoursePath(
                user_id=user_id,
                course_name=course_name,
                steps=steps,
                total_steps=len(steps),
                done_steps=0,
                progress=0.0,
                status="active",
            )
            db.add(path)
        else:
            previous_steps = {s.get("title"): s for s in (path.steps or []) if isinstance(s, dict)}
            for step in steps:
                prev = previous_steps.get(step.get("title"))
                if prev:
                    step["status"] = prev.get("status", "pending")
                    step["completed_at"] = prev.get("completed_at")
            path.steps = steps
            path.total_steps = len(steps)
            path.done_steps = sum(1 for s in steps if s.get("status") == "done")
            path.progress = round(path.done_steps / max(path.total_steps, 1), 4)
            path.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(path)
        return {
            "id": path.id,
            "course_name": course_name,
            "total_steps": path.total_steps,
            "progress": path.progress,
            "updated_at": now,
        }
    finally:
        db.close()


async def profile_diagnosis_node(state: AgentGraphState) -> dict:
    topic = state.get("user_message", "")
    profile = state.get("profile")
    explicit_course = state.get("course_name")
    course_name = explicit_course or infer_course_from_text(topic, default=None)
    focus_kps = list(state.get("knowledge_points") or [])
    if not focus_kps:
        focus_kps = default_focus_kps(course_name, topic, limit=4) if course_name else default_focus_kps(None, topic, limit=4)

    study_scope, focus_kps, course_kps, scope_reason = _classify_study_scope(
        topic=topic,
        explicit_course=explicit_course,
        course_name=course_name,
        focus_kps=focus_kps,
        profile=profile,
    )
    if study_scope == "extension":
        course_name = None

    profile_data = _profile_snapshot(profile)
    diagnosis = {
        "course_name": course_name,
        "focus_knowledge_points": focus_kps,
        "weak_points": profile_data.get("weak_points", []),
        "learning_goal": profile_data.get("learning_goal"),
        "study_scope": study_scope,
        "scope_reason": scope_reason,
        "course_knowledge_point_count": len(course_kps),
    }
    workflow = [_event("profile_analyzed", profile_data), _event("diagnosis_done", diagnosis)]
    return {
        "course_name": course_name,
        "knowledge_points": focus_kps,
        "study_scope": study_scope,
        "course_knowledge_points": course_kps,
        "profile_analysis": diagnosis,
        "workflow_outputs": workflow,
        "agent_events": collaboration_events_from_workflow(workflow),
    }


async def resource_plan_node(state: AgentGraphState) -> dict:
    requested = list(state.get("requested_resource_types") or DEFAULT_RESOURCE_TYPES)
    requested = [rtype for rtype in requested if rtype in RESOURCE_PLAN]
    if not requested:
        requested = ["article"]

    plan = [
        {"resource_type": rtype, "agent": RESOURCE_PLAN[rtype][0], "purpose": RESOURCE_PLAN[rtype][1]}
        for rtype in requested
    ]
    jobs = [{"resource_type": rtype} for rtype in requested if rtype != "article"]
    workflow = [_event("resource_planned", plan)]
    return {
        "requested_resource_types": requested,
        "resource_jobs": jobs,
        "workflow_outputs": workflow,
        "agent_events": collaboration_events_from_workflow(workflow),
    }


async def article_gen_node(state: AgentGraphState) -> dict:
    requested = set(state.get("requested_resource_types") or [])
    if "article" not in requested:
        return {}

    return await _run_resource_node(state, "article", state.get("user_message", ""))


def _dispatch_parallel_resources(state: AgentGraphState):
    jobs = state.get("resource_jobs") or []
    if not jobs:
        return "safety_review"
    return [
        Send("resource_gen", {**state, "current_resource_type": job["resource_type"]})
        for job in jobs
    ]


async def resource_gen_node(state: AgentGraphState) -> dict:
    resource_type = state.get("current_resource_type")
    if not resource_type:
        return {}

    message = state.get("user_message", "")
    if resource_type == "mindmap":
        article = _article_content(state)
        if article:
            message = f"{message}\n\n参考讲解内容：\n{article[:1500]}"
    return await _run_resource_node(state, resource_type, message)


async def _run_resource_node(state: AgentGraphState, resource_type: str, message: str) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=message,
        profile=state.get("profile"),
        resource_type=resource_type,
        course_name=state.get("course_name"),
        knowledge_points=state.get("knowledge_points") or [],
    )
    if resource_type == "quiz":
        agent_state.update({"question_count": 5, "difficulty": "中等", "question_types": "single_choice,fill_blank,coding"})
    elif resource_type == "code":
        agent_state.update({"code_language": "python"})

    agent_name = RESOURCE_PLAN.get(resource_type, ("content_gen", ""))[0]
    started = _event("resource_started", {"resource_type": resource_type, "agent": agent_name})
    _write_agent_event("resource_started", started["data"])
    try:
        if resource_type == "mindmap":
            await MindMapAgent().process(agent_state)
        elif resource_type == "video":
            await VideoAgent().process(agent_state)
        elif resource_type == "evaluation":
            await EvaluationAgent().process(agent_state)
        else:
            await ContentGenAgent().process(agent_state)
    except Exception as exc:
        failure = {"resource_type": resource_type, "error": str(exc)}
        _write_agent_event("resource_failed", failure)
        events = [started, _event("resource_failed", failure)]
        return {
            "orchestration_failures": [failure],
            "orchestration_events": events,
            "agent_events": collaboration_events_from_workflow(events),
        }

    info = _resource_info(resource_type, agent_state)
    preview = _extract_content_preview(agent_state)
    if preview:
        info["content_preview"] = preview[:2000]
    _write_agent_event("resource_created", info)
    events = [started, _event("resource_created", info)]
    return {
        "generated_resources": [info] if info.get("resource_id") or info.get("ppt_session") else [],
        "orchestration_events": events,
        "agent_events": collaboration_events_from_workflow(events),
    }


async def safety_review_node(state: AgentGraphState) -> dict:
    data = {
        "status": "passed",
        "policy": "关键词安全检查 + 生成提示反幻觉约束；各资源生成后写入安全过滤结果。",
    }
    event = _event("safety_reviewed", data)
    return {
        "workflow_outputs": list(state.get("orchestration_events") or []) + [event],
        "agent_events": collaboration_events_from_workflow([event]),
    }


async def graph_tagging_node(state: AgentGraphState) -> dict:
    resources = [r for r in (state.get("generated_resources") or []) if r.get("resource_id")]
    data = {
        "course_name": state.get("course_name"),
        "knowledge_points": state.get("knowledge_points") or [],
        "resource_count": len(resources),
    }
    event = _event("knowledge_tagged", data)
    return {
        "workflow_outputs": list(state.get("workflow_outputs") or []) + [event],
        "agent_events": collaboration_events_from_workflow([event]),
    }


async def path_update_node(state: AgentGraphState) -> dict:
    path_info = _upsert_learning_path(
        state["user_id"],
        state.get("course_name"),
        state.get("knowledge_points") or [],
        state.get("generated_resources") or [],
        study_scope=state.get("study_scope") or "",
        course_kps=state.get("course_knowledge_points") or [],
    )
    event = _event("path_updated", path_info)
    return {
        "path_info": path_info,
        "workflow_outputs": list(state.get("workflow_outputs") or []) + [event],
        "agent_events": collaboration_events_from_workflow([event]),
    }


async def finalize_node(state: AgentGraphState) -> dict:
    resources = [r for r in (state.get("generated_resources") or []) if r.get("resource_id")]
    failures = state.get("orchestration_failures") or []
    course_name = state.get("course_name")
    knowledge_points = state.get("knowledge_points") or []
    path_info = state.get("path_info") or {}
    done = {"resources": resources, "failures": failures, "path": path_info}
    type_names = "、".join(r["resource_type"] for r in resources) or "暂无资源"
    focus_names = "、".join(knowledge_points) or (course_name or "未绑定课程")
    response = (
        f"## 个性化学习方案已生成\n\n"
        f"- 课程节点：{course_name or '未识别'}\n"
        f"- 知识点标签：{focus_names}\n"
        f"- 已生成资源：{type_names}\n"
        f"- 学习路径：{'已更新 ' + str(path_info.get('total_steps', 0)) + ' 个步骤' if not path_info.get('skipped') else path_info.get('reason')}\n"
        f"- 失败项：{len(failures)} 个，已保留可用资源并继续闭环\n\n"
        f"建议按学习路径完成资源，并通过题库提交结果更新知识点掌握度。"
    )
    event = _event("done", done)
    return {
        "response": response,
        "workflow_outputs": list(state.get("workflow_outputs") or []) + [event],
        "agent_events": collaboration_events_from_workflow([event]),
    }


async def finalize_node(state: AgentGraphState) -> dict:
    resources = [r for r in (state.get("generated_resources") or []) if r.get("resource_id")]
    ppt_sessions = [r for r in (state.get("generated_resources") or []) if r.get("ppt_session")]
    failures = state.get("orchestration_failures") or []
    course_name = state.get("course_name")
    knowledge_points = state.get("knowledge_points") or []
    path_info = state.get("path_info") or {}
    study_scope = state.get("study_scope") or "extension"
    scope_label = {
        "course": "课程学习",
        "knowledge_point": "知识点专项",
        "extension": "拓展学习",
    }.get(study_scope, "拓展学习")
    done = {
        "resources": resources,
        "ppt_sessions": ppt_sessions,
        "failures": failures,
        "path": path_info,
        "study_scope": study_scope,
        "scope_label": scope_label,
    }
    type_items = [r["resource_type"] for r in resources] + ["ppt_session" for _ in ppt_sessions]
    type_names = "、".join(type_items) or "暂无资源"
    focus_names = "、".join(knowledge_points) or (course_name or "未绑定课程")
    path_text = (
        f"已更新 {path_info.get('total_steps', 0)} 个步骤"
        if not path_info.get("skipped")
        else path_info.get("reason")
    )
    response = (
        "## 个性化学习方案已生成\n\n"
        f"- 学习类型：{scope_label}\n"
        f"- 课程节点：{course_name or '未绑定培养方案课程'}\n"
        f"- 知识点标签：{focus_names}\n"
        f"- 已生成资源：{type_names}\n"
        f"- PPT 分步会话：{len(ppt_sessions)} 个\n"
        f"- 学习路径：{path_text}\n"
        f"- 失败项：{len(failures)} 个\n\n"
        "说明：学习路径只用于课程级、多知识点学习；知识点专项和拓展学习只生成资源包。掌握度仍由题目提交结果更新。"
    )
    event = _event("done", done)
    return {
        "response": response,
        "workflow_outputs": list(state.get("workflow_outputs") or []) + [event],
        "agent_events": collaboration_events_from_workflow([event]),
    }


_builder = StateGraph(AgentGraphState)
_builder.add_node("profile_diagnosis", profile_diagnosis_node)
_builder.add_node("resource_plan", resource_plan_node)
_builder.add_node("article_gen", article_gen_node)
_builder.add_node("resource_gen", resource_gen_node)
_builder.add_node("safety_review", safety_review_node)
_builder.add_node("graph_tagging", graph_tagging_node)
_builder.add_node("path_update", path_update_node)
_builder.add_node("finalize", finalize_node)

_builder.set_entry_point("profile_diagnosis")
_builder.add_edge("profile_diagnosis", "resource_plan")
_builder.add_edge("resource_plan", "article_gen")
_builder.add_conditional_edges("article_gen", _dispatch_parallel_resources, ["resource_gen", "safety_review"])
_builder.add_edge("resource_gen", "safety_review")
_builder.add_edge("safety_review", "graph_tagging")
_builder.add_edge("graph_tagging", "path_update")
_builder.add_edge("path_update", "finalize")
_builder.add_edge("finalize", END)

resource_orchestration_graph = _builder.compile()
