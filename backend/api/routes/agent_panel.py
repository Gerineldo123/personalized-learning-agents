import json
import asyncio
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from core.sse import sse_stream
from core import sse_registry
from schemas.agent import AgentExecuteRequest, UploadResponse
from graph.subgraphs.agent_execute import agent_execute_graph

router = APIRouter(prefix="/api/agent", tags=["Agent面板"])

def _group_tokens(wf: list) -> dict:
    """按 step_id 分组归集 token 事件，保持顺序"""
    groups: dict = {}
    for e in wf:
        if e.get("type") == "token":
            sid = e.get("step_id", "")
            groups.setdefault(sid, []).append(e)
    return groups

MAX_FILE_SIZE = 10 * 1024 * 1024
TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".xml", ".yaml", ".yml",
             ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css",
             ".java", ".c", ".cpp", ".h", ".rs", ".go", ".sh", ".sql",
             ".toml", ".ini", ".cfg", ".log", ".tex"}


def _extract_text(filename: str, content: bytes) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = "." + ext if ext else ""

    if ext in TEXT_EXTS or ext in {".rst", ".bat", ".ps1"}:
        try:
            return {"content": content.decode("utf-8"), "error": ""}
        except UnicodeDecodeError:
            try:
                return {"content": content.decode("gbk"), "error": ""}
            except Exception:
                return {"content": "", "error": "文件编码不支持"}

    if ext == ".pdf":
        try:
            from io import BytesIO
            try:
                from PyPDF2 import PdfReader
            except ImportError:
                try:
                    from pypdf import PdfReader
                except ImportError:
                    return {"content": "", "error": "未安装PDF解析库(PyPDF2)，无法解析PDF文件"}
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return {"content": text[:10000], "error": "" if text else "PDF无可提取文本"}
        except Exception as e:
            return {"content": "", "error": f"PDF解析失败: {e}"}

    return {"content": content.decode("utf-8", errors="replace")[:5000], "error": ""}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse(status_code=400, content={"ok": False, "error": "文件名为空"})

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return JSONResponse(status_code=400, content={"ok": False, "error": f"文件超过最大限制 {MAX_FILE_SIZE // 1024 // 1024}MB"})

    result = _extract_text(file.filename, content)
    if result["error"]:
        return JSONResponse(status_code=400, content={"ok": False, "error": result["error"], "file_name": file.filename, "content": "", "size": len(content)})

    return UploadResponse(file_name=file.filename, content=result["content"], size=len(content)).model_dump()


async def _make_state(task_description: str, user_id: str, file_content: str = "", file_name: str = "", history: list | None = None) -> dict:
    user_message = task_description
    if file_content and file_name:
        user_message = f"文件: {file_name}\n内容:\n```\n{file_content[:3000]}\n```\n\n任务: {task_description}"

    profile = None
    profile_text = "暂无学生画像"
    try:
        from core.database import SessionLocal
        from models.student import StudentProfile
        from models.mistake_question import MistakeQuestion
        from models.focus import FocusSession
        import json as _json
        db = SessionLocal()
        try:
            profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
            mistakes = db.query(MistakeQuestion).filter(
                MistakeQuestion.user_id == user_id
            ).order_by(MistakeQuestion.created_at.desc()).limit(5).all()
            mistake_text = "、".join([
                (m.question.get("question", "")[:30] if m.question else "") for m in mistakes
            ]) or "无"
            sessions = db.query(FocusSession).filter(
                FocusSession.user_id == user_id
            ).order_by(FocusSession.started_at.desc()).limit(20).all()
            focus_text = "无专注记录"
            if sessions:
                total = sum(s.duration_min for s in sessions)
                done = sum(1 for s in sessions if s.completed)
                focus_text = f"累计专注{total}分钟，完成{done}/{len(sessions)}次"
            profile_data = {"最近错题": mistake_text, "专注情况": focus_text}
            if profile:
                profile_data = {
                    "专业": profile.major, "年级": profile.grade,
                    "知识基础": profile.knowledge_base, "薄弱知识点": profile.weak_points,
                    "学习目标": profile.learning_goal,
                    "最近错题": mistake_text, "专注情况": focus_text,
                }
            profile_text = _json.dumps(profile_data, ensure_ascii=False)
        finally:
            db.close()
    except Exception:
        pass

    return {
        "user_id": user_id,
        "user_message": user_message,
        "profile": profile,
        "profile_text": profile_text,
        "history": (history or [])[-20:],
        "messages": [],
        "response": "",
        "agent_name": "",
        "task_plan": [],
        "agent_feedback": {},
        "completed_tasks": [],
        "all_modules_data": {"file_name": file_name, "file_content": file_content} if file_content else {},
        "workflow_outputs": [],
    }


async def _agent_stream(task_description: str, user_id: str, file_content: str = "", file_name: str = "", history: list | None = None):
    state = await _make_state(task_description, user_id, file_content, file_name, history)

    session_id = str(id(state))
    sse_queue: asyncio.Queue = asyncio.Queue(maxsize=512)
    sse_registry.register(session_id, sse_queue)
    state["_session_id"] = session_id
    _DONE = object()

    live_pushed: set = set()
    token_counts: dict = {}  # step_id -> 已推送的 token 数量
    step_pushed: set = set()  # (step_id, status) -> 已推送的 step 事件

    async def run_graph():
        try:
            async for chunk in graph.astream(state, stream_mode="updates"):
                for node_name, node_update in chunk.items():
                    wf = node_update.get("workflow_outputs", None)
                    if wf is None:
                        continue
                    # token 增量去重
                    for sid, tokens in _group_tokens(wf).items():
                        already = token_counts.get(sid, 0)
                        for te in tokens[already:]:
                            await sse_queue.put(te)
                        token_counts[sid] = len(tokens)
                    # 非 token 事件去重
                    for event in wf:
                        if event.get("type") == "token":
                            continue
                        step_type = event.get("step_type")
                        key = (event.get("step_id"), event.get("status"), step_type)
                        if key in step_pushed:
                            continue
                        step_pushed.add(key)
                        if step_type == "skill":
                            live_pushed.add((event.get("step_id"), event.get("status")))
                        await sse_queue.put(event)
        except Exception as e:
            await sse_queue.put({"type": "error", "message": str(e)})
        finally:
            await sse_queue.put(_DONE)

    graph = agent_execute_graph
    graph_task = asyncio.create_task(run_graph())

    try:
        while True:
            item = await sse_queue.get()
            if item is _DONE:
                break
            if isinstance(item, dict) and item.get("step_type") == "skill":
                live_pushed.add((item.get("step_id"), item.get("status")))
            yield json.dumps(item, ensure_ascii=False) + "\n"
    finally:
        graph_task.cancel()
        sse_registry.unregister(session_id)


@router.post("/execute/stream")
async def execute_stream(req: AgentExecuteRequest):
    return StreamingResponse(
        sse_stream(_agent_stream(req.task_description, req.user_id, req.file_content or "", req.file_name or "", req.history or [])),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
