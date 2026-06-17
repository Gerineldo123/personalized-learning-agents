from pydantic import BaseModel
from typing import Optional, Union


class ThinkingData(BaseModel):
    content: str = ""


class SearchResult(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class SearchData(BaseModel):
    query: str = ""
    results: list[SearchResult] = []
    answer: str = ""


class MemoryData(BaseModel):
    action: str = "read"
    key: str = ""
    value: str = ""


class CodeData(BaseModel):
    language: str = "javascript"
    code: str = ""
    output: str = ""
    status: str = "completed"


class ScrapeData(BaseModel):
    url: str = ""
    content: str = ""


class SkillData(BaseModel):
    skill_name: str = ""
    skill_icon: str = "🔧"
    content: str = ""
    sub_steps: list[str] = []
    language: str = ""


class ResultData(BaseModel):
    content: str = ""


class StepEvent(BaseModel):
    type: str = "step"
    step_type: str
    step_id: str
    status: str = "running"
    title: str = ""
    data: Optional[dict] = None


class AgentExecuteRequest(BaseModel):
    user_id: str
    task_description: str
    conversation_id: Optional[int] = None
    history: Optional[list[dict]] = None
    file_content: Optional[str] = None
    file_name: Optional[str] = None


class UploadResponse(BaseModel):
    ok: bool = True
    file_name: str = ""
    content: str = ""
    size: int = 0
    error: str = ""
