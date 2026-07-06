from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime
import json
import uuid
from api.deps import get_db
from models.resource import LearningResource
from models.student import StudentProfile
from models.profile_history import ProfileHistory
from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from agents.evaluation_agent import EvaluationAgent
from agents.orchestrator_agent import OrchestratorAgent
from services.event_service import emit
from services.rag_service import search_rag, index_resource
from services.kp_service import infer_resource_tags, update_knowledge_base
from services.safety_service import check_text
from services.curriculum_service import build_relation_context, load_curriculum_by_major
from services.ppt_preview_service import (
    cleanup_ppt_preview,
    get_ppt_preview_status,
    start_ppt_preview,
)
import asyncio

router = APIRouter(prefix="/api/resources", tags=["资源"])


class ResourceTagRequest(BaseModel):
    user_id: str
    course_name: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    kp_weights: dict[str, float] | None = None


class ResourceFeedbackRequest(BaseModel):
    user_id: str
    feedback: str
    note: str | None = None


class ResourceDraftRequest(BaseModel):
    user_id: str
    client_draft_id: str
    resource_type: str
    title: str
    content: dict | list | str
    course_name: str | None = None
    knowledge_points: list[str] = Field(default_factory=list)
    kp_weights: dict[str, float] | None = None


GRAPH_PACKAGE_TYPES: dict[str, list[str]] = {
    "课程总览": ["article", "mindmap", "quiz", "ppt"],
    "阶段复习": ["article", "quiz", "mindmap"],
    "先修补弱": ["article", "quiz"],
    "后继预习": ["article", "video"],
    "知识点补弱": ["article", "quiz", "mindmap"],
    "专项练习": ["quiz"],
    "实操案例": ["code", "article"],
    "PPT课件": ["ppt"],
    "完整资源包": ["article", "mindmap", "quiz", "code", "ppt", "video"],
}

RESOURCE_TYPE_LABELS: dict[str, str] = {
    "article": "文章",
    "quiz": "题库",
    "code": "代码案例",
    "mindmap": "思维导图",
    "ppt": "PPT课件",
    "video": "视频推荐",
    "evaluation": "学习评估",
}


def _generation_job_id(job_id: str | None = None) -> str:
    return job_id.strip() if job_id and job_id.strip() else uuid.uuid4().hex


async def _emit_generation_progress(
    user_id: str,
    job_id: str,
    progress: int,
    message: str,
    status: str = "running",
    **extra,
):
    payload = {
        "user_id": user_id,
        "job_id": job_id,
        "progress": max(0, min(100, int(progress))),
        "message": message,
        "status": status,
        "updated_at": datetime.utcnow().isoformat(),
    }
    payload.update(extra)
    await emit("resource.generation_progress", payload)


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


def _equal_kp_weights(knowledge_points: list[str]) -> dict[str, float]:
    if not knowledge_points:
        return {}
    weight = round(1 / len(knowledge_points), 4)
    return {kp: weight for kp in knowledge_points}


def _package_topic(
    package_type: str,
    course_name: str,
    knowledge_points: list[str],
    relation_context: dict,
) -> str:
    kp_text = "、".join(knowledge_points)
    if package_type == "先修补弱":
        prereqs = "、".join(relation_context.get("prerequisites") or [])
        return f"{course_name}先修补弱：{prereqs or kp_text or '核心基础'}"
    if package_type == "后继预习":
        successors = "、".join(relation_context.get("successors") or [])
        return f"{course_name}后继预习：{successors or kp_text or '进阶内容'}"
    if kp_text:
        return f"{course_name}：{kp_text}（{package_type}）"
    return f"{course_name}（{package_type}）"


def _attach_relation_context(
    db: Session,
    user_id: str,
    since_id: int,
    course_name: str,
    knowledge_points: list[str],
    relation_context: dict,
) -> list[int]:
    resources = db.query(LearningResource).filter(
        LearningResource.user_id == user_id,
        LearningResource.id > since_id,
    ).all()
    updated_ids: list[int] = []
    kp_weights = _equal_kp_weights(knowledge_points)
    for resource in resources:
        resource.course_name = course_name
        resource.knowledge_points = knowledge_points
        resource.kp_weights = kp_weights
        resource.tag_confidence = 1.0 if knowledge_points else max(resource.tag_confidence or 0, 0.7)
        tags = [resource.resource_type, course_name, *knowledge_points]
        resource.tags = list(dict.fromkeys(_as_list(resource.tags) + [tag for tag in tags if tag]))
        content = dict(resource.content) if isinstance(resource.content, dict) else {"text": resource.content}
        content["relation_context"] = relation_context
        resource.content = content
        updated_ids.append(resource.id)
    db.commit()
    return updated_ids


def _ensure_quiz_question_tags(content: dict, knowledge_points: list[str]) -> dict:
    if not isinstance(content, dict):
        return content
    questions = content.get("questions")
    if not isinstance(questions, list):
        return content
    fallback_kps = [kp for kp in knowledge_points if kp]
    fallback_weights = _equal_kp_weights(fallback_kps)
    normalized = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        raw_kps = question.get("knowledge_points")
        if isinstance(raw_kps, str):
            q_kps = [x.strip() for x in raw_kps.split(",") if x.strip()]
        elif isinstance(raw_kps, list):
            q_kps = [str(x).strip() for x in raw_kps if str(x).strip()]
        else:
            q_kps = []
        if fallback_kps:
            allowed = set(fallback_kps)
            q_kps = [kp for kp in q_kps if kp in allowed] or fallback_kps
        q_kps = list(dict.fromkeys(q_kps))
        question["knowledge_points"] = q_kps
        question["kp_weights"] = question.get("kp_weights") or (_equal_kp_weights(q_kps) if q_kps else fallback_weights)
        normalized.append(question)
    content["questions"] = normalized
    return content


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


@router.post("/save_draft")
async def save_draft_resource(req: ResourceDraftRequest, db: Session = Depends(get_db)):
    if req.resource_type not in RESOURCE_TYPE_LABELS:
        raise HTTPException(status_code=400, detail="不支持的资源类型")
    if req.resource_type == "ppt":
        raise HTTPException(status_code=400, detail="PPT 资源必须通过 AiPPT 分步流程生成并保存")
    client_draft_id = req.client_draft_id.strip()
    if not client_draft_id:
        raise HTTPException(status_code=400, detail="缺少草稿 ID")

    existing_items = db.query(LearningResource).filter(
        LearningResource.user_id == req.user_id
    ).order_by(LearningResource.created_at.desc()).limit(200).all()
    for item in existing_items:
        content = item.content if isinstance(item.content, dict) else {}
        if content.get("client_draft_id") == client_draft_id:
            return {"ok": True, "resource": _serialize_resource(item)}

    content = req.content if isinstance(req.content, dict) else {"items": req.content} if isinstance(req.content, list) else {"text": str(req.content)}
    safe_text, _ = await check_text(json.dumps(content, ensure_ascii=False))
    if safe_text != json.dumps(content, ensure_ascii=False):
        content = {"text": safe_text}
    content = dict(content)
    content["client_draft_id"] = client_draft_id

    text = " ".join([
        req.title,
        req.resource_type,
        json.dumps(content, ensure_ascii=False),
    ])
    graph_tags = infer_resource_tags(
        text,
        course_name=req.course_name,
        knowledge_points=req.knowledge_points,
    )
    knowledge_points = graph_tags.get("knowledge_points") or req.knowledge_points or []
    kp_weights = req.kp_weights or graph_tags.get("kp_weights") or _equal_kp_weights(knowledge_points)
    tags = list(dict.fromkeys([
        req.resource_type,
        *[x for x in [graph_tags.get("course_name") or req.course_name] if x],
        *knowledge_points,
    ]))

    resource = LearningResource(
        user_id=req.user_id,
        resource_type=req.resource_type,
        title=req.title or f"{req.resource_type}_resource",
        content=content,
        tags=tags,
        course_name=graph_tags.get("course_name") or req.course_name,
        knowledge_points=knowledge_points,
        kp_weights=kp_weights,
        tag_confidence=graph_tags.get("tag_confidence") or (1.0 if req.course_name or req.knowledge_points else 0.0),
    )
    db.add(resource)
    db.flush()
    db.commit()

    index_resource(resource.id, req.user_id or "", json.dumps(content, ensure_ascii=False)[:4000], req.resource_type)
    await emit("resource.created", {
        "user_id": req.user_id,
        "resource_id": resource.id,
        "resource_type": resource.resource_type,
        "title": resource.title,
        "source": "agent_draft",
    })
    return {"ok": True, "resource": _serialize_resource(resource)}


@router.get("/{resource_id}")
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(LearningResource).get(resource_id)
    if not resource:
        return {"found": False}
    return {"found": True, **_serialize_resource(resource)}


@router.post("/{article_id}/generate_quiz_from_article")
async def generate_quiz_from_article(
    article_id: int,
    user_id: str,
    question_count: int = Query(6, ge=3, le=20),
    difficulty: str = "中等",
    db: Session = Depends(get_db),
):
    article = db.query(LearningResource).filter(
        LearningResource.id == article_id,
        LearningResource.user_id == user_id,
        LearningResource.resource_type == "article",
    ).first()
    if not article:
        raise HTTPException(status_code=404, detail="文章资源不存在")

    course_name = article.course_name or ""
    knowledge_points = _as_list(article.knowledge_points)
    if not course_name or not knowledge_points:
        inferred = infer_resource_tags(_resource_text(article))
        course_name = course_name or inferred.get("course_name") or ""
        knowledge_points = knowledge_points or inferred.get("knowledge_points") or []
    if not course_name or not knowledge_points:
        raise HTTPException(status_code=400, detail="文章缺少课程或知识点标签，无法生成可回写掌握度的测试题")

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    article_text = ""
    content = article.content
    if isinstance(content, dict):
        article_text = str(content.get("text") or content.get("markdown") or json.dumps(content, ensure_ascii=False))
    else:
        article_text = str(content or "")
    topic = (
        f"请基于以下文章内容生成课后测试题，课程：{course_name}，"
        f"知识点范围：{'、'.join(knowledge_points)}。\n\n"
        f"文章标题：{article.title}\n文章内容：\n{article_text[:5000]}"
    )
    state = AgentState(
        user_id=user_id,
        user_message=topic,
        resource_type="quiz",
        profile=profile,
        course_name=course_name,
        knowledge_points=knowledge_points,
        question_count=question_count,
        difficulty=difficulty,
        question_types="single_choice,fill_blank",
    )
    await ContentGenAgent().process(state)
    resource_id = state.get("resource_db_id")
    quiz = db.query(LearningResource).filter(
        LearningResource.id == resource_id,
        LearningResource.user_id == user_id,
    ).first()
    if not quiz:
        raise HTTPException(status_code=502, detail="题库生成失败")

    quiz.course_name = course_name
    quiz.knowledge_points = knowledge_points
    quiz.kp_weights = quiz.kp_weights or _equal_kp_weights(knowledge_points)
    quiz.tag_confidence = 1.0
    quiz.tags = list(dict.fromkeys(_as_list(quiz.tags) + ["quiz", course_name, *knowledge_points]))
    quiz.content = _ensure_quiz_question_tags(dict(quiz.content or {}), knowledge_points)
    db.commit()
    db.refresh(quiz)
    index_resource(quiz.id, user_id, json.dumps(quiz.content or {}, ensure_ascii=False)[:4000], "quiz")
    await emit("resource.created", {
        "user_id": user_id,
        "resource_id": quiz.id,
        "resource_type": "quiz",
        "source": "article_quiz",
        "article_id": article.id,
        "course_name": course_name,
        "knowledge_points": knowledge_points,
    })
    return {"ok": True, "resource": _serialize_resource(quiz)}


@router.get("/{resource_id}/ppt_preview")
def get_resource_ppt_preview(resource_id: int, user_id: str | None = Query(None)):
    result = get_ppt_preview_status(resource_id, user_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="资源不存在")
    return result


@router.post("/{resource_id}/ppt_preview")
def create_resource_ppt_preview(
    resource_id: int,
    user_id: str | None = Query(None),
    force: bool = Query(True),
):
    result = start_ppt_preview(resource_id, user_id, force=force)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="资源不存在")
    if not result.get("ok", True):
        raise HTTPException(status_code=400, detail=result.get("error") or "无法生成 PPT 预览")
    return result


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


@router.post("/{resource_id}/feedback")
async def feedback_resource(
    resource_id: int,
    req: ResourceFeedbackRequest,
    db: Session = Depends(get_db),
):
    allowed = {"too_hard", "too_easy", "helpful", "irrelevant"}
    if req.feedback not in allowed:
        raise HTTPException(status_code=400, detail="不支持的资源反馈类型")

    resource = db.query(LearningResource).filter(
        LearningResource.id == resource_id,
        LearningResource.user_id == req.user_id,
    ).first()
    if not resource:
        return {"ok": False, "message": "资源不存在"}

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == req.user_id).first()
    if not profile:
        profile = StudentProfile(user_id=req.user_id)
        db.add(profile)
        db.flush()

    feedback_profile = dict(profile.resource_feedback_profile or {})
    counts = dict(feedback_profile.get("counts") or {})
    counts[req.feedback] = counts.get(req.feedback, 0) + 1
    by_type = dict(feedback_profile.get("by_resource_type") or {})
    type_counts = dict(by_type.get(resource.resource_type) or {})
    type_counts[req.feedback] = type_counts.get(req.feedback, 0) + 1
    by_type[resource.resource_type] = type_counts
    feedback_profile.update({
        "counts": counts,
        "by_resource_type": by_type,
        "last_feedback": {
            "resource_id": resource.id,
            "resource_type": resource.resource_type,
            "course_name": resource.course_name,
            "knowledge_points": _as_list(resource.knowledge_points),
            "feedback": req.feedback,
            "note": req.note or "",
            "created_at": datetime.utcnow().isoformat(),
        },
    })
    profile.resource_feedback_profile = feedback_profile

    evidence = dict(profile.profile_evidence or {})
    evidence["resource_feedback_profile"] = "学习资源反馈"
    profile.profile_evidence = evidence

    db.add(ProfileHistory(
        user_id=req.user_id,
        trigger="resource_feedback",
        snapshot={
            "resource_feedback_profile": feedback_profile,
            "preferred_format": profile.preferred_format or [],
        },
        delta={
            "feedback": req.feedback,
            "resource_id": resource.id,
            "resource_type": resource.resource_type,
        },
    ))
    db.commit()

    await emit("resource.feedback", {
        "user_id": req.user_id,
        "resource_id": resource.id,
        "feedback": req.feedback,
    })
    await emit("profile.updated", {"user_id": req.user_id})
    return {"ok": True, "resource_feedback_profile": feedback_profile}


@router.post("/generate/graph_package")
async def generate_graph_package(
    user_id: str,
    course_name: str,
    knowledge_points: str = "",
    package_type: str = "知识点补弱",
    job_id: str = "",
    db: Session = Depends(get_db),
):
    if package_type not in GRAPH_PACKAGE_TYPES:
        raise HTTPException(status_code=400, detail="不支持的资源包类型")
    if not course_name.strip():
        raise HTTPException(status_code=400, detail="请选择课程节点")

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    kp_list = [kp.strip() for kp in knowledge_points.split(",") if kp.strip()]
    curriculum = load_curriculum_by_major(profile.major if profile else "")
    relation_context = build_relation_context(curriculum, course_name.strip())
    topic = _package_topic(package_type, course_name.strip(), kp_list, relation_context)
    before_id = db.query(LearningResource.id).filter(
        LearningResource.user_id == user_id
    ).order_by(LearningResource.id.desc()).limit(1).scalar() or 0
    types = GRAPH_PACKAGE_TYPES[package_type]
    job_id = _generation_job_id(job_id)
    await _emit_generation_progress(
        user_id,
        job_id,
        5,
        f"已提交{package_type}生成任务",
        package_type=package_type,
        course_name=course_name.strip(),
        knowledge_points=kp_list,
        types=types,
        current=0,
        total=len(types),
    )

    state = AgentState(
        user_id=user_id,
        user_message=topic,
        profile=profile,
        course_name=course_name.strip(),
        knowledge_points=kp_list,
        requested_resource_types=types,
    )
    try:
        await _emit_generation_progress(
            user_id,
            job_id,
            18,
            "LangGraph 多智能体正在规划并生成资源包",
            package_type=package_type,
            current=0,
            total=len(types),
        )
        await OrchestratorAgent().process(state)
        failures = state.get("orchestration_failures") or []
        await _emit_generation_progress(
            user_id,
            job_id,
            88,
            "资源内容已生成，正在写入图谱标签",
            package_type=package_type,
            current=len(types),
            total=len(types),
            failures=failures,
        )
    except Exception as exc:
        await _emit_generation_progress(
            user_id,
            job_id,
            100,
            f"图谱资源包生成失败：{exc}",
            status="failed",
            package_type=package_type,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await _emit_generation_progress(
        user_id,
        job_id,
        94,
        "正在同步课程与知识点标签",
        package_type=package_type,
        current=len(types),
        total=len(types),
    )
    updated_ids = _attach_relation_context(
        db,
        user_id,
        before_id,
        course_name.strip(),
        kp_list,
        relation_context,
    )
    await emit("resource.created", {
        "user_id": user_id,
        "topic": topic,
        "types": types,
        "package_type": package_type,
        "course_name": course_name,
        "knowledge_points": kp_list,
        "job_id": job_id,
    })
    await _emit_generation_progress(
        user_id,
        job_id,
        100,
        "图谱资源包生成完成",
        status="completed",
        package_type=package_type,
        course_name=course_name,
        knowledge_points=kp_list,
        current=len(types),
        total=len(types),
    )
    generated_resources = state.get("generated_resources") or []
    ppt_sessions = [item.get("ppt_session") for item in generated_resources if item.get("ppt_session")]
    return {
        "ok": True,
        "job_id": job_id,
        "package_type": package_type,
        "course_name": course_name,
        "knowledge_points": kp_list,
        "types": types,
        "generated": len(updated_ids),
        "ids": updated_ids,
        "resources": generated_resources,
        "ppt_sessions": ppt_sessions,
        "failures": failures,
    }


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
    job_id: str = "",
    db: Session = Depends(get_db),
):
    types = [t.strip() for t in resource_types.split(",") if t.strip()]
    if not types:
        types = ["article"]
    kp_list = [kp.strip() for kp in knowledge_points.split(",") if kp.strip()]

    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    job_id = _generation_job_id(job_id)
    await _emit_generation_progress(
        user_id,
        job_id,
        5,
        "已提交学习资源生成任务",
        topic=topic,
        types=types,
        current=0,
        total=len(types),
    )

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
        return state

    completed_count = 0
    progress_lock = asyncio.Lock()

    async def gen_one_with_progress(rtype: str):
        nonlocal completed_count
        label = RESOURCE_TYPE_LABELS.get(rtype, rtype)
        await _emit_generation_progress(
            user_id,
            job_id,
            8,
            f"正在生成{label}",
            topic=topic,
            resource_type=rtype,
            current=completed_count,
            total=len(types),
        )
        state = await gen_one(rtype)
        async with progress_lock:
            completed_count += 1
            progress = 10 + round(completed_count / max(1, len(types)) * 82)
            await _emit_generation_progress(
                user_id,
                job_id,
                progress,
                f"{label}生成完成",
                topic=topic,
                resource_type=rtype,
                current=completed_count,
                total=len(types),
            )
        return state

    try:
        generated_states = await asyncio.gather(*[gen_one_with_progress(t) for t in types])
    except Exception as exc:
        await _emit_generation_progress(
            user_id,
            job_id,
            100,
            f"资源生成失败：{exc}",
            status="failed",
            topic=topic,
            types=types,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await emit("resource.created", {
        "user_id": user_id,
        "topic": topic,
        "types": types,
        "job_id": job_id,
    })
    await _emit_generation_progress(
        user_id,
        job_id,
        100,
        "学习资源生成完成",
        status="completed",
        topic=topic,
        types=types,
        current=len(types),
        total=len(types),
    )

    ppt_sessions = [state.get("ppt_session") for state in generated_states if state.get("ppt_session")]
    generated_ids = [state.get("resource_db_id") for state in generated_states if state.get("resource_db_id")]
    return {
        "ok": True,
        "job_id": job_id,
        "types": types,
        "ids": generated_ids,
        "ppt_sessions": ppt_sessions,
    }


@router.post("/generate/starter")
async def generate_starter_resources(
    user_id: str,
    max_courses: int = 3,
    job_id: str = "",
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
    job_id = _generation_job_id(job_id)
    await _emit_generation_progress(
        user_id,
        job_id,
        5,
        "已提交入门资源包生成任务",
        topic="starter_pack",
        current=0,
        total=len(seeds) * 2,
    )

    async def gen_seed(seed: dict):
        topic = seed["topic"]
        article = AgentState(user_id=user_id, user_message=topic, resource_type="article", profile=profile)
        quiz = AgentState(user_id=user_id, user_message=topic, resource_type="quiz", profile=profile)
        content_agent = ContentGenAgent()
        await asyncio.gather(content_agent.process(article), content_agent.process(quiz))

    completed_count = 0
    progress_lock = asyncio.Lock()

    async def gen_seed_with_progress(seed: dict):
        nonlocal completed_count
        await _emit_generation_progress(
            user_id,
            job_id,
            8,
            f"正在为 {seed['course']} 生成文章和题库",
            topic="starter_pack",
            course_name=seed["course"],
            current=completed_count,
            total=len(seeds) * 2,
        )
        await gen_seed(seed)
        async with progress_lock:
            completed_count += 2
            progress = 10 + round(completed_count / max(1, len(seeds) * 2) * 82)
            await _emit_generation_progress(
                user_id,
                job_id,
                progress,
                f"{seed['course']} 入门资源生成完成",
                topic="starter_pack",
                course_name=seed["course"],
                current=completed_count,
                total=len(seeds) * 2,
            )

    try:
        await asyncio.gather(*[gen_seed_with_progress(s) for s in seeds])
    except Exception as exc:
        await _emit_generation_progress(
            user_id,
            job_id,
            100,
            f"入门资源包生成失败：{exc}",
            status="failed",
            topic="starter_pack",
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await emit("resource.created", {
        "user_id": user_id,
        "topic": "starter_pack",
        "types": ["article", "quiz"],
        "job_id": job_id,
    })
    await _emit_generation_progress(
        user_id,
        job_id,
        100,
        "入门资源包生成完成",
        status="completed",
        topic="starter_pack",
        current=len(seeds) * 2,
        total=len(seeds) * 2,
    )

    return {
        "ok": True,
        "job_id": job_id,
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

    ppt_ids = [
        item.id for item in db.query(LearningResource.id).filter(
            LearningResource.user_id == user_id,
            LearningResource.id.in_(id_list),
            LearningResource.resource_type == "ppt",
        ).all()
    ]

    deleted = db.query(LearningResource).filter(
        LearningResource.user_id == user_id,
        LearningResource.id.in_(id_list),
    ).delete(synchronize_session=False)
    db.commit()

    for resource_id in ppt_ids:
        cleanup_ppt_preview(resource_id)

    await emit("resource.deleted", {
        "user_id": user_id,
        "ids": id_list,
    })
    return {"ok": True, "deleted": deleted}


@router.post("/generate/orchestrate")
async def generate_orchestrated(
    user_id: str,
    topic: str,
    course_name: str = "",
    knowledge_points: str = "",
    job_id: str = "",
    db: Session = Depends(get_db),
):
    """多智能体协同编排：一次调用生成 article+mindmap+quiz+code+ppt+video 六种资源"""
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    kp_list = [kp.strip() for kp in knowledge_points.split(",") if kp.strip()]
    job_id = _generation_job_id(job_id)
    types = ["article", "mindmap", "quiz", "code", "ppt", "video"]
    await _emit_generation_progress(
        user_id,
        job_id,
        5,
        "已提交多智能体协同生成任务",
        topic=topic,
        types=types,
        current=0,
        total=len(types),
    )
    state = AgentState(
        user_id=user_id,
        user_message=topic,
        profile=profile,
        course_name=course_name.strip() or None,
        knowledge_points=kp_list,
    )
    try:
        await _emit_generation_progress(
            user_id,
            job_id,
            18,
            "多智能体正在并行规划文章、导图、题库、代码、PPT和视频",
            topic=topic,
            types=types,
            current=0,
            total=len(types),
        )
        await OrchestratorAgent().process(state)
        await _emit_generation_progress(
            user_id,
            job_id,
            92,
            "多智能体生成完成，正在刷新资源列表",
            topic=topic,
            types=types,
            current=len(types),
            total=len(types),
        )
    except Exception as exc:
        await _emit_generation_progress(
            user_id,
            job_id,
            100,
            f"多智能体协同生成失败：{exc}",
            status="failed",
            topic=topic,
            types=types,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await emit("resource.created", {"user_id": user_id, "topic": topic, "types": types, "job_id": job_id})
    await _emit_generation_progress(
        user_id,
        job_id,
        100,
        "多智能体协同生成完成",
        status="completed",
        topic=topic,
        types=types,
        current=len(types),
        total=len(types),
    )
    generated_resources = state.get("generated_resources") or []
    ppt_sessions = [item.get("ppt_session") for item in generated_resources if item.get("ppt_session")]
    return {
        "ok": True,
        "job_id": job_id,
        "types": types,
        "resources": generated_resources,
        "ppt_sessions": ppt_sessions,
        "failures": state.get("orchestration_failures") or [],
        "course_name": state.get("course_name"),
        "knowledge_points": state.get("knowledge_points") or [],
    }
