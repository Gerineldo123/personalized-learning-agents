from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    history: list[dict] | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    agent_name: str
    content: str
    resource_type: str | None = None


class QuizSubmitRequest(BaseModel):
    user_id: str
    resource_id: int
    answers: dict
    score: float
    time_spent: int = 0
