import re
import bcrypt
from fastapi import APIRouter, HTTPException
from core.database import SessionLocal
from core.auth import create_token, require_user
from models.user import User

router = APIRouter(prefix="/api/auth", tags=["认证"])

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]{6,14}$")


def _validate_phone(phone: str):
    if not PHONE_RE.match(phone or ""):
        raise HTTPException(status_code=400, detail="手机号格式不正确")


def _validate_password(password: str):
    if not PASSWORD_RE.match(password or ""):
        raise HTTPException(status_code=400, detail="密码需为6~14位，且仅可包含大小写字母、数字和特殊符号")


@router.post('/register')
def register(phone: str, password: str, confirm_password: str):
    _validate_phone(phone)
    _validate_password(password)
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")

    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.phone == phone).first()
        if exists:
            raise HTTPException(status_code=400, detail="该手机号已注册")
        pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(phone=phone, password_hash=pwd_hash, first_login=True)
        db.add(user)
        db.commit()
        token = create_token(phone)
        return {"ok": True, "token": token, "phone": phone, "first_login": True}
    finally:
        db.close()


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
        return {"ok": True, "token": token, "phone": phone, "first_login": bool(user.first_login)}
    finally:
        db.close()


@router.get('/me')
def me(phone: str = require_user):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"ok": True, "phone": user.phone, "first_login": bool(user.first_login)}
    finally:
        db.close()


@router.post('/mark_first_login_done')
def mark_first_login_done(phone: str = require_user):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        user.first_login = False
        db.commit()
        return {"ok": True}
    finally:
        db.close()
