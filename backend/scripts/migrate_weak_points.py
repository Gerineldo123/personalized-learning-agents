"""一次性迁移脚本：将旧 weak_points 字段迁移到 WeakPoint 表"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal
from models.student import StudentProfile
from models.weak_point import WeakPoint
from core.database import Base, engine

# 确保表已创建
from models import weak_point  # noqa
Base.metadata.create_all(bind=engine)


def migrate():
    db = SessionLocal()
    try:
        profiles = db.query(StudentProfile).all()
        count = 0
        for p in profiles:
            if not p.weak_points:
                continue
            for name in p.weak_points:
                exists = db.query(WeakPoint).filter(
                    WeakPoint.user_id == p.user_id,
                    WeakPoint.name == name
                ).first()
                if not exists:
                    db.add(WeakPoint(user_id=p.user_id, name=name))
                    count += 1
        db.commit()
        print(f"迁移完成，共新增 {count} 条记录")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
