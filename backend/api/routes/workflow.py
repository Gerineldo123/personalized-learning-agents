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
from graph.subgraphs.resource_orchestration import DEFAULT_RESOURCE_TYPES, resource_orchestration_graph
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
    state = _make_state(req.user_id, safe_topic, req.history)
    state["requested_resource_types"] = DEFAULT_RESOURCE_TYPES
    yielded_resources = set()
    yielded_events = set()

    async for chunk in resource_orchestration_graph.astream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            events = []
            if isinstance(update.get("workflow_outputs"), list):
                events.extend(update["workflow_outputs"])
            if isinstance(update.get("orchestration_events"), list):
                events.extend(update["orchestration_events"])
            for item in events:
                stage = item.get("stage", node_name)
                data = item.get("data", "")
                key = json.dumps({"stage": stage, "data": data}, ensure_ascii=False, sort_keys=True, default=str)
                if key in yielded_events:
                    continue
                yielded_events.add(key)
                yield _stage(stage, data)
                if stage == "resource_created" and isinstance(data, dict):
                    rid = data.get("resource_id")
                    if rid and rid not in yielded_resources:
                        yielded_resources.add(rid)
                        event = _resource(rid, data.get("resource_type", ""), data.get("title", ""))
                        if event:
                            yield event
            if update.get("response"):
                yield update["response"]


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
