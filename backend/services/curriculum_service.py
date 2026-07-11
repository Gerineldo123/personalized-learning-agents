import json
import os
from functools import lru_cache
from typing import Any


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CURRICULA_DIR = os.path.join(BASE_DIR, "data", "curricula")
KP_DIR = os.path.join(BASE_DIR, "static", "kp")

MAJOR_FILES = {
    "computer_science": "computer_science_2025.json",
    "software_engineering": "software_engineering_2025.json",
    "artificial_intelligence": "artificial_intelligence_2025.json",
    "intelligent_science": "intelligent_science_2025.json",
}

MAJOR_ALIASES = {
    "计算机科学与技术": "computer_science",
    "计算机": "computer_science",
    "软件工程": "software_engineering",
    "软件": "software_engineering",
    "人工智能": "artificial_intelligence",
    "智能科学与技术": "intelligent_science",
    "智能科学": "intelligent_science",
}

GRADE_CURRENT_SEMESTER = {
    "大一": 1,
    "大二": 3,
    "大三": 5,
    "大四": 7,
    "大五": 9,
    "研一": 1,
    "研二": 3,
    "研三": 5,
    "博一": 1,
    "博二": 3,
    "博三": 5,
}

SUMMER_SEMESTER_RANK = {
    "S1": 2.5,
    "S2": 4.5,
    "S3": 6.5,
}


def semester_rank(value: Any) -> float:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper()
    if text in SUMMER_SEMESTER_RANK:
        return SUMMER_SEMESTER_RANK[text]
    try:
        return float(text)
    except ValueError:
        return 0


def infer_current_semester(grade: str = "", current_semester: int | None = None) -> int:
    if current_semester:
        return max(1, min(int(current_semester), 8))
    grade_text = grade or ""
    for key, value in GRADE_CURRENT_SEMESTER.items():
        if key in grade_text:
            return max(1, min(value, 8))
    return 1


def resolve_major_id(major: str = "") -> str:
    value = (major or "").strip()
    if value in MAJOR_FILES:
        return value
    if value in MAJOR_ALIASES:
        return MAJOR_ALIASES[value]
    for key, major_id in MAJOR_ALIASES.items():
        if key and key in value:
            return major_id
    return "computer_science"


@lru_cache(maxsize=16)
def load_curriculum_by_id(major_id: str) -> dict:
    filename = MAJOR_FILES.get(major_id, MAJOR_FILES["computer_science"])
    path = os.path.join(CURRICULA_DIR, filename)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data


def load_curriculum_by_major(major: str = "") -> dict:
    return load_curriculum_by_id(resolve_major_id(major))


def list_supported_majors() -> list[dict]:
    items = []
    for major_id in MAJOR_FILES:
        data = load_curriculum_by_id(major_id)
        items.append({
            "major_id": data.get("major_id") or major_id,
            "major_name": data.get("major_name") or major_id,
            "major_code": data.get("major_code") or "",
            "version": data.get("version") or "",
            "total_credits": data.get("total_credits"),
        })
    return items


def course_name_map(curriculum: dict) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for course in curriculum.get("courses", []):
        for key in (course.get("id"), course.get("name")):
            if key:
                mapping[str(key)] = course
    return mapping


def prerequisite_names(curriculum: dict, course_id: str) -> list[str]:
    courses = course_name_map(curriculum)
    names = []
    for rel in curriculum.get("relations", []):
        if rel.get("target") == course_id and rel.get("type") == "prerequisite":
            source = courses.get(rel.get("source"))
            if source and source.get("name"):
                names.append(source["name"])
    return names


def legacy_courses(curriculum: dict) -> list[dict]:
    return [
        {
            "course_name": course.get("name") or course.get("id"),
            "semester": int(semester_rank(course.get("semester"))),
            "category": course.get("category") or "必修",
            "prerequisites": prerequisite_names(curriculum, course.get("id") or ""),
        }
        for course in curriculum.get("courses", [])
    ]


def _read_kp_graph_by_file(kp_file: str | None) -> dict:
    if not kp_file:
        return {"nodes": [], "links": [], "categories": []}
    path = os.path.join(KP_DIR, os.path.basename(kp_file))
    if not os.path.exists(path):
        return {"nodes": [], "links": [], "categories": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_course_kp_graph(course_name: str, major: str = "") -> dict:
    target = (course_name or "").strip()
    if target:
        search_curricula = [load_curriculum_by_major(major)] if major else [
            load_curriculum_by_id(major_id) for major_id in MAJOR_FILES
        ]
        for curriculum in search_curricula:
            for course in curriculum.get("courses", []):
                if target in {course.get("id"), course.get("name")}:
                    graph = _read_kp_graph_by_file(course.get("kp_file"))
                    if graph.get("nodes"):
                        return graph

    direct = _read_kp_graph_by_file(f"{target}.json")
    if direct.get("nodes"):
        return direct
    return {"nodes": [], "links": [], "categories": []}


def get_course_kps(course: dict) -> list[str]:
    graph = _read_kp_graph_by_file(course.get("kp_file"))
    return [node.get("id") for node in graph.get("nodes", []) if node.get("id")]


def build_relation_context(curriculum: dict, course_name: str) -> dict:
    courses = course_name_map(curriculum)
    target_course = courses.get(course_name)
    if not target_course:
        for course in curriculum.get("courses", []):
            if course.get("name") == course_name:
                target_course = course
                break
    if not target_course:
        return {"course_name": course_name, "relations": []}

    target_id = target_course.get("id")
    relations = []
    for rel in curriculum.get("relations", []):
        source = courses.get(rel.get("source"))
        target = courses.get(rel.get("target"))
        if rel.get("source") == target_id or rel.get("target") == target_id:
            relations.append({
                "source": source.get("name") if source else rel.get("source"),
                "target": target.get("name") if target else rel.get("target"),
                "type": rel.get("type"),
                "reason": rel.get("reason"),
            })
    return {
        "course_id": target_id,
        "course_name": target_course.get("name"),
        "relations": relations,
        "prerequisites": [r["source"] for r in relations if r["target"] == target_course.get("name") and r["type"] == "prerequisite"],
        "successors": [r["target"] for r in relations if r["source"] == target_course.get("name")],
    }


def build_user_curriculum_graph(
    curriculum: dict,
    knowledge_base: dict | None,
    current_semester: int,
    manual_status: dict[str, str] | None = None,
) -> dict:
    kb = knowledge_base or {}
    manual_status = manual_status or {}
    courses = curriculum.get("courses", [])
    courses_by_id = {course.get("id"): course for course in courses if course.get("id")}

    mastery_by_id: dict[str, float] = {}
    course_metrics_by_id: dict[str, dict[str, float | int]] = {}
    evidence_by_id: dict[str, bool] = {}
    for course in courses:
        kps = get_course_kps(course)
        measured_scores = [float(kb.get(kp, 0) or 0) for kp in kps if kp in kb]
        all_scores = [float(kb.get(kp, 0) or 0) for kp in kps]
        evidence = bool(measured_scores)
        measured_mastery = round(sum(measured_scores) / len(measured_scores), 4) if measured_scores else 0
        overall_mastery = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0
        coverage_ratio = round(len(measured_scores) / len(kps), 4) if kps else 0
        mastery_by_id[course.get("id")] = measured_mastery
        course_metrics_by_id[course.get("id")] = {
            "measured_mastery": measured_mastery,
            "overall_mastery": overall_mastery,
            "coverage_ratio": coverage_ratio,
            "measured_kp_count": len(measured_scores),
            "total_kp_count": len(kps),
        }
        evidence_by_id[course.get("id")] = evidence

    def prereq_satisfied(course: dict) -> bool:
        prereqs = [
            rel.get("source")
            for rel in curriculum.get("relations", [])
            if rel.get("target") == course.get("id") and rel.get("type") == "prerequisite"
        ]
        if not prereqs:
            return True
        for prereq_id in prereqs:
            prereq = courses_by_id.get(prereq_id)
            if not prereq:
                continue
            if manual_status.get(prereq.get("name")) == "completed":
                continue
            if evidence_by_id.get(prereq_id) and mastery_by_id.get(prereq_id, 0) < 0.5:
                return False
            if semester_rank(prereq.get("semester")) < current_semester:
                continue
            if mastery_by_id.get(prereq_id, 0) >= 0.5:
                continue
            return False
        return True

    nodes = []
    for course in courses:
        course_id = course.get("id")
        name = course.get("name") or course_id
        sem_rank = semester_rank(course.get("semester"))
        metrics = course_metrics_by_id.get(course_id, {})
        mastery = float(metrics.get("measured_mastery", mastery_by_id.get(course_id, 0)) or 0)
        has_evidence = evidence_by_id.get(course_id, False)
        status = manual_status.get(name) or ""

        if status not in {"completed", "learning", "weak", "recommended"}:
            if sem_rank < current_semester:
                status = "weak" if has_evidence and mastery < 0.5 else "completed"
            elif sem_rank == current_semester:
                status = "learning"
            else:
                status = "available" if prereq_satisfied(course) else "locked"

        if status == "completed" and has_evidence and mastery < 0.5:
            status = "weak"

        nodes.append({
            "id": name,
            "course_id": course_id,
            "name": name,
            "semester": course.get("semester"),
            "category": course.get("category"),
            "module": course.get("module"),
            "credits": course.get("credits"),
            "status": status,
            "mastery": mastery,
            "measured_mastery": mastery,
            "overall_mastery": metrics.get("overall_mastery", mastery),
            "coverage_ratio": metrics.get("coverage_ratio", 0),
            "measured_kp_count": metrics.get("measured_kp_count", 0),
            "total_kp_count": metrics.get("total_kp_count", 0),
            "kp_file": course.get("kp_file"),
        })

    links = []
    for rel in curriculum.get("relations", []):
        source = courses_by_id.get(rel.get("source"))
        target = courses_by_id.get(rel.get("target"))
        if not source or not target:
            continue
        links.append({
            "source": source.get("name"),
            "target": target.get("name"),
            "source_course_id": source.get("id"),
            "target_course_id": target.get("id"),
            "type": rel.get("type"),
            "reason": rel.get("reason"),
        })

    return {
        "nodes": nodes,
        "links": links,
        "meta": {
            "major_id": curriculum.get("major_id"),
            "major_name": curriculum.get("major_name"),
            "version": curriculum.get("version"),
            "current_semester": current_semester,
        },
    }
