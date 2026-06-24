import re
import bcrypt
from fastapi import APIRouter, HTTPException
from core.database import SessionLocal
from core.auth import create_token, require_user
from models.user import User
from models.student import StudentProfile

router = APIRouter(prefix="/api/auth", tags=["认证"])

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]{6,14}$")

# 专业 → 学科门类映射
_MAJOR_DISCIPLINE = {
    "计算机科学与技术": "计算机",
    "软件工程": "软件",
    "人工智能": "人工智能",
    "智能科学与技术": "计算机",
}

# 年级 → 已完成学期数映射
_GRADE_SEMESTER = {
    "大一": 1, "大二": 3, "大三": 5, "大四": 7,
    "研一": 1, "研二": 3, "研三": 5,
    "博一": 1, "博二": 3, "博三": 5,
    "专科大一": 1, "专科大二": 3, "专科大三": 5,
}


def _validate_phone(phone: str):
    if not PHONE_RE.match(phone or ""):
        raise HTTPException(status_code=400, detail="手机号格式不正确")


def _validate_password(password: str):
    if not PASSWORD_RE.match(password or ""):
        raise HTTPException(status_code=400, detail="密码需为6~14位，且仅可包含大小写字母、数字和特殊符号")


@router.post('/register')
def register(
    phone: str, password: str, confirm_password: str,
    education_level: str = "本科", grade: str = "", major: str = "",
):
    _validate_phone(phone)
    _validate_password(password)
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.phone == phone).first():
            raise HTTPException(status_code=400, detail="该手机号已注册")
        pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(phone=phone, password_hash=pwd_hash, first_login=False)
        db.add(user)
        db.commit()

        # 创建 StudentProfile
        discipline = _MAJOR_DISCIPLINE.get(major, "计算机")
        profile = StudentProfile(
            user_id=phone,
            major=major,
            grade=grade,
            education_level=education_level,
            discipline=discipline,
            knowledge_base={},
            ability_scores={},
            weak_courses=[],
        )
        db.add(profile)
        db.commit()

        # 初始化培养方案 + 按年级点亮节点（复用 curriculum 路由的逻辑）
        _init_curriculum(db, phone, major, grade)

        token = create_token(phone)
        return {"ok": True, "token": token, "phone": phone, "first_login": False}
    finally:
        db.close()


def _init_curriculum(db, user_id: str, major: str, grade: str):
    """注册时初始化培养方案并按年级点亮已学课程"""
    import json, os
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from models.curriculum import Curriculum, UserCourseStatus

    # 已有培养方案则跳过
    if db.query(Curriculum).filter(Curriculum.user_id == user_id).first():
        return

    major_file = {
        "计算机科学与技术": "curriculum_cs.json",
        "软件工程": "curriculum_se.json",
        "人工智能": "curriculum_ai.json",
        "智能科学与技术": "curriculum_cs.json",
    }.get(major, "curriculum_cs.json")

    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    path = os.path.join(static_dir, major_file)
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        courses = json.load(f)

    # 写入培养方案
    for c in courses:
        db.execute(
            sqlite_insert(Curriculum).values(
                user_id=user_id,
                course_name=c["course_name"],
                semester=c.get("semester", 0),
                category=c.get("category", "必修"),
                prerequisites=c.get("prerequisites", []),
                source="preset",
            ).on_conflict_do_nothing()
        )

    # 按年级推算已学学期，点亮节点
    completed_semesters = _GRADE_SEMESTER.get(grade, 0)
    for c in courses:
        sem = c.get("semester", 0)
        if sem == 0:
            continue
        if sem < completed_semesters:
            status = "completed"
        elif sem == completed_semesters:
            status = "learning"
        else:
            continue  # 未来课程不写入，默认 not_started
        db.execute(
            sqlite_insert(UserCourseStatus).values(
                user_id=user_id,
                course_name=c["course_name"],
                status=status,
            ).on_conflict_do_nothing()
        )
    db.commit()


@router.post('/login')
def login(phone: str, password: str):
    _validate_phone(phone)
    _validate_password(password)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            raise HTTPException(status_code=401, detail="手机号或密码错误")
        ok = bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8'))
        if not ok:
            raise HTTPException(status_code=401, detail="手机号或密码错误")
        token = create_token(phone)
        return {"ok": True, "token": token, "phone": phone, "first_login": False}
    finally:
        db.close()


@router.get('/me')
def me(phone: str = require_user):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"ok": True, "phone": user.phone, "first_login": False}
    finally:
        db.close()


@router.post('/mark_first_login_done')
def mark_first_login_done(phone: str = require_user):
    return {"ok": True}

