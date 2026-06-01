from pydantic import BaseModel


class ProfileCreate(BaseModel):
    major: str = ""
    grade: str = ""
    learning_goal: str = ""


class QuestionnaireRequest(BaseModel):
    education_level: str = ""
    education_year: str = ""
    discipline: str = ""
    major: str = ""
    cross_disciplines: list[str] = []
    courses: list[dict] = []


class CourseInfo(BaseModel):
    name: str
    knowledge_points: str = ""
    difficulty_types: list[str] = []
    impacts: list[str] = []
    goal: str = ""


class ProfileResponse(BaseModel):
    user_id: str
    major: str
    grade: str
    knowledge_base: dict
    cognitive_style: str
    weak_points: list
    learning_goal: str
    preferred_format: list
    education_level: str = ""
    education_year: str = ""
    discipline: str = ""
    cross_disciplines: list = []
    ability_scores: dict = {}
    weak_courses: list = []
    ability_summary: str = ""

    class Config:
        from_attributes = True
