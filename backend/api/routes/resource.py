from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from api.deps import get_db
from models.resource import LearningResource
from models.student import StudentProfile
from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from services.event_service import emit
from services.rag_service import delete_rag_resources
import asyncio
import os

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
):
    types = [t.strip() for t in resource_types.split(",") if t.strip()]
    if not types:
        types = ["article"]

    async def gen_one(rtype: str):
        state = AgentState(
            user_id=user_id,
            user_message=topic,
            resource_type=rtype,
            question_count=question_count,
            difficulty=difficulty,
        )
        if rtype == "mindmap":
            agent = MindMapAgent()
            await agent.process(state)
        else:
            agent = ContentGenAgent()
            state["resource_type"] = rtype
            await agent.process(state)

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
        article = AgentState(user_id=user_id, user_message=topic, resource_type="article")
        quiz = AgentState(user_id=user_id, user_message=topic, resource_type="quiz")
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

    delete_rag_resources(id_list)

    await emit("resource.deleted", {
        "user_id": user_id,
        "ids": id_list,
    })
    return {"ok": True, "deleted": deleted}


@router.get("/{resource_id}/download")
def download_pptx(resource_id: int, user_id: str, db: Session = Depends(get_db)):
    resource = db.query(LearningResource).filter(
        LearningResource.id == resource_id,
        LearningResource.user_id == user_id,
    ).first()
    if not resource:
        raise HTTPException(404, "资源不存在")
    path = ""
    if isinstance(resource.content, dict):
        path = resource.content.get("_pptx_path", "")
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "课件文件不存在，可尝试重新生成")
    filename = f"{resource.title}.pptx"
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
