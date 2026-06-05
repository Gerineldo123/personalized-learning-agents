import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from graph.subgraphs.study import study_subgraph
from graph.subgraphs.review import review_subgraph
from graph.subgraphs.evaluation import evaluation_subgraph
from agents.video_agent import VideoAgent
from agents.base import AgentState
from graph.state import AgentGraphState
from core.database import SessionLocal
from core.sse import sse_stream
from models.student import StudentProfile
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


async def _stream_subgraph(subgraph, state: AgentGraphState):
    async for chunk in subgraph.astream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            if "workflow_outputs" in update:
                outputs = update["workflow_outputs"]
                latest = outputs[-1] if isinstance(outputs, list) and outputs else {}
                yield json.dumps({
                    "type": "stage",
                    "stage": latest.get("stage", node_name),
                    "data": latest.get("data", ""),
                }, ensure_ascii=False)
            if "response" in update and update["response"]:
                yield update["response"]


class WorkflowRequest(BaseModel):
    user_id: str
    topic: str
    history: list[dict] = []


@router.post("/study/stream")
async def study_stream(req: WorkflowRequest):
    safe, ok = check_text_input(req.topic)
    if not ok:
        async def deny():
            yield "话题包含不当内容"
        return StreamingResponse(sse_stream(deny()), media_type="text/event-stream; charset=utf-8")
    state = _make_state(req.user_id, safe, req.history)
    return StreamingResponse(
        sse_stream(_stream_subgraph(study_subgraph, state)),
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
