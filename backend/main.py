import traceback
import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from core.database import engine, Base
from core.exceptions import AppException, AgentNotFoundError
from models.student import StudentProfile
from models.resource import LearningResource
from models.conversation import Conversation, ChatMessage
from models.quiz_record import QuizRecord
from models.mistake_question import MistakeQuestion
from models.course_path import CoursePath
from models.focus import FocusSession
from models.user import User
from models.profile_history import ProfileHistory
from models.curriculum import Curriculum, UserCourseStatus
from models.ppt_session import PptSession
from models.profile_onboarding import ProfileOnboardingSession

Base.metadata.create_all(bind=engine)


def _ensure_resource_pinned_column():
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(learning_resources)").fetchall()
        names = {c[1] for c in cols}
        if "pinned" not in names:
            conn.exec_driver_sql("ALTER TABLE learning_resources ADD COLUMN pinned INTEGER DEFAULT 0")
        for col, typedef in [
            ("course_name", "VARCHAR"),
            ("knowledge_points", "JSON"),
            ("kp_weights", "JSON"),
            ("tag_confidence", "REAL DEFAULT 0"),
            ("learning_status", "VARCHAR DEFAULT 'not_started'"),
            ("progress", "REAL DEFAULT 0"),
            ("completed_at", "TIMESTAMP"),
        ]:
            if col not in names:
                conn.exec_driver_sql(f"ALTER TABLE learning_resources ADD COLUMN {col} {typedef}")
            conn.commit()


_ensure_resource_pinned_column()


def _ensure_focus_columns():
    with engine.connect() as conn:
        cols = {c[1] for c in conn.exec_driver_sql("PRAGMA table_info(student_profiles)").fetchall()}
        for col, typedef in [
            ("current_semester", "INTEGER"),
            ("mistake_tendency", "JSON"),
            ("course_mastery", "JSON"),
            ("profile_evidence", "JSON"),
            ("resource_feedback_profile", "JSON"),
            ("focus_stamina_score", "INTEGER"),
            ("focus_peak_hours",    "JSON"),
            ("focus_interrupt_rate","REAL"),
            ("focus_weekly_avg_min","INTEGER"),
        ]:
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE student_profiles ADD COLUMN {col} {typedef}")
        conn.commit()


_ensure_focus_columns()


def _ensure_mistake_columns():
    with engine.connect() as conn:
        cols = {c[1] for c in conn.exec_driver_sql("PRAGMA table_info(mistake_questions)").fetchall()}
        if "analysis" not in cols:
            conn.exec_driver_sql("ALTER TABLE mistake_questions ADD COLUMN analysis JSON")
        if "wrong_count" not in cols:
            conn.exec_driver_sql("ALTER TABLE mistake_questions ADD COLUMN wrong_count INTEGER DEFAULT 1")
        if "last_wrong_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE mistake_questions ADD COLUMN last_wrong_at TIMESTAMP")
        conn.commit()


_ensure_mistake_columns()


def _ensure_course_path_columns():
    with engine.connect() as conn:
        cols = {c[1] for c in conn.exec_driver_sql("PRAGMA table_info(course_paths)").fetchall()}
        for col, typedef in [
            ("display_name", "VARCHAR"),
            ("is_archived", "INTEGER DEFAULT 0"),
            ("archived_at", "TIMESTAMP"),
        ]:
            if col not in cols:
                conn.exec_driver_sql(f"ALTER TABLE course_paths ADD COLUMN {col} {typedef}")
        conn.commit()


_ensure_course_path_columns()


def _repair_legacy_resource_titles():
    try:
        from core.database import SessionLocal
        from services.resource_title_service import repair_legacy_code_resource_titles
        repaired = repair_legacy_code_resource_titles(SessionLocal)
        if repaired:
            print(f"Repaired legacy code resource titles: {repaired}")
    except Exception as exc:
        print(f"[WARN] repair legacy code resource titles failed: {exc}")


_repair_legacy_resource_titles()

app = FastAPI(title="智途｜个性化学习智能体系统")

_course_kb_warmup_task = None


@app.on_event("startup")
async def warmup_course_knowledge_base():
    """后台预热公共课程知识库，不阻塞 API 服务启动。"""
    global _course_kb_warmup_task

    async def run_seed():
        try:
            from services.rag_service import ensure_course_knowledge_base
            status = await asyncio.to_thread(ensure_course_knowledge_base)
            print(
                "Course knowledge base ready: "
                f"{status.get('document_count', 0)} documents / {status.get('chunk_count', 0)} chunks"
            )
        except Exception as exc:
            print(f"[WARN] course knowledge base warmup failed: {exc}")

    _course_kb_warmup_task = asyncio.create_task(run_seed())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录，供下载 .pptx 等文件
import os as _os
_static_dir = _os.path.join(_os.path.dirname(__file__), "static")
_os.makedirs(_os.path.join(_static_dir, "ppt"), exist_ok=True)
_os.makedirs(_os.path.join(_static_dir, "ppt_preview"), exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.code,
        content={"detail": exc.message},
    )


@app.exception_handler(AgentNotFoundError)
async def agent_not_found_handler(request: Request, exc: AgentNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"[ERROR] Unhandled exception: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Server Error"},
    )

from agents.registry import register, get_all_agents
from agents.profile_agent import ProfileAgent
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.evaluation_agent import EvaluationAgent
from agents.chat_agent import ChatAgent
from agents.video_agent import VideoAgent
from agents.skills import init_skills

register(ProfileAgent())
register(ContentGenAgent())
register(MindMapAgent())
register(EvaluationAgent())
register(ChatAgent())
register(VideoAgent())

# 初始化 Skill 系统
init_skills()

from services.event_service import on

from api.routes import chat, student, resource, evaluation, config, conversation, events, quiz, mistake, course_path, auth, focus, workflow, weak_point, agent_panel, curriculum, profile_onboarding, ppt as ppt_routes

app.include_router(chat.router)
app.include_router(student.router)
app.include_router(resource.router)
app.include_router(evaluation.router)
app.include_router(config.router)
app.include_router(conversation.router)
app.include_router(events.router)
app.include_router(quiz.router)
app.include_router(mistake.router)
app.include_router(course_path.router)
app.include_router(auth.router)
app.include_router(focus.router)
app.include_router(workflow.router)
app.include_router(weak_point.router)
app.include_router(agent_panel.router)
app.include_router(curriculum.router)
app.include_router(profile_onboarding.router)
app.include_router(ppt_routes.router)

print("Registered agents:", [a.name for a in get_all_agents()])


@on("evaluation.completed")
async def on_evaluation_completed(data: dict):
    user_id = data.get("user_id", "")
    score = data.get("overall_score", 0)
    print(f"[Event] evaluation completed for {user_id}, score: {score}")


@app.get("/health")
async def health():
    return {"status": "ok"}



