import json
import asyncio
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from core.sse import sse_stream
from schemas.agent import AgentExecuteRequest, UploadResponse
from graph.subgraphs.agent_execute import agent_execute_graph

router = APIRouter(prefix="/api/agent", tags=["Agent面板"])

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


async def _make_state(task_description: str, user_id: str, file_content: str = "", file_name: str = "") -> dict:
    user_message = task_description
    if file_content and file_name:
        user_message = f"文件: {file_name}\n内容:\n```\n{file_content[:3000]}\n```\n\n任务: {task_description}"

    return {
        "user_id": user_id,
        "user_message": user_message,
        "profile": None,
        "history": [],
        "messages": [],
        "response": "",
        "agent_name": "",
        "task_plan": [],
        "agent_feedback": {},
        "completed_tasks": [],
        "all_modules_data": {"file_name": file_name, "file_content": file_content} if file_content else {},
        "workflow_outputs": [],
    }


async def _agent_stream(task_description: str, user_id: str, file_content: str = "", file_name: str = ""):
    state = await _make_state(task_description, user_id, file_content, file_name)
    graph = agent_execute_graph
    yielded = 0

    try:
        async for chunk in graph.astream(state, stream_mode="updates"):
            for node_name, node_update in chunk.items():
                wf = node_update.get("workflow_outputs", None)
                if wf is None:
                    continue
                for i in range(yielded, len(wf)):
                    yield json.dumps(wf[i], ensure_ascii=False) + "\n"
                    yielded = i + 1
    except Exception as e:
        yield json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False) + "\n"


@router.post("/execute/stream")
async def execute_stream(req: AgentExecuteRequest):
    return StreamingResponse(
        sse_stream(_agent_stream(req.task_description, req.user_id, req.file_content or "", req.file_name or "")),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
