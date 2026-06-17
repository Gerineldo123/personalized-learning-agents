from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
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
import asyncio

router = APIRouter(prefix="/api/resources", tags=["资源"])


@router.get("")
def list_resources(
    user_id: str,
    resource_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(LearningResource).filter(LearningResource.user_id == user_id)
    if resource_type:
        q = q.filter(LearningResource.resource_type == resource_type)
    total = q.count()
    resources = q.order_by(LearningResource.pinned.desc(), LearningResource.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "resource_type": r.resource_type,
                "title": r.title,
                "content": r.content,
                "tags": r.tags,
                "pinned": bool(r.pinned),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in resources
        ],
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
        "items": [
            {
                "id": r.id,
                "resource_type": r.resource_type,
                "title": r.title,
                "tags": r.tags,
                "pinned": bool(r.pinned),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
    }


@router.get("/{resource_id}")
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(LearningResource).get(resource_id)
    if not resource:
        return {"found": False}
    return {
        "found": True,
        "id": resource.id,
        "resource_type": resource.resource_type,
        "title": resource.title,
        "content": resource.content,
        "tags": resource.tags,
        "pinned": bool(resource.pinned),
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
    }


@router.post("/generate")
async def generate_resource(
    user_id: str,
    topic: str,
    resource_types: str = "article",
    question_count: int = 5,
    difficulty: str = "中等",
    question_types: str = "single_choice",
    code_language: str = "python",
    db: Session = Depends(get_db),
):
    types = [t.strip() for t in resource_types.split(",") if t.strip()]
    if not types:
        types = ["article"]

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

    await asyncio.gather(*[gen_one(t) for t in types])

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
