from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ppt", tags=["PPT课件"])


class CreateSessionRequest(BaseModel):
    user_id: str
    topic: str
    course_name: str = ""
    knowledge_points: list[str] = Field(default_factory=list)


class CompleteSessionRequest(BaseModel):
    user_id: str
    ppt_id: str
    subject: str = ""
    cover_url: str | None = None
    template_id: str | None = None


class OneClickRequest(BaseModel):
    user_id: str
    topic: str
    course_name: str = ""
    knowledge_points: list[str] = Field(default_factory=list)


def _clean_items(items: list[str]) -> list[str]:
    return [item.strip() for item in items if str(item or "").strip()]


def _validate_generate_input(
    user_id: str,
    topic: str,
    course_name: str,
    knowledge_points: list[str],
) -> tuple[str, str, list[str]]:
    clean_user_id = user_id.strip()
    clean_topic = topic.strip()
    clean_course_name = course_name.strip()
    clean_knowledge_points = _clean_items(knowledge_points)

    if not clean_user_id:
        raise HTTPException(status_code=400, detail="用户不能为空")
    if not clean_topic:
        raise HTTPException(status_code=400, detail="PPT 主题不能为空")
    if not clean_course_name:
        raise HTTPException(status_code=400, detail="生成 PPT 前必须绑定课程节点")
    if not clean_knowledge_points:
        raise HTTPException(status_code=400, detail="生成 PPT 前必须绑定至少一个知识点节点")
    return clean_user_id, clean_topic, clean_course_name, clean_knowledge_points


@router.post("/sessions")
async def create_session(req: CreateSessionRequest):
    from services.ppt_model_service import create_ppt_session, is_docmee_aippt_configured

    if not is_docmee_aippt_configured():
        raise HTTPException(status_code=400, detail="PPT API 未配置，请先在 API 配置中设置 Docmee AiPPT 密钥")

    user_id, topic, course_name, knowledge_points = _validate_generate_input(
        req.user_id,
        req.topic,
        req.course_name,
        req.knowledge_points,
    )

    try:
        return await create_ppt_session(
            user_id=user_id,
            topic=topic,
            course_name=course_name,
            knowledge_points=knowledge_points,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/sessions/{session_id}/complete")
async def complete_session(session_id: str, req: CompleteSessionRequest):
    from services.ppt_model_service import complete_ppt_session

    if not req.user_id.strip():
        raise HTTPException(status_code=400, detail="用户不能为空")
    if not req.ppt_id.strip():
        raise HTTPException(status_code=400, detail="PPT ID 不能为空")

    try:
        return await complete_ppt_session(
            session_id=session_id,
            user_id=req.user_id.strip(),
            ppt_id=req.ppt_id.strip(),
            subject=req.subject.strip(),
            cover_url=req.cover_url,
            template_id=req.template_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/sessions/{session_id}/status")
def get_session_status(session_id: str, user_id: str):
    from services.ppt_model_service import get_ppt_session_status

    result = get_ppt_session_status(session_id, user_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="PPT 会话不存在")
    return result


@router.post("/one-click")
async def one_click_generate(req: OneClickRequest):
    from services.ppt_model_service import create_ppt_session, is_docmee_aippt_configured

    if not is_docmee_aippt_configured():
        raise HTTPException(status_code=400, detail="PPT API 未配置，请先在 API 配置中设置 Docmee AiPPT 密钥")

    user_id, topic, course_name, knowledge_points = _validate_generate_input(
        req.user_id,
        req.topic,
        req.course_name,
        req.knowledge_points,
    )

    try:
        session = await create_ppt_session(
            user_id=user_id,
            topic=topic,
            course_name=course_name,
            knowledge_points=knowledge_points,
        )
        return {
            "ok": True,
            "status": "pending_step_by_step",
            "message": "PPT 已改为强制 AiPPT 分步生成，请在工作台确认大纲和模板后保存。",
            "ppt_session": session,
            "session_id": session.get("session_id"),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
