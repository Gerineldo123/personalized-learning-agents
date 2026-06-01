import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from core.database import engine, Base
from core.exceptions import AppException, AgentNotFoundError
from models.student import StudentProfile
from models.resource import LearningResource
from models.conversation import Conversation, ChatMessage
from models.quiz_record import QuizRecord
from models.mistake_question import MistakeQuestion
from models.course_path import CoursePath
from models.user import User

Base.metadata.create_all(bind=engine)


def _ensure_resource_pinned_column():
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(learning_resources)").fetchall()
        names = {c[1] for c in cols}
        if "pinned" not in names:
            conn.exec_driver_sql("ALTER TABLE learning_resources ADD COLUMN pinned INTEGER DEFAULT 0")
            conn.commit()


_ensure_resource_pinned_column()

app = FastAPI(title="个性化学习智能体系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

register(ProfileAgent())
register(ContentGenAgent())
register(MindMapAgent())
register(EvaluationAgent())
register(ChatAgent())

from services.event_service import on

from api.routes import chat, student, resource, evaluation, config, conversation, events, quiz, mistake, course_path, auth

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

print("Registered agents:", [a.name for a in get_all_agents()])


@on("evaluation.completed")
async def on_evaluation_completed(data: dict):
    user_id = data.get("user_id", "")
    score = data.get("overall_score", 0)
    print(f"[Event] evaluation completed for {user_id}, score: {score}")


@app.get("/health")
async def health():
    return {"status": "ok"}



