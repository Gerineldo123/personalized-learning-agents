import json
import os

from models.student import StudentProfile

_KP_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "kp")

course_kp_map: dict[str, list[str]] = {}
kp_course_map: dict[str, str] = {}


def _build_index():
    if not os.path.exists(_KP_DIR):
        return
    for fname in os.listdir(_KP_DIR):
        if not fname.endswith(".json"):
            continue
        course = fname[:-5]
        try:
            with open(os.path.join(_KP_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            nodes = [n["id"] for n in data.get("nodes", []) if n.get("id")]
            course_kp_map[course] = nodes
            for node in nodes:
                kp_course_map[node] = course
        except Exception:
            pass


_build_index()


def match_kp(text: str) -> list[str]:
    return [kp for kp in kp_course_map if kp in (text or "")]


def infer_resource_tags(
    text: str,
    course_name: str | None = None,
    knowledge_points: list[str] | None = None,
) -> dict:
    explicit_kps = [kp for kp in (knowledge_points or []) if kp in kp_course_map]
    matched_kps = explicit_kps or match_kp(text or "")

    if course_name:
        course = course_name
    elif matched_kps:
        counts: dict[str, int] = {}
        for kp in matched_kps:
            course = kp_course_map.get(kp)
            if course:
                counts[course] = counts.get(course, 0) + 1
        course = max(counts, key=counts.get) if counts else None
    else:
        course_matches = [course for course in course_kp_map if course in (text or "")]
        course = course_matches[0] if course_matches else None

    if course and course in course_kp_map:
        allowed = set(course_kp_map.get(course, []))
        matched_kps = [kp for kp in matched_kps if kp in allowed]

    unique_kps = list(dict.fromkeys(matched_kps))
    kp_weights = {}
    if unique_kps:
        weight = round(1 / len(unique_kps), 4)
        kp_weights = {kp: weight for kp in unique_kps}

    confidence = 0.0
    if explicit_kps:
        confidence = 1.0
    elif unique_kps:
        confidence = 0.8
    elif course:
        confidence = 0.45

    return {
        "course_name": course,
        "knowledge_points": unique_kps,
        "kp_weights": kp_weights,
        "tag_confidence": confidence,
    }


def update_knowledge_base(db, user_id: str, kp_scores: dict[str, float], alpha: float = 0.3):
    if not kp_scores:
        return
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    if not profile:
        return
    kb = dict(profile.knowledge_base or {})
    alpha = max(0.0, min(alpha, 1.0))
    for kp, score in kp_scores.items():
        old = kb.get(kp, 0.0)
        score = max(0.0, min(float(score), 1.0))
        kb[kp] = round(old * (1 - alpha) + score * alpha, 4)
    profile.knowledge_base = kb
    db.commit()


def set_course_kp_scores(db, user_id: str, course_name: str, score: float):
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
