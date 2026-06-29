import json
import os

from models.student import StudentProfile

_KP_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "kp")
_CURRICULA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "curricula")

course_kp_map: dict[str, list[str]] = {}
kp_course_map: dict[str, str] = {}
course_graph_map: dict[str, dict] = {}


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
            course_graph_map[course] = data
            for node in nodes:
                kp_course_map[node] = course
        except Exception:
            pass

    if not os.path.exists(_CURRICULA_DIR):
        return
    for fname in os.listdir(_CURRICULA_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_CURRICULA_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            for course in data.get("courses", []):
                kp_file = course.get("kp_file")
                if not kp_file:
                    continue
                base_course = os.path.splitext(os.path.basename(kp_file))[0]
                nodes = course_kp_map.get(base_course, [])
                graph = course_graph_map.get(base_course)
                if not nodes or not graph:
                    continue
                aliases = [course.get("name"), course.get("id")]
                for alias in [a for a in aliases if a]:
                    course_kp_map[alias] = nodes
                    course_graph_map[alias] = graph
                display_name = course.get("name") or base_course
                for node in nodes:
                    kp_course_map[node] = display_name
        except Exception:
            pass


_build_index()


def match_kp(text: str) -> list[str]:
    return [kp for kp in kp_course_map if kp in (text or "")]


def get_course_kps(course_name: str | None) -> list[str]:
    if not course_name:
        return []
    return list(course_kp_map.get(course_name, []))


def infer_course_from_text(text: str, default: str | None = None) -> str | None:
    content = text or ""
    for course in course_kp_map:
        if course in content:
            return course
    matched = match_kp(content)
    if matched:
        return kp_course_map.get(matched[0])
    return default


def default_focus_kps(course_name: str | None, text: str = "", limit: int = 4) -> list[str]:
    matched = match_kp(text or "")
    if matched:
        return list(dict.fromkeys(matched))[:limit]
    nodes = get_course_kps(course_name)
    return nodes[:limit]


def course_coverage(db, user_id: str, course_name: str) -> dict:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    kb = dict(profile.knowledge_base or {}) if profile else {}
    kps = get_course_kps(course_name)
    items = [{"knowledge_point": kp, "mastery": float(kb.get(kp, 0) or 0)} for kp in kps]
    avg = round(sum(x["mastery"] for x in items) / len(items), 4) if items else 0
    return {
        "course_name": course_name,
        "total": len(items),
        "average_mastery": avg,
        "items": items,
    }


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
