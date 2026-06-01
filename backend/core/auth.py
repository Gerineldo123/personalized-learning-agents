import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Header, HTTPException


JWT_SECRET = os.getenv("JWT_SECRET", "learning-agent-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


def create_token(phone: str) -> str:
    payload = {
        "sub": phone,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        phone = payload.get("sub", "")
        if not phone:
            raise HTTPException(status_code=401, detail="无效的登录凭证")
        return phone
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的登录凭证")


def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization:
        return ""
    if not authorization.startswith("Bearer "):
        return ""
    token = authorization[7:]
    return verify_token(token)


def require_user(authorization: str = Header(None)) -> str:
    phone = get_current_user(authorization)
    if not phone:
        raise HTTPException(status_code=401, detail="请先登录")
    return phone
