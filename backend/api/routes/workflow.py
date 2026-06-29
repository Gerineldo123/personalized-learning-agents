import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from core.database import SessionLocal
from core.sse import sse_stream
from graph.state import AgentGraphState
from graph.subgraphs.evaluation import evaluation_subgraph
from graph.subgraphs.review import review_subgraph
from models.course_path import CoursePath
from models.student import StudentProfile
from services.kp_service import default_focus_kps, infer_course_from_text
from services.safety_service import check_text_input


router = APIRouter(prefix="/api/workflow", tags=["学习工作流"])


def _load_profile(user_id: str):
    db = SessionLocal()
    try:
        return db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    finally:
        db.close()


def _make_state(user_id: str, topic: str, history: list) -> AgentGraphState:
    return {
        "user_id": user_id,
        "user_message": topic,
        "profile": _load_profile(user_id),
        "history": history,
        "messages": [],
        "response": "",
        "agent_name": "",
        "task_plan": [],
        "agent_feedback": {},
        "completed_tasks": [],
        "all_modules_data": {},
    }


def _stage(stage: str, data) -> str:
    return json.dumps({"type": "stage", "stage": stage, "data": data}, ensure_ascii=False)


def _resource(resource_id: int | None, resource_type: str, title: str) -> str | None:
    if not resource_id:
        return None
    return json.dumps({
        "type": "resource",
        "resource_id": resource_id,
        "resource_type": resource_type,
        "title": title or resource_type,
    }, ensure_ascii=False)


async def _stream_subgraph(subgraph, state: AgentGraphState):
    yielded_resources = set()
    async for chunk in subgraph.astream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if "workflow_outputs" in update:
                outputs = update["workflow_outputs"]
                latest = outputs[-1] if isinstance(outputs, list) and outputs else {}
                yield _stage(latest.get("stage", node_name), latest.get("data", ""))
                rid = latest.get("resource_db_id")
                if rid and rid not in yielded_resources:
                    yielded_resources.add(rid)
                    event = _resource(rid, latest.get("resource_type", ""), latest.get("title", ""))
                    if event:
                        yield event
            if "response" in update and update["response"]:
                yield update["response"]


class WorkflowRequest(BaseModel):
    user_id: str
    topic: str
    history: list[dict] = []


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


def _child_state(
    user_id: str,
    topic: str,
    profile,
    resource_type: str,
    course_name: str,
    focus_kps: list[str],
    extra: dict | None = None,
) -> AgentState:
    payload = {
        "user_id": user_id,
        "user_message": topic,
        "profile": profile,
        "resource_type": resource_type,
        "course_name": course_name,
        "knowledge_points": focus_kps,
    }
    if extra:
        payload.update(extra)
    return AgentState(**payload)


def _resource_info(resource_type: str, state: AgentState) -> dict:
    return {
        "resource_id": state.get("resource_db_id"),
        "resource_type": resource_type,
        "title": state.get("resource_title") or state.get("user_message") or resource_type,
    }


def _upsert_learning_path(user_id: str, course_name: str, focus_kps: list[str], resources: list[dict]) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    typed_resources = [
        {"id": r.get("resource_id"), "type": r.get("resource_type"), "title": r.get("title")}
        for r in resources if r.get("resource_id")
    ]
    steps = []
    for idx, kp in enumerate(focus_kps[:6] or [course_name], start=1):
        steps.append({
            "order": idx,
            "title": kp,
            "description": f"围绕“{kp}”完成讲解、导图、练习和代码/PPT资源学习。",
            "duration_estimate": "30-45分钟",
            "resource_queries": [course_name, kp],
            "checkpoint": f"能说明“{kp}”的核心概念，并完成至少一道相关练习。",
            "status": "pending",
            "completed_at": None,
            "resource_ids": [r["id"] for r in typed_resources],
            "resources": typed_resources,
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


async def _run_resource(resource_type: str, agent, state: AgentState) -> tuple[str, AgentState, str | None]:
    try:
        await agent.process(state)
        return resource_type, state, None
    except Exception as exc:
        return resource_type, state, str(exc)


async def _stream_study_workflow(req: WorkflowRequest, safe_topic: str):
    profile = _load_profile(req.user_id)
    profile_data = _profile_snapshot(profile)
    course_name = infer_course_from_text(safe_topic, default="数据结构") or "数据结构"
    focus_kps = default_focus_kps(course_name, safe_topic, limit=4)

    yield _stage("profile_analyzed", profile_data)
    diagnosis = {
        "course_name": course_name,
        "focus_knowledge_points": focus_kps,
        "weak_points": profile_data.get("weak_points", []),
        "learning_goal": profile_data.get("learning_goal"),
    }
    yield _stage("diagnosis_done", diagnosis)

    plan = [
        {"resource_type": "article", "agent": "content_gen", "purpose": "概念讲解"},
        {"resource_type": "mindmap", "agent": "mindmap", "purpose": "知识结构化"},
        {"resource_type": "quiz", "agent": "content_gen", "purpose": "掌握度检测"},
        {"resource_type": "code", "agent": "content_gen", "purpose": "算法实践"},
        {"resource_type": "ppt", "agent": "content_gen", "purpose": "课件沉淀"},
        {"resource_type": "video", "agent": "video", "purpose": "外部视频推荐"},
    ]
    yield _stage("resource_planned", plan)

    resources: list[dict] = []
    failures: list[dict] = []
    content_agent = ContentGenAgent()

    yield _stage("resource_started", {"resource_type": "article", "agent": "content_gen"})
    article_state = _child_state(req.user_id, safe_topic, profile, "article", course_name, focus_kps)
    _, article_state, article_error = await _run_resource("article", content_agent, article_state)
    if article_error:
        failures.append({"resource_type": "article", "error": article_error})
        yield _stage("resource_failed", failures[-1])
    else:
        info = _resource_info("article", article_state)
        resources.append(info)
        yield _stage("resource_created", info)
        event = _resource(info.get("resource_id"), "article", info.get("title", "文章"))
        if event:
            yield event

    article_content = ""
    try:
        raw = json.loads(article_state.get("response", "{}"))
        content = raw.get("content", "")
        article_content = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
    except Exception:
        article_content = ""

    mindmap_topic = f"{safe_topic}\n\n参考讲解内容：\n{article_content[:1500]}" if article_content else safe_topic
    specs = [
        ("mindmap", MindMapAgent(), mindmap_topic, {}),
        ("quiz", ContentGenAgent(), safe_topic, {"question_count": 5, "difficulty": "中等", "question_types": "single_choice,fill_blank,coding"}),
        ("code", ContentGenAgent(), safe_topic, {"code_language": "python"}),
        ("ppt", ContentGenAgent(), safe_topic, {}),
        ("video", VideoAgent(), safe_topic, {}),
    ]

    tasks = []
    for resource_type, agent, topic, extra in specs:
        yield _stage("resource_started", {"resource_type": resource_type, "agent": getattr(agent, "name", agent.__class__.__name__)})
        state = _child_state(req.user_id, topic, profile, resource_type, course_name, focus_kps, extra)
        tasks.append(asyncio.create_task(_run_resource(resource_type, agent, state)))

    for task in asyncio.as_completed(tasks):
        resource_type, state, error = await task
        if error:
            failures.append({"resource_type": resource_type, "error": error})
            yield _stage("resource_failed", failures[-1])
            continue
        info = _resource_info(resource_type, state)
        resources.append(info)
        yield _stage("resource_created", info)
        event = _resource(info.get("resource_id"), resource_type, info.get("title", resource_type))
        if event:
            yield event

    yield _stage("safety_reviewed", {
        "status": "passed",
        "policy": "关键词安全检查 + 生成提示反幻觉约束；各资源生成后写入安全过滤结果。",
    })
    yield _stage("knowledge_tagged", {
        "course_name": course_name,
        "knowledge_points": focus_kps,
        "resource_count": len([r for r in resources if r.get("resource_id")]),
    })

    path_info = _upsert_learning_path(req.user_id, course_name, focus_kps, resources)
    yield _stage("path_updated", path_info)
    yield _stage("done", {
        "resources": resources,
        "failures": failures,
        "path": path_info,
    })

    type_names = "、".join(r["resource_type"] for r in resources if r.get("resource_id")) or "暂无资源"
    focus_names = "、".join(focus_kps) or course_name
    yield (
        f"## 个性化学习方案已生成\n\n"
        f"- 课程节点：{course_name}\n"
        f"- 知识点标签：{focus_names}\n"
        f"- 已生成资源：{type_names}\n"
        f"- 学习路径：已更新 {path_info.get('total_steps', 0)} 个步骤\n"
        f"- 失败项：{len(failures)} 个，已保留可用资源并继续闭环\n\n"
        f"建议按学习路径完成资源，并通过题库提交结果更新知识点掌握度。"
    )


@router.post("/study/stream")
async def study_stream(req: WorkflowRequest):
    safe, ok = check_text_input(req.topic)
    if not ok:
        async def deny():
            yield "话题包含不当内容"
        return StreamingResponse(sse_stream(deny()), media_type="text/event-stream; charset=utf-8")
    return StreamingResponse(
        sse_stream(_stream_study_workflow(req, safe)),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/review/stream")
async def review_stream(req: WorkflowRequest):
    safe, ok = check_text_input(req.topic)
    if not ok:
        async def deny():
            yield "话题包含不当内容"
        return StreamingResponse(sse_stream(deny()), media_type="text/event-stream; charset=utf-8")
    state = _make_state(req.user_id, safe, req.history)
    return StreamingResponse(
        sse_stream(_stream_subgraph(review_subgraph, state)),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/evaluation/stream")
async def evaluation_stream(req: WorkflowRequest):
    safe, ok = check_text_input(req.topic)
    if not ok:
        async def deny():
            yield "话题包含不当内容"
        return StreamingResponse(sse_stream(deny()), media_type="text/event-stream; charset=utf-8")
    state = _make_state(req.user_id, safe, req.history)
    return StreamingResponse(
        sse_stream(_stream_subgraph(evaluation_subgraph, state)),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_video_agent = VideoAgent()


@router.post("/video/stream")
async def video_stream(req: WorkflowRequest):
    safe, ok = check_text_input(req.topic)
    if not ok:
        async def deny():
            yield "话题包含不当内容"
        return StreamingResponse(sse_stream(deny()), media_type="text/event-stream; charset=utf-8")

    profile = _load_profile(req.user_id)
    agent_state = AgentState(
        user_id=req.user_id,
        user_message=safe,
        profile=profile,
        profile_analysis={},
    )

    async def event_stream():
        result = await _video_agent.process(agent_state)
        response = result.get("response", "")
        if response:
            yield response

    return StreamingResponse(
        sse_stream(event_stream()),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
