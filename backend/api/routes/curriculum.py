import json
import os
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.curriculum import Curriculum, UserCourseStatus
from models.course_path import CoursePath

router = APIRouter(prefix="/api/curriculum", tags=["知识图谱-培养方案"])

# 专业 → 预置静态文件名 映射
_PRESET_MAP = {
    "计算机": "curriculum_cs.json",
    "软件": "curriculum_se.json",
    "信息": "curriculum_cs.json",
    "人工智能": "curriculum_ai.json",
    "数学": "curriculum_math.json",
    "统计": "curriculum_math.json",
}

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static")


def _load_preset(major: str) -> list[dict]:
    filename = "curriculum_cs.json"  # 默认
    for key, fname in _PRESET_MAP.items():
        if key in (major or ""):
            filename = fname
            break
    path = os.path.join(_STATIC_DIR, filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def _upsert_curricula(db, user_id: str, courses: list[dict], source: str):
    """将课程列表写入 curricula 表（有则更新，无则插入）"""
    for c in courses:
        stmt = sqlite_insert(Curriculum).values(
            user_id=user_id,
            course_name=c["course_name"],
            semester=c.get("semester", 0),
            category=c.get("category", "必修"),
            prerequisites=c.get("prerequisites", []),
            source=source,
        ).on_conflict_do_update(
            index_elements=["user_id", "course_name"],
            set_=dict(
                semester=c.get("semester", 0),
                category=c.get("category", "必修"),
                prerequisites=c.get("prerequisites", []),
                source=source,
            ),
        )
        db.execute(stmt)
    db.commit()


def _sync_status_from_course_paths(db, user_id: str):
    """将 CoursePath 状态同步到 UserCourseStatus"""
    paths = db.query(CoursePath).filter(CoursePath.user_id == user_id).all()
    for p in paths:
        status = "completed" if p.status == "completed" else "learning"
        stmt = sqlite_insert(UserCourseStatus).values(
            user_id=user_id,
            course_name=p.course_name,
            status=status,
        ).on_conflict_do_update(
            index_elements=["user_id", "course_name"],
            set_=dict(status=status),
        )
        db.execute(stmt)
    db.commit()


@router.get("/graph")
def get_curriculum_graph(user_id: str, major: str = ""):
    db = SessionLocal()
    try:
        courses = db.query(Curriculum).filter(Curriculum.user_id == user_id).all()

        # 首次访问：用预置数据初始化
        if not courses:
            preset = _load_preset(major)
            if preset:
                _upsert_curricula(db, user_id, preset, "preset")
                courses = db.query(Curriculum).filter(Curriculum.user_id == user_id).all()

        # 同步 CoursePath → UserCourseStatus
        _sync_status_from_course_paths(db, user_id)

        # 构建状态字典
        status_rows = db.query(UserCourseStatus).filter(
            UserCourseStatus.user_id == user_id
        ).all()
        status_map = {r.course_name: r.status for r in status_rows}

        nodes = [
            {
                "id": c.course_name,
                "semester": c.semester,
                "category": c.category,
                "status": status_map.get(c.course_name, "not_started"),
            }
            for c in courses
        ]

        # 从 prerequisites 构建边
        links = []
        for c in courses:
            for pre in (c.prerequisites or []):
                links.append({"source": pre, "target": c.course_name})

        return {"nodes": nodes, "links": links}
    finally:
        db.close()


PARSE_PROMPT = """你是一个教育数据提取专家。从以下培养方案文本中提取课程信息，只返回JSON数组。

培养方案文本：
{text}

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
    """用LLM解析培养方案文本，保存并返回课程图谱"""
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
        # 先清除旧的 ai_parsed 数据
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
    """手动更新课程状态（planned / not_started 等）"""
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
def get_course_kp(course_name: str):
    """返回单门课程的知识点图谱 JSON"""
    path = os.path.join(_STATIC_DIR, "kp", f"{course_name}.json")
    if not os.path.exists(path):
        return {"nodes": [], "links": [], "categories": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
