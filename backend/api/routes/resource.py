from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime
import json
from api.deps import get_db
from models.resource import LearningResource
from models.student import StudentProfile
from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from agents.evaluation_agent import EvaluationAgent
from agents.orchestrator_agent import OrchestratorAgent
from services.event_service import emit
from services.rag_service import search_rag
from services.kp_service import infer_resource_tags, update_knowledge_base
import asyncio

router = APIRouter(prefix="/api/resources", tags=["资源"])


class ResourceTagRequest(BaseModel):
    user_id: str
    course_name: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    kp_weights: dict[str, float] | None = None


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _resource_text(resource: LearningResource) -> str:
    parts = [
        resource.title or "",
        resource.course_name or "",
        " ".join(_as_list(resource.knowledge_points)),
        " ".join(_as_list(resource.tags)),
    ]
    try:
        parts.append(json.dumps(resource.content or {}, ensure_ascii=False))
    except TypeError:
        parts.append(str(resource.content or ""))
    return " ".join(parts)


def _apply_graph_tags(
    resource: LearningResource,
    course_name: str | None = None,
    knowledge_points: list[str] | None = None,
    overwrite: bool = True,
) -> bool:
    if not overwrite and (resource.course_name or _as_list(resource.knowledge_points)):
        return False

    inferred = infer_resource_tags(
        _resource_text(resource),
        course_name=course_name or resource.course_name,
        knowledge_points=knowledge_points or _as_list(resource.knowledge_points),
    )
    changed = False
    if inferred["course_name"] and inferred["course_name"] != resource.course_name:
        resource.course_name = inferred["course_name"]
        changed = True
    if inferred["knowledge_points"] and inferred["knowledge_points"] != _as_list(resource.knowledge_points):
        resource.knowledge_points = inferred["knowledge_points"]
        changed = True
    if inferred["kp_weights"] and inferred["kp_weights"] != (resource.kp_weights or {}):
        resource.kp_weights = inferred["kp_weights"]
        changed = True
    if inferred["tag_confidence"] and inferred["tag_confidence"] != (resource.tag_confidence or 0):
        resource.tag_confidence = inferred["tag_confidence"]
        changed = True

    graph_tags = [x for x in [resource.course_name, *_as_list(resource.knowledge_points)] if x]
    tags = list(dict.fromkeys(_as_list(resource.tags) + graph_tags))
    if tags != _as_list(resource.tags):
        resource.tags = tags
        changed = True
    return changed


def _serialize_resource(resource: LearningResource, include_content: bool = True) -> dict:
    data = {
        "id": resource.id,
        "resource_type": resource.resource_type,
        "title": resource.title,
        "tags": resource.tags,
        "course_name": resource.course_name,
        "knowledge_points": _as_list(resource.knowledge_points),
        "kp_weights": resource.kp_weights or {},
        "tag_confidence": resource.tag_confidence or 0,
        "learning_status": resource.learning_status or "not_started",
        "progress": resource.progress or 0,
        "completed_at": resource.completed_at.isoformat() if resource.completed_at else None,
        "pinned": bool(resource.pinned),
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
    }
    if include_content:
        data["content"] = resource.content
    return data


@router.get("")
def list_resources(
    user_id: str,
    resource_type: str | None = Query(None),
    course_name: str | None = Query(None),
    knowledge_point: str | None = Query(None),
    learning_status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(LearningResource).filter(LearningResource.user_id == user_id)
    if resource_type:
        q = q.filter(LearningResource.resource_type == resource_type)
    if course_name:
        q = q.filter(LearningResource.course_name == course_name)
    if learning_status:
        q = q.filter(LearningResource.learning_status == learning_status)
    ordered = q.order_by(LearningResource.pinned.desc(), LearningResource.created_at.desc())
    if knowledge_point:
        filtered = [r for r in ordered.all() if knowledge_point in _as_list(r.knowledge_points)]
        total = len(filtered)
        resources = filtered[offset:offset + limit]
    else:
        total = q.count()
        resources = ordered.offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [_serialize_resource(r) for r in resources],
    }


@router.get("/recommend")
def recommend_resources(
    user_id: str,
    top_k: int = Query(10, le=30),
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not profile:
        return {"items": []}

    query_parts = []
    if profile.weak_points:
        query_parts.extend(profile.weak_points[:3])
    if profile.learning_goal:
        query_parts.append(profile.learning_goal)
    if profile.major:
        query_parts.append(profile.major)
    query = " ".join(query_parts) or "学习资源"

    rag_result = search_rag(query, user_id, top_k=top_k * 2)
    def _parse_rag_id(s: str) -> int | None:
        try:
            return int(s)
        except ValueError:
            # 格式如 "res_27_chunk_0"，取第一个数字段
            import re
            m = re.search(r'\d+', s)
            return int(m.group()) if m else None

    candidate_ids = [x for x in (_parse_rag_id(i) for i in rag_result.get("ids", []) if i) if x is not None]
    distances = rag_result.get("distances", [])

    if not candidate_ids:
        items = db.query(LearningResource).filter(
            LearningResource.user_id == user_id
        ).order_by(LearningResource.created_at.desc()).limit(top_k).all()
    else:
        id_to_dist = {candidate_ids[i]: distances[i] for i in range(len(candidate_ids))}
        items_map = {
            r.id: r for r in db.query(LearningResource).filter(
                LearningResource.user_id == user_id,
                LearningResource.id.in_(candidate_ids),
            ).all()
        }
        seen_types: dict[str, int] = {}
        ordered = sorted(candidate_ids, key=lambda i: id_to_dist.get(i, 1.0))
        diverse, rest = [], []
        for rid in ordered:
            r = items_map.get(rid)
            if not r:
                continue
            t = r.resource_type
            if seen_types.get(t, 0) == 0:
                diverse.append(r)
                seen_types[t] = 1
            else:
                rest.append(r)
        items = (diverse + rest)[:top_k]

    return {
        "query": query,
        "items": [_serialize_resource(r, include_content=False) for r in items],
    }


@router.get("/{resource_id}")
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(LearningResource).get(resource_id)
    if not resource:
        return {"found": False}
    return {"found": True, **_serialize_resource(resource)}


@router.post("/auto_tag")
async def auto_tag_resources(
    user_id: str,
    ids: str | None = None,
    overwrite: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(LearningResource).filter(LearningResource.user_id == user_id)
    id_list = [int(x) for x in (ids or "").split(",") if x.strip().isdigit()]
    if id_list:
        q = q.filter(LearningResource.id.in_(id_list))

    updated_ids: list[int] = []
    for resource in q.all():
        if _apply_graph_tags(resource, overwrite=overwrite):
            updated_ids.append(resource.id)
    db.commit()

    await emit("resource.updated", {
        "user_id": user_id,
        "ids": updated_ids,
        "action": "auto_tag",
    })
    return {"ok": True, "updated": len(updated_ids), "ids": updated_ids}


@router.post("/{resource_id}/tag")
async def tag_resource(resource_id: int, req: ResourceTagRequest, db: Session = Depends(get_db)):
    resource = db.query(LearningResource).filter(
        LearningResource.id == resource_id,
        LearningResource.user_id == req.user_id,
    ).first()
    if not resource:
        return {"ok": False, "message": "资源不存在"}

    kp_weights = req.kp_weights or {}
    if req.knowledge_points and not kp_weights:
        weight = round(1 / len(req.knowledge_points), 4)
        kp_weights = {kp: weight for kp in req.knowledge_points}

    resource.course_name = req.course_name
    resource.knowledge_points = req.knowledge_points
    resource.kp_weights = kp_weights
    resource.tag_confidence = 1.0
    resource.tags = list(dict.fromkeys(_as_list(resource.tags) + [x for x in [req.course_name, *req.knowledge_points] if x]))
    db.commit()

    await emit("resource.updated", {
        "user_id": req.user_id,
        "ids": [resource.id],
        "action": "tag",
    })
    return {"ok": True, "resource": _serialize_resource(resource)}


@router.post("/{resource_id}/progress")
async def update_resource_progress(
    resource_id: int,
    user_id: str,
    progress: float = Query(0, ge=0, le=1),
    db: Session = Depends(get_db),
):
    resource = db.query(LearningResource).filter(
        LearningResource.id == resource_id,
        LearningResource.user_id == user_id,
    ).first()
    if not resource:
        return {"ok": False, "message": "资源不存在"}
    resource.progress = progress
    resource.learning_status = "completed" if progress >= 1 else "learning"
    if progress >= 1 and not resource.completed_at:
        resource.completed_at = datetime.utcnow()
    db.commit()
    await emit("resource.updated", {"user_id": user_id, "ids": [resource.id], "action": "progress"})
    return {"ok": True, "resource": _serialize_resource(resource)}


@router.post("/{resource_id}/complete")
async def complete_resource(
    resource_id: int,
    user_id: str,
    score: float | None = Query(None, ge=0, le=1),
    db: Session = Depends(get_db),
):
    resource = db.query(LearningResource).filter(
        LearningResource.id == resource_id,
        LearningResource.user_id == user_id,
    ).first()
    if not resource:
        return {"ok": False, "message": "资源不存在"}

    if not resource.course_name and not _as_list(resource.knowledge_points):
        _apply_graph_tags(resource, overwrite=True)

    resource.learning_status = "completed"
    resource.progress = 1.0
    resource.completed_at = datetime.utcnow()

    kps = _as_list(resource.knowledge_points)
    mastery_score = score
    if mastery_score is None:
        mastery_score = 0.8 if resource.resource_type in ("quiz", "evaluation") else 0.65
    alpha = 0.3 if resource.resource_type in ("quiz", "evaluation") else 0.15
    if kps:
        update_knowledge_base(db, user_id, {kp: mastery_score for kp in kps}, alpha=alpha)
    else:
        db.commit()

    await emit("resource.completed", {
        "user_id": user_id,
        "resource_id": resource.id,
        "course_name": resource.course_name,
        "knowledge_points": kps,
        "score": mastery_score,
    })
    return {"ok": True, "resource": _serialize_resource(resource)}


@router.post("/generate")
async def generate_resource(
    user_id: str,
    topic: str,
    resource_types: str = "article",
    course_name: str = "",
    knowledge_points: str = "",
    question_count: int = 5,
    difficulty: str = "中等",
    question_types: str = "single_choice",
    code_language: str = "python",
    db: Session = Depends(get_db),
):
    types = [t.strip() for t in resource_types.split(",") if t.strip()]
    if not types:
        types = ["article"]
    kp_list = [kp.strip() for kp in knowledge_points.split(",") if kp.strip()]

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()

    async def gen_one(rtype: str):
        state = AgentState(
            user_id=user_id,
            user_message=topic,
            resource_type=rtype,
            question_count=question_count,
            difficulty=difficulty,
            question_types=question_types,
            code_language=code_language,
            course_name=course_name.strip() or None,
            knowledge_points=kp_list,
            profile=profile,
        )
        if rtype == "mindmap":
            await MindMapAgent().process(state)
        elif rtype == "video":
            await VideoAgent().process(state)
        elif rtype == "evaluation":
            await EvaluationAgent().process(state)
        else:
            state["resource_type"] = rtype
            await ContentGenAgent().process(state)

    try:
        await asyncio.gather(*[gen_one(t) for t in types])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await emit("resource.created", {
        "user_id": user_id,
        "topic": topic,
        "types": types,
    })

    return {"ok": True, "types": types}


@router.post("/generate/starter")
async def generate_starter_resources(
    user_id: str,
    max_courses: int = 3,
    db: Session = Depends(get_db),
):
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    weak_courses = (profile.weak_courses if profile else []) or []

    seeds: list[dict] = []
    for c in weak_courses:
        if not isinstance(c, dict):
            continue
        course_name = (c.get("name") or "").strip()
        kp = (c.get("knowledge_points") or "").strip()
        if not course_name:
            continue
        topic = f"{course_name}：{kp}" if kp else course_name
        seeds.append({"course": course_name, "topic": topic})

    if not seeds:
        discipline = (profile.discipline if profile else "") or "通识"
        seeds = [
            {"course": f"{discipline}基础", "topic": f"{discipline}核心概念"},
            {"course": f"{discipline}练习", "topic": f"{discipline}基础题训练"},
        ]

    seeds = seeds[:max(1, min(max_courses, 5))]

    async def gen_seed(seed: dict):
        topic = seed["topic"]
        article = AgentState(user_id=user_id, user_message=topic, resource_type="article", profile=profile)
        quiz = AgentState(user_id=user_id, user_message=topic, resource_type="quiz", profile=profile)
        content_agent = ContentGenAgent()
        await asyncio.gather(content_agent.process(article), content_agent.process(quiz))

    await asyncio.gather(*[gen_seed(s) for s in seeds])

    await emit("resource.created", {
        "user_id": user_id,
        "topic": "starter_pack",
        "types": ["article", "quiz"],
    })

    return {
        "ok": True,
        "courses": [s["course"] for s in seeds],
        "generated": len(seeds) * 2,
    }


@router.post("/batch_pin")
async def batch_pin_resources(
    user_id: str,
    ids: str,
    pinned: int = 1,
    db: Session = Depends(get_db),
):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return {"ok": True, "updated": 0}

    updated = db.query(LearningResource).filter(
        LearningResource.user_id == user_id,
        LearningResource.id.in_(id_list),
    ).update({LearningResource.pinned: 1 if pinned else 0}, synchronize_session=False)
    db.commit()

    await emit("resource.updated", {
        "user_id": user_id,
        "ids": id_list,
        "pinned": 1 if pinned else 0,
    })
    return {"ok": True, "updated": updated}


@router.post("/batch_delete")
async def batch_delete_resources(
    user_id: str,
    ids: str,
    db: Session = Depends(get_db),
):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return {"ok": True, "deleted": 0}

    deleted = db.query(LearningResource).filter(
        LearningResource.user_id == user_id,
        LearningResource.id.in_(id_list),
    ).delete(synchronize_session=False)
    db.commit()

    await emit("resource.deleted", {
        "user_id": user_id,
        "ids": id_list,
    })
    return {"ok": True, "deleted": deleted}


@router.post("/generate/orchestrate")
async def generate_orchestrated(
    user_id: str,
    topic: str,
    db: Session = Depends(get_db),
):
    """多智能体协同编排：一次调用生成 article+mindmap+quiz+video 四种资源"""
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    state = AgentState(user_id=user_id, user_message=topic, profile=profile)
    await OrchestratorAgent().process(state)
    await emit("resource.created", {"user_id": user_id, "topic": topic, "types": ["article", "mindmap", "quiz", "video"]})
    return {"ok": True, "types": ["article", "mindmap", "quiz", "video"]}
