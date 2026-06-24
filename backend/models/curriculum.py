from sqlalchemy import Column, Integer, String, JSON, UniqueConstraint
from core.database import Base


class Curriculum(Base):
    """学生个人培养方案（来源：预置或AI解析）"""
    __tablename__ = "curricula"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    course_name = Column(String)
    semester = Column(Integer, default=0)   # 建议学期 1~8，0=未知
    category = Column(String, default="必修")  # 必修/选修/通识
    prerequisites = Column(JSON, default=list)  # ["课程A", "课程B"]
    source = Column(String, default="preset")   # "preset" | "ai_parsed"

    __table_args__ = (UniqueConstraint("user_id", "course_name"),)


class UserCourseStatus(Base):
    """学生各课程学习状态（与 CoursePath 联动）"""
    __tablename__ = "user_course_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True)
    course_name = Column(String)
    status = Column(String, default="not_started")  # completed/learning/planned/not_started

    __table_args__ = (UniqueConstraint("user_id", "course_name"),)
