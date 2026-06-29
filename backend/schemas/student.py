from pydantic import BaseModel, field_validator


class ProfileCreate(BaseModel):
    major: str = ""
    grade: str = ""
    learning_goal: str = ""


class QuestionnaireRequest(BaseModel):
    education_level: str = ""
    education_year: str = ""
    current_semester: int | None = None
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
    major: str | None = ""
    grade: str | None = ""
    knowledge_base: dict | None = None
    cognitive_style: str | None = ""
    weak_points: list | None = None
    learning_goal: str | None = ""
    preferred_format: list | None = None
    education_level: str | None = ""
    education_year: str | None = ""
    discipline: str | None = ""
    cross_disciplines: list | None = None
    ability_scores: dict | None = None
    weak_courses: list | None = None
    ability_summary: str | None = ""
    mistake_tendency: dict | None = None
    course_mastery: dict | None = None
    profile_evidence: dict | None = None
    resource_feedback_profile: dict | None = None

    @field_validator(
        "major", "grade", "cognitive_style", "learning_goal",
        "education_level", "education_year", "discipline", "ability_summary",
        mode="before",
    )
    @classmethod
    def none_to_empty_string(cls, value):
        return "" if value is None else value

    @field_validator("weak_points", "preferred_format", "cross_disciplines", "weak_courses", mode="before")
    @classmethod
    def none_to_empty_list(cls, value):
        return [] if value is None else value

    @field_validator(
        "knowledge_base", "ability_scores", "mistake_tendency", "course_mastery",
        "profile_evidence", "resource_feedback_profile",
        mode="before",
    )
    @classmethod
    def none_to_empty_dict(cls, value):
        return {} if value is None else value

    class Config:
        from_attributes = True
