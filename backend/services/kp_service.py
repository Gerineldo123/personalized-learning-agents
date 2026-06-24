"""
知识点索引工具：从 kp/*.json 构建课程→知识点映射，提供掌握度更新函数。
"""
import json
import os
from models.student import StudentProfile

_KP_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "kp")

# 构建两张索引表（模块加载时执行一次）
# course_kp_map: {"课程名": ["知识点1", "知识点2", ...]}
# kp_course_map: {"知识点": "课程名"}
course_kp_map: dict[str, list[str]] = {}
kp_course_map: dict[str, str] = {}

def _build_index():
    if not os.path.exists(_KP_DIR):
        return
    for fname in os.listdir(_KP_DIR):
        if not fname.endswith(".json"):
            continue
        course = fname[:-5]  # 去掉 .json
        try:
            with open(os.path.join(_KP_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            nodes = [n["id"] for n in data.get("nodes", [])]
            course_kp_map[course] = nodes
            for n in nodes:
                kp_course_map[n] = course
        except Exception:
            pass

_build_index()


def match_kp(text: str) -> list[str]:
    """在文本中查找匹配的知识点名称（精确包含匹配）"""
    return [kp for kp in kp_course_map if kp in text]


def update_knowledge_base(db, user_id: str, kp_scores: dict[str, float]):
    """
    用滑动平均更新 StudentProfile.knowledge_base。
    kp_scores: {知识点名: 本次得分 0.0~1.0}
    公式: new = old * 0.7 + score * 0.3
    """
    if not kp_scores:
        return
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not profile:
        return
    kb = dict(profile.knowledge_base or {})
    for kp, score in kp_scores.items():
        old = kb.get(kp, 0.0)
        kb[kp] = round(old * 0.7 + score * 0.3, 4)
    profile.knowledge_base = kb
    db.commit()


def set_course_kp_scores(db, user_id: str, course_name: str, score: float):
    """将某门课的所有知识点掌握度设为指定值（课程完成时调用）"""
    kps = course_kp_map.get(course_name, [])
    if not kps:
        return
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not profile:
        return
    kb = dict(profile.knowledge_base or {})
    for kp in kps:
        kb[kp] = score
    profile.knowledge_base = kb
    db.commit()
