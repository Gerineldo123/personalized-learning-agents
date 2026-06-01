from sqlalchemy import Column, String, Boolean, DateTime
from core.database import Base
from datetime import datetime, timezone


class User(Base):
    __tablename__ = "users"

    phone = Column(String, primary_key=True)
    password_hash = Column(String, nullable=False)
    first_login = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
