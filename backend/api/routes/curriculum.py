import json
import os

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from core.database import SessionLocal
from core.llm_client import chat_completion
from models.course_path import CoursePath
from models.curriculum import Curriculum, UserCourseStatus
from models.student import StudentProfile
from services.curriculum_service import (
    build_user_curriculum_graph,
    get_course_kp_graph,
    infer_current_semester,
    legacy_courses,
    list_supported_majors,
    load_curriculum_by_major,
)
from services.kp_service import course_coverage

router = APIRouter(prefix="/api/curriculum", tags=["知识图谱-培养方案"])

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def _upsert_curricula(db, user_id: str, courses: list[dict], source: str):
    """将课程列表写入 curricula 表；该表保留给旧解析/兼容逻辑使用。"""
    for course in courses:
        stmt = sqlite_insert(Curriculum).values(
            user_id=user_id,
            course_name=course["course_name"],
            semester=course.get("semester", 0),
            category=course.get("category", "必修"),
            prerequisites=course.get("prerequisites", []),
            source=source,
        ).on_conflict_do_update(
            index_elements=["user_id", "course_name"],
            set_=dict(
                semester=course.get("semester", 0),
                category=course.get("category", "必修"),
                prerequisites=course.get("prerequisites", []),
                source=source,
            ),
        )
        db.execute(stmt)
    db.commit()


def _sync_status_from_course_paths(db, user_id: str):
    """将 CoursePath 完成情况同步到 UserCourseStatus，作为图谱状态覆盖来源之一。"""
    paths = db.query(CoursePath).filter(CoursePath.user_id == user_id).all()
    for path in paths:
        status = "completed" if path.status == "completed" else "learning"
        stmt = sqlite_insert(UserCourseStatus).values(
            user_id=user_id,
            course_name=path.course_name,
            status=status,
        ).on_conflict_do_update(
            index_elements=["user_id", "course_name"],
            set_=dict(status=status),
        )
        db.execute(stmt)
    db.commit()


@router.get("/majors")
def get_supported_majors():
    return list_supported_majors()


@router.get("/graph")
def get_curriculum_graph(
    user_id: str,
    major: str = "",
    current_semester: int | None = Query(None, ge=1, le=8),
    source: str = Query("preset"),
):
    db = SessionLocal()
    try:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        selected_major = major or (profile.major if profile else "")

        if source != "parsed":
            curriculum = load_curriculum_by_major(selected_major)
            resolved_semester = infer_current_semester(
                profile.grade if profile else "",
                current_semester or (profile.current_semester if profile else None),
            )

            if not db.query(Curriculum).filter(Curriculum.user_id == user_id).first():
                _upsert_curricula(db, user_id, legacy_courses(curriculum), "preset_2025")

            _sync_status_from_course_paths(db, user_id)
            status_rows = db.query(UserCourseStatus).filter(
                UserCourseStatus.user_id == user_id
            ).all()
            status_map = {row.course_name: row.status for row in status_rows}
            return build_user_curriculum_graph(
                curriculum,
                profile.knowledge_base if profile else {},
                resolved_semester,
                status_map,
            )

        courses = db.query(Curriculum).filter(Curriculum.user_id == user_id).all()
        _sync_status_from_course_paths(db, user_id)
        status_rows = db.query(UserCourseStatus).filter(
            UserCourseStatus.user_id == user_id
        ).all()
        status_map = {row.course_name: row.status for row in status_rows}
        nodes = [
            {
                "id": course.course_name,
                "course_id": course.course_name,
                "name": course.course_name,
                "semester": course.semester,
                "category": course.category,
                "module": "",
                "credits": None,
                "status": status_map.get(course.course_name, "not_started"),
                "mastery": 0,
                "kp_file": None,
            }
            for course in courses
        ]
        links = [
            {
                "source": prereq,
                "target": course.course_name,
                "source_course_id": prereq,
                "target_course_id": course.course_name,
                "type": "prerequisite",
                "reason": "AI 解析培养方案得到的先修关系",
            }
            for course in courses
            for prereq in (course.prerequisites or [])
        ]
        return {
            "nodes": nodes,
            "links": links,
            "meta": {
                "major_id": "parsed",
                "major_name": selected_major or "AI解析培养方案",
                "version": "custom",
                "current_semester": current_semester,
            },
        }
    finally:
        db.close()


PARSE_PROMPT = """你是一个教育数据提取专家。从以下培养方案文本中提取课程信息，只返回JSON数组。
培养方案文本：{text}

每门课程提取：
- course_name: 课程名称
- semester: 建议学期（整数1-8，不确定填0）
- category: 课程类别（必修/选修/通识，不确定填必修）
- prerequisites: 先修课程名称列表（没有则为空数组）
只返回JSON数组，不要其他内容。格式：
[{{"course_name":"...","semester":1,"category":"必修","prerequisites":[]}}]"""


class ParseRequest(BaseModel):
    user_id: str
    text: str


@router.post("/parse")
async def parse_curriculum(req: ParseRequest):
    """备用入口：用 LLM 解析用户粘贴的培养方案文本。"""
    resp = await chat_completion(
        [{"role": "user", "content": PARSE_PROMPT.format(text=req.text[:4000])}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    courses = json.loads(raw)

    db = SessionLocal()
    try:
        db.query(Curriculum).filter(
            Curriculum.user_id == req.user_id,
            Curriculum.source == "ai_parsed",
        ).delete()
        db.commit()
        _upsert_curricula(db, req.user_id, courses, "ai_parsed")
    finally:
        db.close()

    return {"ok": True, "count": len(courses), "courses": courses}


@router.post("/status")
def update_course_status(user_id: str, course_name: str, status: str):
    """手动更新课程状态。"""
    db = SessionLocal()
    try:
        stmt = sqlite_insert(UserCourseStatus).values(
            user_id=user_id, course_name=course_name, status=status
        ).on_conflict_do_update(
            index_elements=["user_id", "course_name"],
            set_=dict(status=status),
        )
        db.execute(stmt)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("/kp/{course_name:path}")
def get_course_kp(course_name: str, major: str = ""):
    """返回单门课程的知识点图谱 JSON，支持培养方案 kp_file 映射。"""
    return get_course_kp_graph(course_name, major)


@router.get("/coverage/{course_name:path}")
def get_course_kp_coverage(course_name: str, user_id: str):
    """返回单门课程各知识点掌握度。"""
    db = SessionLocal()
    try:
        return course_coverage(db, user_id, course_name)
    finally:
        db.close()


@router.get("/courseware/{course_name:path}")
def get_courseware(course_name: str):
    """返回比赛演示用的完整课程样例资料。"""
    path = os.path.join(_DATA_DIR, "courseware", f"{course_name}.json")
    if not os.path.exists(path):
        return {"found": False, "course_name": course_name}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {"found": True, **data}
