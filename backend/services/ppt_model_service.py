import asyncio
import io
import json
import os
import re
import uuid
import zipfile

import httpx

from core.llm_client import ppt_completion
from services.config_service import get_ppt_config, is_configured
from services.safety_service import hallu_rules

PPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "ppt")
DOCMEE_DEFAULT_BASE_URL = "https://docmee.cn"
DOCMEE_MODEL_NAMES = {"aippt", "docmee", "docmee-aippt", "veasion-aippt"}

PPT_MODEL_PROMPT = """You are a dedicated university course PPT generator.

Student profile: {profile}
Topic: {topic}
Target slides: {slide_count}

Return valid JSON only:
{{
  "title": "courseware title",
  "slides": [
    {{
      "title": "slide title",
      "content": ["point 1", "point 2", "point 3"],
      "notes": "teaching note"
    }}
  ]
}}

Rules:
- Generate content for university-level learning.
- Use concise slide titles and 3-5 short bullets per slide.
- Avoid marketing copy.
- {hallu}
"""


def _ppt_cfg():
    return get_ppt_config()


def is_docmee_aippt_configured() -> bool:
    cfg = _ppt_cfg()
    model = (cfg.model or "docmee-aippt").lower()
    base_url = (cfg.base_url or DOCMEE_DEFAULT_BASE_URL).lower()
    return bool(cfg.api_key and ("docmee" in base_url or model in DOCMEE_MODEL_NAMES))


def is_ppt_model_configured() -> bool:
    return is_docmee_aippt_configured() or is_configured("ppt")


def _compact_text(text: str, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[:max_chars - 3].rstrip() + "..."


def _compact_bytes(text: str, max_bytes: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    if max_bytes <= 3:
        return encoded[:max_bytes].decode("utf-8", errors="ignore")
    clipped = encoded[:max_bytes - 3].decode("utf-8", errors="ignore").rstrip()
    return clipped + "..."


def _docmee_subject(topic: str) -> str:
    return _compact_bytes(topic, 40) or "AI Courseware"


def _docmee_prompt(topic: str, profile: str, slide_count: int) -> str:
    topic_hint = _compact_bytes(topic, 48)
    prompt = f"Create {slide_count} Chinese course PPT slides. Topic: {topic_hint}"
    return _compact_bytes(prompt, 110)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json(raw: str) -> dict:
    text = _strip_json_fence(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_ppt_data(data: dict, fallback_title: str) -> dict:
    if not isinstance(data, dict):
        data = {}

    title = str(data.get("title") or fallback_title or "PPT Courseware").strip()
    slides = data.get("slides") or []
    normalized_slides = []

    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        slide_title = str(slide.get("title") or f"Slide {index + 1}").strip()
        content = slide.get("content") or []
        if isinstance(content, str):
            content = [content]
        content = [str(item).strip() for item in content if str(item).strip()]
        if not content:
            continue
        normalized_slides.append({
            "title": slide_title,
            "content": content[:6],
            "notes": str(slide.get("notes") or "").strip(),
        })

    return {
        "title": title,
        "slides": normalized_slides[:12],
    }


def _docmee_base_url() -> str:
    return (_ppt_cfg().base_url or DOCMEE_DEFAULT_BASE_URL).rstrip("/")


async def _docmee_post_json(client: httpx.AsyncClient, path: str, headers: dict, body: dict) -> dict:
    resp = await client.post(_docmee_base_url() + path, headers=headers, json=body)
    if resp.status_code != 200:
        raise RuntimeError(f"Docmee API HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("message") or "Docmee API request failed")
    return data.get("data") or {}


async def _docmee_create_token(client: httpx.AsyncClient, user_id: str) -> str:
    cfg = _ppt_cfg()
    data = await _docmee_post_json(
        client,
        "/api/user/createApiToken",
        {"Api-Key": cfg.api_key},
        {"uid": user_id or "default", "limit": None},
    )
    token = data.get("token")
    if not token:
        raise RuntimeError("Docmee API did not return token")
    return token


async def _docmee_random_template(client: httpx.AsyncClient, token: str) -> str:
    data = await _docmee_post_json(
        client,
        "/api/ppt/randomTemplates",
        {"token": token},
        {"size": 1, "filters": {"type": 1}},
    )
    templates = data if isinstance(data, list) else data.get("list") or data.get("records") or []
    if not templates:
        raise RuntimeError("Docmee API did not return templates")
    template_id = templates[0].get("id")
    if not template_id:
        raise RuntimeError("Docmee template id is empty")
    return template_id


async def _docmee_direct_generate(
    client: httpx.AsyncClient,
    token: str,
    template_id: str,
    topic: str,
    profile: str,
    slide_count: int,
) -> dict:
    data = await _docmee_post_json(
        client,
        "/api/ppt/directGeneratePptx",
        {"token": token},
        {
            "stream": False,
            "templateId": template_id,
            "subject": _docmee_subject(topic),
            "prompt": _docmee_prompt(topic, profile, slide_count),
            "dataUrl": None,
            "pptxProperty": False,
        },
    )
    ppt_info = data.get("pptInfo") or data
    if not ppt_info.get("id"):
        raise RuntimeError("Docmee API did not return ppt id")
    return ppt_info


async def _docmee_download_info(client: httpx.AsyncClient, token: str, ppt_id: str) -> dict:
    for _ in range(30):
        data = await _docmee_post_json(
            client,
            "/api/ppt/downloadPptx",
            {"token": token},
            {"id": ppt_id},
        )
        file_url = data.get("fileUrl") or data.get("downloadUrl") or data.get("url")
        if file_url:
            data["fileUrl"] = file_url
            return data
        await asyncio.sleep(1)
    raise RuntimeError("Docmee PPT file is not ready")


async def _download_file(client: httpx.AsyncClient, file_url: str) -> str:
    os.makedirs(PPT_DIR, exist_ok=True)
    filename = f"docmee_{uuid.uuid4().hex[:10]}.pptx"
    path = os.path.join(PPT_DIR, filename)
    resp = await client.get(file_url)
    if resp.status_code != 200:
        raise RuntimeError(f"Download PPT failed, HTTP {resp.status_code}")
    if not zipfile.is_zipfile(io.BytesIO(resp.content)):
        raise RuntimeError("Downloaded file is not a valid PPTX")
    with open(path, "wb") as f:
        f.write(resp.content)
    return filename


def _ppt_resource_response(resource: "LearningResource", pptx_url: str, cover_url: str | None = None) -> dict:
    return {
        "id": resource.id,
        "title": resource.title,
        "resource_type": resource.resource_type,
        "course_name": resource.course_name,
        "knowledge_points": resource.knowledge_points,
        "pptx_url": pptx_url,
        "cover_url": cover_url,
    }


async def _generate_docmee_aippt(topic: str, profile: str, user_id: str, slide_count: int) -> dict:
    timeout = httpx.Timeout(180.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        token = await _docmee_create_token(client, user_id)
        template_id = await _docmee_random_template(client, token)
        ppt_info = await _docmee_direct_generate(client, token, template_id, topic, profile, slide_count)
        download_info = await _docmee_download_info(client, token, ppt_info["id"])
        pptx_filename = await _download_file(client, download_info["fileUrl"])

    title = ppt_info.get("subject") or _docmee_subject(topic)
    return {
        "title": title,
        "slides": [
            {
                "title": "AiPPT课件已生成",
                "content": [
                    "完整PPT文件已由文多多 AiPPT 生成",
                    f"主题：{title}",
                    "当前页面只是下载预览，请点击右上角下载查看完整课件",
                ],
                "notes": "Docmee/AiPPT 返回的是 PPTX 文件；系统已保存到本地静态目录。",
            }
        ],
        "pptx_file": pptx_filename,
        "pptx_url": f"/static/ppt/{pptx_filename}",
        "source": "docmee_aippt",
        "template_id": template_id,
        "remote_ppt_id": ppt_info.get("id"),
        "cover_url": ppt_info.get("coverUrl"),
    }


async def generate_ppt_json(
    topic: str,
    profile: str,
    slide_count: int = 7,
    user_id: str = "default",
) -> dict:
    if not is_ppt_model_configured():
        raise RuntimeError("PPT model API is not configured")

    slide_count = max(4, min(int(slide_count or 7), 12))
    if is_docmee_aippt_configured():
        return await _generate_docmee_aippt(topic, profile, user_id, slide_count)

    resp = await ppt_completion([
        {
            "role": "user",
            "content": PPT_MODEL_PROMPT.format(
                profile=profile,
                topic=topic,
                slide_count=slide_count,
                hallu=hallu_rules(),
            ),
        },
    ], temperature=0.45)

    raw = resp.choices[0].message.content.strip()
    return _normalize_ppt_data(_extract_json(raw), topic)


async def create_ppt_session(
    user_id: str,
    topic: str,
    course_name: str,
    knowledge_points: list[str],
) -> dict:
    if not is_docmee_aippt_configured():
        raise RuntimeError("PPT API 未配置，请先在 API 配置中设置 Docmee AiPPT 密钥")

    session_id = uuid.uuid4().hex
    timeout = httpx.Timeout(60.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        token = await _docmee_create_token(client, user_id)

    from core.database import SessionLocal
    from models.ppt_session import PptSession
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        session = PptSession(
            session_id=session_id,
            user_id=user_id,
            topic=topic,
            course_name=course_name,
            knowledge_points=knowledge_points,
            status="created",
            docmee_token=token,
            expires_at=datetime.utcnow() + timedelta(hours=2),
        )
        db.add(session)
        db.commit()
    finally:
        db.close()

    base_url = _docmee_base_url()
    return {
        "session_id": session_id,
        "token": token,
        "expires_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        "embed_config": {
            "base_url": base_url,
            "token": token,
            "sdk_url": os.getenv(
                "DOCMEE_AIPPT_SDK_URL",
                "https://oss.docmee.cn/ajax/libs/docmee/sdk-ui/dist/index.global.js",
            ),
            "domain": os.getenv("DOCMEE_AIPPT_DOMAIN", base_url),
        },
    }


async def complete_ppt_session(
    session_id: str,
    user_id: str,
    ppt_id: str,
    subject: str,
    cover_url: str | None = None,
    template_id: str | None = None,
) -> dict:
    from core.database import SessionLocal
    from models.ppt_session import PptSession
    from models.resource import LearningResource
    from datetime import datetime
    import json

    db = SessionLocal()
    try:
        session = db.query(PptSession).filter(
            PptSession.session_id == session_id,
            PptSession.user_id == user_id,
        ).first()
        if not session:
            raise RuntimeError("PPT 会话不存在")
        if session.status == "completed":
            resource = None
            if session.resource_id:
                resource = db.query(LearningResource).filter(
                    LearningResource.id == session.resource_id,
                    LearningResource.user_id == user_id,
                ).first()
            if resource:
                content = resource.content or {}
                return {
                    "ok": True,
                    "status": "already_completed",
                    "resource": _ppt_resource_response(
                        resource,
                        content.get("pptx_url", ""),
                        content.get("cover_url"),
                    ),
                }
            return {"ok": True, "resource_id": session.resource_id, "status": "already_completed"}
        if session.status == "generating":
            raise RuntimeError("PPT 正在保存中，请稍后查看状态")
        if session.expires_at and session.expires_at < datetime.utcnow():
            raise RuntimeError("PPT 会话已过期，请重新打开 AiPPT 生成")

        try:
            session.status = "generating"
            session.ppt_id = ppt_id
            session.cover_url = cover_url
            session.template_id = template_id
            session.error_message = None
            session.updated_at = datetime.utcnow()
            db.commit()

            token = session.docmee_token
            if not token:
                raise RuntimeError("Session token missing, cannot download")
            timeout = httpx.Timeout(180.0, connect=20.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                download_info = await _docmee_download_info(client, token, ppt_id)
                session.file_url = download_info["fileUrl"]
                pptx_filename = await _download_file(client, download_info["fileUrl"])

            title = subject or session.topic or "PPT课件"

            ppt_data = {
                "title": title,
                "slides": [
                    {
                        "title": "AiPPT课件已生成",
                        "content": [
                            "完整PPT文件已由文多多 AiPPT 生成",
                            f"主题：{title}",
                            "请下载查看完整课件",
                        ],
                        "notes": "Docmee/AiPPT 返回的是 PPTX 文件；系统已保存到本地静态目录。",
                    }
                ],
                "pptx_file": pptx_filename,
                "pptx_url": f"/static/ppt/{pptx_filename}",
                "source": "docmee_ui",
                "template_id": template_id or session.template_id,
                "remote_ppt_id": ppt_id,
                "cover_url": cover_url or session.cover_url,
            }

            from services.kp_service import infer_resource_tags
            text_for_tags = " ".join([
                title,
                session.course_name or "",
                " ".join(session.knowledge_points or []),
                json.dumps(ppt_data, ensure_ascii=False),
            ])
            graph_tags = infer_resource_tags(
                text_for_tags,
                course_name=session.course_name,
                knowledge_points=session.knowledge_points or [],
            )
            tags = list(dict.fromkeys(
                ["ppt"]
                + [x for x in [graph_tags.get("course_name")] if x]
                + list(graph_tags.get("knowledge_points") or [])
            ))

            resource = LearningResource(
                user_id=user_id,
                resource_type="ppt",
                title=title,
                content=ppt_data,
                tags=tags,
                course_name=graph_tags.get("course_name"),
                knowledge_points=graph_tags.get("knowledge_points") or [],
                kp_weights=graph_tags.get("kp_weights") or {},
                tag_confidence=graph_tags.get("tag_confidence") or 0,
            )
            db.add(resource)
            db.flush()

            session.status = "completed"
            session.pptx_file = pptx_filename
            session.resource_id = resource.id
            session.updated_at = datetime.utcnow()
            db.commit()

            try:
                from services.ppt_preview_service import schedule_ppt_preview
                schedule_ppt_preview(resource.id)
            except Exception:
                pass

            try:
                from services.event_service import emit
                import asyncio
                asyncio.ensure_future(emit("resource.created", {
                    "user_id": user_id,
                    "resource_id": resource.id,
                    "course_name": resource.course_name,
                    "knowledge_points": resource.knowledge_points,
                }))
            except Exception:
                pass

            return {
                "ok": True,
                "resource": _ppt_resource_response(
                    resource,
                    ppt_data["pptx_url"],
                    ppt_data.get("cover_url"),
                ),
            }
        except Exception as exc:
            db.rollback()
            session.status = "failed"
            session.error_message = str(exc)[:500]
            session.updated_at = datetime.utcnow()
            db.commit()
            raise
    finally:
        db.close()


def get_ppt_session_status(session_id: str, user_id: str) -> dict:
    from core.database import SessionLocal
    from models.ppt_session import PptSession

    db = SessionLocal()
    try:
        session = db.query(PptSession).filter(
            PptSession.session_id == session_id,
            PptSession.user_id == user_id,
        ).first()
        if not session:
            return {"found": False}
        return {
            "found": True,
            "session_id": session.session_id,
            "status": session.status,
            "ppt_id": session.ppt_id,
            "cover_url": session.cover_url,
            "template_id": session.template_id,
            "resource_id": session.resource_id,
            "error_message": session.error_message,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }
    finally:
        db.close()


async def one_click_generate_ppt(
    user_id: str,
    topic: str,
    course_name: str,
    knowledge_points: list[str],
) -> dict:
    if not is_docmee_aippt_configured():
        raise RuntimeError("PPT API 未配置，请先在 API 配置中设置 Docmee AiPPT 密钥")

    slide_count = 7
    profile_text = "大学生学习课件"
    try:
        from core.database import SessionLocal
        from models.student import StudentProfile
        db = SessionLocal()
        try:
            p = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
            if p:
                profile_text = f"专业：{p.major or '未知'}，年级：{p.grade or '未知'}"
        finally:
            db.close()
    except Exception:
        pass

    result = await _generate_docmee_aippt(topic, profile_text, user_id, slide_count)

    from core.database import SessionLocal
    from models.resource import LearningResource
    import json

    ppt_data = {
        "title": result["title"],
        "slides": result.get("slides", []),
        "pptx_file": result.get("pptx_file"),
        "pptx_url": result.get("pptx_url", ""),
        "source": "docmee_one_click",
        "template_id": result.get("template_id"),
        "remote_ppt_id": result.get("remote_ppt_id"),
        "cover_url": result.get("cover_url"),
    }

    from services.kp_service import infer_resource_tags
    text_for_tags = " ".join([
        result["title"],
        course_name or "",
        " ".join(knowledge_points or []),
        json.dumps(ppt_data, ensure_ascii=False),
    ])
    graph_tags = infer_resource_tags(
        text_for_tags,
        course_name=course_name,
        knowledge_points=knowledge_points or [],
    )
    tags = list(dict.fromkeys(
        ["ppt"]
        + [x for x in [graph_tags.get("course_name")] if x]
        + list(graph_tags.get("knowledge_points") or [])
    ))

    db = SessionLocal()
    try:
        resource = LearningResource(
            user_id=user_id,
            resource_type="ppt",
            title=result["title"],
            content=ppt_data,
            tags=tags,
            course_name=graph_tags.get("course_name"),
            knowledge_points=graph_tags.get("knowledge_points") or [],
            kp_weights=graph_tags.get("kp_weights") or {},
            tag_confidence=graph_tags.get("tag_confidence") or 0,
        )
        db.add(resource)
        db.flush()
        db.commit()

        try:
            from services.ppt_preview_service import schedule_ppt_preview
            schedule_ppt_preview(resource.id)
        except Exception:
            pass

        try:
            from services.event_service import emit
            import asyncio
            asyncio.ensure_future(emit("resource.created", {
                "user_id": user_id,
                "resource_id": resource.id,
                "course_name": resource.course_name,
                "knowledge_points": resource.knowledge_points,
            }))
        except Exception:
            pass

        return {
            "ok": True,
            "resource": {
                "id": resource.id,
                "title": resource.title,
                "resource_type": resource.resource_type,
                "course_name": resource.course_name,
                "knowledge_points": resource.knowledge_points,
                "pptx_url": ppt_data["pptx_url"],
                "cover_url": result.get("cover_url"),
            },
        }
    finally:
        db.close()
