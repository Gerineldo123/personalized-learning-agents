import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.course_path import CoursePath
from models.quiz_record import QuizRecord
from models.resource import LearningResource
from models.student import StudentProfile
from services.curriculum_service import (
    build_relation_context,
    build_user_curriculum_graph,
    course_name_map,
    get_course_kp_graph,
    get_course_kps,
    infer_current_semester,
    load_curriculum_by_major,
    semester_rank,
)
from services.kp_service import match_kp
from services.profile_update_service import apply_path_step_completed
from services.rag_service import delete_rag_resources
from services.resource_lineage_service import set_resource_lineage

router = APIRouter(prefix="/api/path/course", tags=["课程学习路径"])

ALLOWED_RESOURCE_TYPES = {"article", "quiz", "mindmap", "code", "anime", "video", "ppt"}
VALID_STEP_STATUS = {"pending", "learning"}
PASSING_SCORE = 0.7


class CoursePathMetaUpdate(BaseModel):
    display_name: str | None = None
    note: str | None = None

COURSE_PATH_PROMPT = """你是学习路径规划智能体。请基于课程关系、知识点图谱和学生画像，生成可追踪的学习路径。
只能返回 JSON，不要输出 Markdown。

课程：{course_name}
课程关系：{relation_context}
可绑定知识点节点：{candidate_kps}
优先补弱知识点：{focus_kps}
学习目标：{goal}
薄弱点：{weak_points}
知识点掌握度：{knowledge_base}
已完成资源：{completed_resources}

要求：
1. 每个步骤必须围绕“可绑定知识点节点”中的真实知识点；不要编造知识点。
2. 如果存在先修短板，前置先修补弱步骤。
3. 每个步骤必须包含推荐资源类型，概念补弱使用 article/mindmap/quiz，实操步骤使用 article/code/quiz，拓展步骤使用 article/video。
4. 如果需要 PPT，只能把 ppt 写入 resource_types；系统会创建 AiPPT 分步会话，不要声称已经生成 PPT 文件。
5. 每个步骤必须有验收标准 completion_rule。

JSON 格式：
{{
  "steps": [
    {{
      "order": 1,
      "title": "步骤标题",
      "description": "学习任务说明",
      "knowledge_points": ["必须精确匹配可绑定知识点节点"],
      "relation_context": "为什么安排在这里",
      "resource_types": ["article", "mindmap", "quiz"],
      "duration_estimate": "45分钟",
      "resource_queries": ["检索或生成资源的关键词"],
      "checkpoint": "阶段检查",
      "completion_rule": "完成此步骤的可验证标准"
    }}
  ]
}}
"""


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).replace("，", ",").split(",") if item.strip()]


def _extract_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _step_kps(step: dict) -> list[str]:
    return [str(kp).strip() for kp in _as_list(step.get("knowledge_points")) if str(kp).strip()]


def _covered_kps(steps: list[dict]) -> list[str]:
    return list(
        dict.fromkeys(
            [
                kp
                for step in steps
                if isinstance(step, dict)
                for kp in _step_kps(step)
            ]
        )
    )


def _course_kp_total(course_name: str) -> int:
    graph = get_course_kp_graph(course_name, "")
    return len([node for node in graph.get("nodes", []) if node.get("id")])


def _path_scope_from_steps(course_name: str, steps: list[dict]) -> tuple[str, float, list[str]]:
    covered = _covered_kps(steps)
    explicit_scope = next(
        (str(step.get("path_scope")) for step in steps if isinstance(step, dict) and step.get("path_scope")),
        "",
    )
    total = _course_kp_total(course_name)
    coverage_ratio = round(len(covered) / total, 4) if total else (1.0 if covered else 0.0)
    if explicit_scope in {"course", "knowledge_point", "weak_point"}:
        scope = explicit_scope
    elif len(covered) <= 2 or (total and coverage_ratio < 0.35):
        scope = "knowledge_point"
    else:
        scope = "course"
    return scope, coverage_ratio, covered


def _step_with_defaults(step: dict) -> dict:
    normalized = dict(step)
    normalized.setdefault("status", "pending")
    normalized.setdefault("mastery_status", "unverified")
    normalized.setdefault("passing_score", PASSING_SCORE)
    # 深拷贝所有 list/dict 字段，防止多步骤共享同一个对象引用
    normalized["evidence"] = dict(normalized.get("evidence") or {})
    normalized.setdefault("check_resource_id", None)
    normalized["resource_ids"] = list(normalized.get("resource_ids") or [])
    normalized["resources"] = [dict(r) for r in (normalized.get("resources") or []) if isinstance(r, dict)]
    normalized["ppt_sessions"] = [dict(s) for s in (normalized.get("ppt_sessions") or []) if isinstance(s, dict)]
    normalized["resource_failures"] = [dict(f) for f in (normalized.get("resource_failures") or []) if isinstance(f, dict)]
    normalized["remediation_attempts"] = [dict(a) for a in (normalized.get("remediation_attempts") or []) if isinstance(a, dict)]
    return normalized


def _recalculate_path_progress(path: CoursePath, steps: list[dict]) -> None:
    total = len(steps)
    verified = sum(
        1
        for step in steps
        if isinstance(step, dict)
        and step.get("status") == "done"
        and step.get("mastery_status") == "verified"
    )
    learning = sum(
        1
        for step in steps
        if isinstance(step, dict) and step.get("status") == "learning"
    )
    path.total_steps = total
    path.done_steps = verified
    path.progress = round((verified + learning * 0.5) / total * 100, 1) if total else 0
    path.status = "completed" if total and verified == total else "active"
    path.steps = steps


def _path_payload(path: CoursePath, found: bool = True) -> dict:
    steps = [_step_with_defaults(step) for step in (path.steps or []) if isinstance(step, dict)]
    path_scope, coverage_ratio, covered = _path_scope_from_steps(path.course_name, steps)
    next_step = next((step for step in steps if step.get("status") != "done"), None)
    learning_steps = sum(1 for step in steps if step.get("status") == "learning")
    return {
        "found": found,
        "id": path.id,
        "course_name": path.course_name,
        "display_name": getattr(path, "display_name", None) or path.course_name,
        "steps": steps,
        "total_steps": path.total_steps,
        "done_steps": path.done_steps,
        "learning_steps": learning_steps,
        "progress": path.progress,
        "status": path.status,
        "is_archived": bool(getattr(path, "is_archived", False) or path.status == "archived"),
        "archived_at": path.archived_at.isoformat() if getattr(path, "archived_at", None) else None,
        "path_scope": path_scope,
        "coverage_ratio": coverage_ratio,
        "covered_knowledge_points": covered,
        "knowledge_points": covered,
        "next_step": {
            "order": next_step.get("order"),
            "title": next_step.get("title"),
            "knowledge_points": _as_list(next_step.get("knowledge_points")),
        }
        if isinstance(next_step, dict)
        else None,
        "created_at": path.created_at.isoformat() if path.created_at else None,
    }


def _resource_types_from_text(text: str) -> list[str]:
    content = text or ""
    if any(key in content for key in ["实操", "实践", "代码", "实验", "案例", "动画", "可视化"]):
        return ["article", "code", "quiz"]
    if any(key in content for key in ["拓展", "预习", "后继", "视频"]):
        return ["article", "video"]
    return ["article", "mindmap", "quiz"]


def _normalize_resource_types(value, fallback_text: str) -> list[str]:
    raw = [str(item).strip() for item in _as_list(value) if str(item).strip()]
    normalized = [item for item in raw if item in ALLOWED_RESOURCE_TYPES]
    if not normalized:
        normalized = _resource_types_from_text(fallback_text)
    return list(dict.fromkeys(normalized))


def _normalize_step(
    step: dict,
    order: int,
    course_name: str,
    candidate_kps: list[str],
    focus_kps: list[str],
    relation_context: dict,
    path_scope: str,
) -> dict:
    title = str(step.get("title") or f"步骤{order}").strip()[:32]
    description = str(step.get("description") or "").strip()
    checkpoint = str(step.get("checkpoint") or step.get("completion_rule") or "完成检查题并能解释关键概念").strip()
    text = " ".join([title, description, checkpoint, json.dumps(step, ensure_ascii=False)])

    raw_kps = [str(kp).strip() for kp in _as_list(step.get("knowledge_points")) if str(kp).strip()]
    if candidate_kps:
        allowed = set(candidate_kps)
        knowledge_points = [kp for kp in raw_kps if kp in allowed]
        if not knowledge_points:
            knowledge_points = [kp for kp in match_kp(text) if kp in allowed]
        if not knowledge_points:
            knowledge_points = [kp for kp in focus_kps if kp in allowed][:2] or candidate_kps[:1]
    else:
        knowledge_points = []

    relation_note = str(step.get("relation_context") or "").strip()
    if not relation_note:
        prereqs = "、".join(relation_context.get("prerequisites") or [])
        relation_note = f"先修关联：{prereqs}" if prereqs and order == 1 else "基于当前薄弱知识点安排"

    return {
        "order": int(step.get("order") or order),
        "title": title,
        "description": description or f"围绕“{'、'.join(knowledge_points) or course_name}”进行针对性学习。",
        "course_name": course_name,
        "knowledge_points": list(dict.fromkeys(knowledge_points)),
        "relation_context": relation_note,
        "resource_types": _normalize_resource_types(step.get("resource_types"), text),
        "duration_estimate": str(step.get("duration_estimate") or "45分钟"),
        "resource_queries": _as_list(step.get("resource_queries"))[:3] or [course_name, *knowledge_points[:2]],
        "checkpoint": checkpoint,
        "completion_rule": str(step.get("completion_rule") or checkpoint),
        "status": "pending",
        "mastery_status": "unverified",
        "passing_score": PASSING_SCORE,
        "check_resource_id": None,
        "evidence": {},
        "completed_at": None,
        "resource_ids": [],
        "resources": [],
        "ppt_sessions": [],
        "resource_failures": [],
        "path_scope": path_scope,
    }


def _fallback_steps(
    course_name: str,
    focus_kps: list[str],
    candidate_kps: list[str],
    relation_context: dict,
    path_scope: str,
) -> list[dict]:
    kps = focus_kps or candidate_kps[:4]
    raw_steps: list[dict] = []
    if relation_context.get("prerequisites"):
        raw_steps.append(
            {
                "title": "先修补弱",
                "description": f"先回补 {course_name} 所需的关键先修基础。",
                "knowledge_points": kps[:1],
                "resource_types": ["article", "mindmap", "quiz"],
                "checkpoint": "能说清本课程所需的先修概念并完成基础题。",
            }
        )
    for kp in kps[:4]:
        raw_steps.append(
            {
                "title": kp[:16],
                "description": f"围绕“{kp}”梳理概念、例题和常见错误。",
                "knowledge_points": [kp],
                "resource_types": ["article", "mindmap", "quiz"],
                "checkpoint": f"能独立完成一道关于“{kp}”的基础题并解释原因。",
            }
        )
    raw_steps.append(
        {
            "title": "综合演练",
            "description": "整合本路径知识点完成综合练习。",
            "knowledge_points": kps[:3],
            "resource_types": ["article", "code", "quiz"] if kps else ["article", "quiz"],
            "checkpoint": "能完成综合练习并复盘错误原因。",
        }
    )
    return [
        _normalize_step(step, index + 1, course_name, candidate_kps, focus_kps, relation_context, path_scope)
        for index, step in enumerate(raw_steps[:8])
    ]


def _course_path_context(profile: StudentProfile | None, course_name: str, knowledge_points: str | None) -> dict:
    major = profile.major if profile else ""
    curriculum = load_curriculum_by_major(major or "")
    course = course_name_map(curriculum).get(course_name)
    relation_context = build_relation_context(curriculum, course_name)
    graph = get_course_kp_graph(course_name, major or "")
    candidate_kps = [node.get("id") for node in graph.get("nodes", []) if node.get("id")]
    explicit_kps = _parse_csv(knowledge_points)
    weak_points = set(_as_list(profile.weak_points) if profile else [])
    kb = (profile.knowledge_base or {}) if profile else {}
    low_mastery = [
        kp
        for kp in candidate_kps
        if kp in weak_points or float(kb.get(kp, 0) or 0) < 0.55
    ]
    focus_kps = [kp for kp in explicit_kps if not candidate_kps or kp in candidate_kps]
    if not focus_kps:
        focus_kps = low_mastery[:6]
    if not focus_kps and candidate_kps:
        focus_kps = candidate_kps[:4]
    return {
        "course_in_curriculum": bool(course),
        "course_has_kp_file": bool(course and course.get("kp_file")),
        "relation_context": relation_context,
        "candidate_kps": candidate_kps,
        "focus_kps": list(dict.fromkeys(focus_kps)),
        "knowledge_base": kb,
        "explicit_kps": focus_kps,
    }


def _completed_resource_summary(db, user_id: str, course_name: str) -> list[dict]:
    items = (
        db.query(LearningResource)
        .filter(
            LearningResource.user_id == user_id,
            LearningResource.course_name == course_name,
            LearningResource.learning_status == "completed",
        )
        .order_by(LearningResource.completed_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id": item.id,
            "title": item.title,
            "type": item.resource_type,
            "knowledge_points": item.knowledge_points or [],
        }
        for item in items
    ]


def _find_step(path: CoursePath, step_order: int) -> tuple[list[dict], dict | None]:
    steps = [_step_with_defaults(step) for step in (path.steps or []) if isinstance(step, dict)]
    target = next((step for step in steps if step.get("order") == step_order), None)
    return steps, target


def _resource_payload(resource: LearningResource | None) -> dict | None:
    if not resource:
        return None
    return {
        "id": resource.id,
        "resource_type": resource.resource_type,
        "title": resource.title,
        "content": resource.content,
        "course_name": resource.course_name,
        "knowledge_points": resource.knowledge_points or [],
    }


def _validate_check_content(content: dict) -> tuple[bool, str]:
    questions = content.get("questions")
    if not isinstance(questions, list) or not questions:
        return False, "生成结果缺少可作答题目"
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            return False, f"第 {index} 题格式不正确"
        if not str(question.get("question") or question.get("title") or "").strip():
            return False, f"第 {index} 题缺少题干"
        if not str(question.get("answer") or "").strip():
            return False, f"第 {index} 题缺少标准答案"
        question_type = str(question.get("type") or "single_choice")
        if question_type == "single_choice":
            options = question.get("options")
            if not isinstance(options, list) or len(options) != 4:
                return False, f"第 {index} 题是选择题但选项不是 4 个"
            for option in options:
                if isinstance(option, dict):
                    option_text = str(option.get("text") or option.get("label") or "").strip()
                else:
                    option_text = str(option or "").strip()
                if not option_text:
                    return False, f"第 {index} 题存在空选项"
    return True, ""


def _discard_invalid_check_resource(db, resource: LearningResource | None) -> None:
    if not resource or not resource.id:
        return
    resource_id = int(resource.id)
    db.delete(resource)
    db.commit()
    delete_rag_resources([resource_id])


def _fallback_check_questions(path: CoursePath, step: dict, passing_score: float, reason: str = "") -> dict:
    step_kps = _step_kps(step)
    focus_points = step_kps or [str(step.get("title") or path.course_name)]
    questions = []
    for index, kp in enumerate(focus_points[:5], start=1):
        questions.append(
            {
                "id": index,
                "type": "single_choice",
                "course_name": path.course_name,
                "knowledge_points": [kp] if kp else [],
                "question": f"完成“{step.get('title')}”后，针对“{kp}”最合理的验收表现是哪一项？",
                "options": [
                    {"key": "A", "text": "能说明核心概念、适用条件，并完成一个对应例题或反例分析"},
                    {"key": "B", "text": "只记住这个知识点名称，但不能解释其含义"},
                    {"key": "C", "text": "只知道它属于本课程，但无法完成相关题目"},
                    {"key": "D", "text": "认为它与本步骤和课程目标无关"},
                ],
                "answer": "A",
                "explanation": f"本步骤验收重点不是简单打卡，而是能围绕“{kp}”解释概念、判断适用条件，并完成对应任务。",
                "difficulty": "基础",
            }
        )
    return {
        "title": f"{path.course_name} · {step.get('title')} 检查题",
        "questions": questions,
        "path_check": {
            "path_id": path.id,
            "step_order": step.get("order"),
            "passing_score": passing_score,
            "fallback": True,
            "fallback_reason": reason[:300] if reason else "",
        },
    }


def _create_fallback_check_resource(db, path: CoursePath, step: dict, passing_score: float, reason: str = "") -> LearningResource:
    step_kps = _step_kps(step)
    content = _fallback_check_questions(path, step, passing_score, reason)
    resource = LearningResource(
        user_id=path.user_id,
        resource_type="quiz",
        title=content["title"],
        content=content,
        tags=["quiz", path.course_name, *step_kps],
        course_name=path.course_name,
        knowledge_points=step_kps,
        kp_weights={kp: round(1 / max(len(step_kps), 1), 4) for kp in step_kps},
        tag_confidence=0.6,
    )
    db.add(resource)
    db.flush()
    return resource


def _question_kps(question: dict, resource: LearningResource | None) -> list[str]:
    if isinstance(question.get("knowledge_points"), list) and question.get("knowledge_points"):
        return [str(kp) for kp in question.get("knowledge_points") if kp]
    if resource and isinstance(resource.knowledge_points, list):
        return [str(kp) for kp in resource.knowledge_points if kp]
    return []


def _wrong_knowledge_points(resource: LearningResource | None, record: QuizRecord | None) -> list[str]:
    if not resource or not record or not isinstance(resource.content, dict):
        return []
    questions = resource.content.get("questions") or []
    answers = record.answers or {}
    wrong: list[str] = []
    for question in questions:
        qid = question.get("id")
        if qid is None:
            continue
        user_ans = str(answers.get(str(qid), answers.get(qid, "")))
        correct_ans = str(question.get("answer", ""))
        q_type = question.get("type", "single_choice")
        if q_type == "fill_blank":
            is_wrong = user_ans.strip().lower() != correct_ans.strip().lower()
        elif q_type == "coding":
            try:
                is_wrong = float(user_ans) < 1.0
            except ValueError:
                is_wrong = True
        else:
            is_wrong = user_ans != correct_ans
        if is_wrong:
            wrong.extend(_question_kps(question, resource))
    return list(dict.fromkeys([kp for kp in wrong if kp]))


def _answer_value(answers: dict, qid) -> str:
    if not isinstance(answers, dict):
        return ""
    return str(answers.get(str(qid), answers.get(qid, "")))


def _is_wrong_question(question: dict, user_ans: str) -> bool:
    correct_ans = str(question.get("answer", ""))
    q_type = question.get("type", "single_choice")
    if q_type == "fill_blank":
        return user_ans.strip().lower() != correct_ans.strip().lower()
    if q_type == "coding":
        try:
            return float(user_ans) < 1.0
        except ValueError:
            return True
    return user_ans != correct_ans


def _wrong_question_items(resource: LearningResource | None, record: QuizRecord | None) -> list[dict]:
    if not resource or not record or not isinstance(resource.content, dict):
        return []
    questions = resource.content.get("questions") or []
    answers = record.answers or {}
    items: list[dict] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        qid = question.get("id")
        if qid is None:
            continue
        user_ans = _answer_value(answers, qid)
        if not _is_wrong_question(question, user_ans):
            continue
        items.append(
            {
                "question_id": qid,
                "question": question.get("question") or question.get("title") or "",
                "type": question.get("type", "single_choice"),
                "knowledge_points": _question_kps(question, resource),
                "user_answer": user_ans,
                "correct_answer": question.get("answer", ""),
                "explanation": question.get("explanation") or question.get("analysis") or "",
            }
        )
    return items


def _latest_step_check_record(db, path: CoursePath, step: dict) -> tuple[LearningResource | None, QuizRecord | None]:
    check_resource_id = step.get("check_resource_id")
    if not check_resource_id:
        return None, None
    resource = db.query(LearningResource).get(int(check_resource_id))
    record = (
        db.query(QuizRecord)
        .filter(
            QuizRecord.user_id == path.user_id,
            QuizRecord.resource_id == int(check_resource_id),
        )
        .order_by(QuizRecord.created_at.desc())
        .first()
    )
    return resource, record


def _remediation_resource_types(step: dict, wrong_kps: list[str]) -> list[str]:
    text = " ".join(
        [
            str(step.get("title") or ""),
            str(step.get("description") or ""),
            " ".join(wrong_kps),
        ]
    )
    types = ["article", "mindmap", "quiz"]
    if any(key in text for key in ["代码", "编程", "实操", "实践", "动画", "可视化"]):
        types.insert(2, "code")
    return list(dict.fromkeys(types))


def _build_remediation_attempt(
    step: dict,
    record: QuizRecord,
    resource: LearningResource | None,
    wrong_kps: list[str],
    wrong_questions: list[dict],
    attempt_no: int,
) -> dict:
    score = float(record.score or 0)
    passing_score = float(step.get("passing_score") or PASSING_SCORE)
    title = step.get("title") or f"步骤 {step.get('order')}"
    diagnosis = (
        f"第 {attempt_no} 轮补弱：最近检查题得分 {round(score * 100)}%，"
        f"未达到 {round(passing_score * 100)}% 通过阈值。"
        f"优先复习 {', '.join(wrong_kps[:5]) if wrong_kps else '本步骤绑定知识点'}，"
        "完成补弱资源后重新生成检查题验证。"
    )
    return {
        "attempt_no": attempt_no,
        "step_title": title,
        "failed_quiz_record_id": record.id,
        "failed_check_resource_id": int(resource.id) if resource else step.get("check_resource_id"),
        "failed_score": round(score, 4),
        "passing_score": passing_score,
        "weak_knowledge_points": wrong_kps,
        "wrong_questions": wrong_questions[:10],
        "diagnosis": diagnosis,
        "resource_ids": [],
        "resources": [],
        "resource_failures": [],
        "new_check_resource_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/recommend")
def recommend_courses(user_id: str, limit: int = 6):
    """
    基于用户画像推荐适合现在开始学的课程。

    优先级：
      1. learning  — 当前学期课程（正在学）
      2. weak      — 已学过但掌握度不足，需要补强
      3. available — 先修已满足、可以开始的课程
    每类内部按掌握度升序（掌握度越低越优先推荐）。
    已有 active/completed 路径的课程不重复推荐。
    """
    db = SessionLocal()
    try:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        if not profile:
            return {"items": []}

        major = profile.major or ""
        knowledge_base = profile.knowledge_base or {}
        current_semester = infer_current_semester(
            grade=profile.grade or "",
            current_semester=profile.current_semester,
        )

        curriculum = load_curriculum_by_major(major)
        graph = build_user_curriculum_graph(
            curriculum=curriculum,
            knowledge_base=knowledge_base,
            current_semester=current_semester,
        )

        # 已有路径的课程名称集合（不重复推荐）
        existing_paths = (
            db.query(CoursePath.course_name)
            .filter(
                CoursePath.user_id == user_id,
                CoursePath.status.in_(["active", "completed"]),
            )
            .all()
        )
        existing_courses = {row.course_name for row in existing_paths}

        PRIORITY = {"learning": 0, "weak": 1, "available": 2}
        LABEL_MAP = {
            "learning": "当前学期",
            "weak": "需要补强",
            "available": "可以开始",
        }
        REASON_MAP = {
            "learning": "该课程处于你当前学期，是现阶段重点学习内容。",
            "weak": "你已学过该课程，但部分知识点掌握度不足，建议针对性补强。",
            "available": "你已具备先修知识，可以提前开始学习。",
        }

        candidates = []
        for node in graph.get("nodes", []):
            status = node.get("status", "")
            name = node.get("name", "")
            if status not in PRIORITY:
                continue
            if name in existing_courses:
                continue
            if not name:
                continue
            # 只推荐有知识点图谱的课程（生成的路径才能绑定真实知识点）
            kp_file = node.get("kp_file")
            if not kp_file:
                continue
            mastery = float(node.get("mastery") or 0)
            sem = node.get("semester")
            candidates.append({
                "course_name": name,
                "status": status,
                "status_label": LABEL_MAP[status],
                "mastery": round(mastery, 4),
                "mastery_percent": round(mastery * 100),
                "semester": sem,
                "category": node.get("category") or "",
                "module": node.get("module") or "",
                "has_kp_graph": True,
                "reason": REASON_MAP[status],
                "priority": PRIORITY[status],
            })

        # 排序：优先级 → 掌握度升序 → 学期升序
        candidates.sort(key=lambda c: (c["priority"], c["mastery"], semester_rank(c["semester"])))

        return {"items": candidates[:limit], "current_semester": current_semester}
    finally:
        db.close()


@router.get("/list")
def list_course_paths(user_id: str, include_archived: bool = Query(False)):
    db = SessionLocal()
    try:
        query = db.query(CoursePath).filter(CoursePath.user_id == user_id)
        if include_archived:
            query = query.filter(CoursePath.status.in_(["active", "completed", "archived"]))
        else:
            query = query.filter(
                CoursePath.status.in_(["active", "completed"]),
                (CoursePath.is_archived == False) | (CoursePath.is_archived.is_(None)),  # noqa: E712
            )
        paths = query.order_by(CoursePath.created_at.desc()).all()
        return {"items": [_path_payload(path) for path in paths]}
    finally:
        db.close()


@router.get("")
def get_course_path(user_id: str, course_name: str | None = None):
    db = SessionLocal()
    try:
        query = db.query(CoursePath).filter(CoursePath.user_id == user_id)
        if course_name:
            query = query.filter(CoursePath.course_name == course_name)
        query = query.filter(
            CoursePath.status.in_(["active", "completed"]),
            (CoursePath.is_archived == False) | (CoursePath.is_archived.is_(None)),  # noqa: E712
        )
        path = query.order_by(CoursePath.created_at.desc()).first()
        if not path:
            return {
                "found": False,
                "course_name": course_name,
                "steps": [],
                "total_steps": 0,
                "done_steps": 0,
                "learning_steps": 0,
                "progress": 0,
                "status": "empty",
                "path_scope": "course",
                "coverage_ratio": 0,
                "covered_knowledge_points": [],
                "knowledge_points": [],
                "next_step": None,
            }
        return _path_payload(path)
    finally:
        db.close()


@router.patch("/{path_id}/meta")
def update_course_path_meta(path_id: int, payload: CoursePathMetaUpdate):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            raise HTTPException(status_code=404, detail="学习路径不存在")
        display_name = (payload.display_name or "").strip()
        if not display_name:
            raise HTTPException(status_code=400, detail="路径名称不能为空")
        if len(display_name) > 80:
            raise HTTPException(status_code=400, detail="路径名称不能超过 80 个字符")
        path.display_name = display_name
        path.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(path)
        return {"ok": True, **_path_payload(path)}
    finally:
        db.close()


@router.patch("/{path_id}/archive")
def archive_course_path(path_id: int):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            raise HTTPException(status_code=404, detail="学习路径不存在")
        path.status = "archived"
        path.is_archived = True
        path.archived_at = datetime.now(timezone.utc)
        path.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(path)
        return {"ok": True, **_path_payload(path)}
    finally:
        db.close()


@router.delete("/{path_id}")
def delete_course_path(path_id: int):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            raise HTTPException(status_code=404, detail="学习路径不存在")
        db.delete(path)
        db.commit()
        return {"ok": True, "deleted_path_id": path_id}
    finally:
        db.close()


@router.patch("/{path_id}/step/{step_order}")
def update_step_status(path_id: int, step_order: int, done: bool | None = None, status: str | None = None):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            return {"ok": False, "error": "路径不存在"}

        steps, current_step = _find_step(path, step_order)
        if not current_step:
            return {"ok": False, "error": "步骤不存在"}

        next_status = status
        if next_status is None and done is not None:
            next_status = "learning" if done else "pending"
        if next_status not in VALID_STEP_STATUS:
            return {"ok": False, "error": "手动操作只能设置为 pending 或 learning；完成状态需要通过检查题验收"}

        current_step["status"] = next_status
        if next_status == "learning":
            evidence = dict(current_step.get("evidence") or {})
            evidence["learned_at"] = datetime.now(timezone.utc).isoformat()
            current_step["evidence"] = evidence
        else:
            current_step["mastery_status"] = "unverified"
            current_step["completed_at"] = None

        _recalculate_path_progress(path, steps)
        db.commit()
        db.refresh(path)
        return {"ok": True, **_path_payload(path), "updated_step": current_step}
    finally:
        db.close()


@router.post("/generate")
async def generate_course_path(
    user_id: str,
    course_name: str,
    knowledge_points: str | None = None,
    path_scope: str | None = None,
):
    db = SessionLocal()
    try:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        context = _course_path_context(profile, course_name, knowledge_points)
        relation_context = context["relation_context"]
        candidate_kps = context["candidate_kps"]
        focus_kps = context["focus_kps"]
        knowledge_base = context["knowledge_base"]
        if not context.get("course_in_curriculum"):
            raise HTTPException(status_code=400, detail="学习路径只支持培养方案中的课程，请改用专项资源包进行拓展学习")
        if not context.get("course_has_kp_file") or len(candidate_kps) < 3:
            raise HTTPException(status_code=400, detail="该课程未配置足够的课内知识点图谱，不能生成课程学习路径")
        if knowledge_points and len(focus_kps) < 3:
            raise HTTPException(status_code=400, detail="单个知识点不生成学习路径，请改用知识点专项资源包")
        chosen_scope = "course"

        completed_resources = _completed_resource_summary(db, user_id, course_name)
        raw_steps: list[dict] = []
        generation_error = None
        try:
            resp = await chat_completion(
                [
                    {
                        "role": "user",
                        "content": COURSE_PATH_PROMPT.format(
                            course_name=course_name,
                            relation_context=json.dumps(relation_context, ensure_ascii=False),
                            candidate_kps=json.dumps(candidate_kps[:80], ensure_ascii=False),
                            focus_kps=json.dumps(focus_kps, ensure_ascii=False),
                            goal=getattr(profile, "learning_goal", "") or "",
                            weak_points=json.dumps(_as_list(profile.weak_points) if profile else [], ensure_ascii=False),
                            knowledge_base=json.dumps(knowledge_base, ensure_ascii=False),
                            completed_resources=json.dumps(completed_resources, ensure_ascii=False),
                        ),
                    }
                ],
                temperature=0.4,
            )
            raw = resp.choices[0].message.content
            data = _extract_json(raw)
            raw_steps = [step for step in _as_list(data.get("steps")) if isinstance(step, dict)]
        except Exception as exc:
            generation_error = str(exc)

        steps = [
            _normalize_step(step, index + 1, course_name, candidate_kps, focus_kps, relation_context, chosen_scope)
            for index, step in enumerate(raw_steps[:8])
        ]
        steps = [step for step in steps if step.get("knowledge_points") or not candidate_kps]
        if not steps:
            steps = _fallback_steps(course_name, focus_kps, candidate_kps, relation_context, chosen_scope)
        covered = list(dict.fromkeys(kp for step in steps for kp in _step_kps(step)))
        if len(covered) < 3:
            steps = _fallback_steps(course_name, candidate_kps[:4], candidate_kps, relation_context, chosen_scope)
            covered = list(dict.fromkeys(kp for step in steps for kp in _step_kps(step)))
        if len(covered) < 3:
            raise HTTPException(status_code=400, detail="生成路径覆盖知识点不足，请先完善课程知识图谱")

        for old_path in (
            db.query(CoursePath)
            .filter(
                CoursePath.user_id == user_id,
                CoursePath.course_name == course_name,
                CoursePath.status == "active",
            )
            .all()
        ):
            old_path.status = "archived"
            old_path.is_archived = True
            old_path.archived_at = datetime.now(timezone.utc)
            old_path.updated_at = datetime.now(timezone.utc)

        if generation_error and steps:
            steps[0]["generation_note"] = f"LLM 生成失败，已使用图谱规则兜底：{generation_error[:120]}"

        path = CoursePath(
            user_id=user_id,
            course_name=course_name,
            steps=steps,
            total_steps=len(steps),
            done_steps=0,
            progress=0,
            status="active",
        )
        db.add(path)
        db.commit()
        db.refresh(path)
        return {"ok": True, **_path_payload(path)}
    finally:
        db.close()


async def _generate_step_resource(user_id: str, path: CoursePath, step: dict, resource_type: str) -> AgentState:
    step_kps = _step_kps(step)
    topic = "；".join(
        [
            f"课程：{path.course_name}",
            f"路径步骤：{step.get('title')}",
            f"学习任务：{step.get('description')}",
            f"知识点：{'、'.join(step_kps)}",
            f"验收标准：{step.get('completion_rule') or step.get('checkpoint')}",
        ]
    )
    state = AgentState(
        user_id=user_id,
        user_message=topic,
        resource_type=resource_type,
        course_name=path.course_name,
        knowledge_points=step_kps,
        question_count=5,
        difficulty="中等",
        question_types="single_choice",
    )
    if resource_type == "mindmap":
        return await MindMapAgent().process(state)
    if resource_type == "video":
        return await VideoAgent().process(state)
    return await ContentGenAgent().process(state)


@router.post("/{path_id}/step/{step_order}/check")
async def create_step_check(path_id: int, step_order: int, force: bool = Query(False)):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            return {"ok": False, "error": "路径不存在"}
        steps, step = _find_step(path, step_order)
        if not step:
            return {"ok": False, "error": "步骤不存在"}

        existing_id = step.get("check_resource_id")
        if existing_id and not force:
            existing = db.query(LearningResource).get(existing_id)
            if existing:
                existing_content = existing.content if isinstance(existing.content, dict) else {}
                existing_path_check = existing_content.get("path_check") if isinstance(existing_content.get("path_check"), dict) else {}
                if not existing_path_check.get("fallback"):
                    return {"ok": True, "resource": _resource_payload(existing), "step": step, **_path_payload(path)}

        step_kps = _step_kps(step)
        passing_score = float(step.get("passing_score") or PASSING_SCORE)
        try:
            state = await _generate_step_resource(path.user_id, path, {**step, "resource_types": ["quiz"]}, "quiz")
            rid = state.get("resource_db_id")
            if not rid:
                return {"ok": False, "error": "检查题生成失败：Agent 未返回资源 ID", "step": step, **_path_payload(path)}
            else:
                resource = db.query(LearningResource).get(rid)
                if not resource:
                    return {"ok": False, "error": f"检查题生成失败：资源 {rid} 不存在", "step": step, **_path_payload(path)}
        except Exception as exc:
            return {"ok": False, "error": f"检查题生成失败：{str(exc)[:300]}", "step": step, **_path_payload(path)}

        if resource:
            content = dict(resource.content) if isinstance(resource.content, dict) else {"text": resource.content}
            questions = content.get("questions") or []
            for question in questions:
                if not question.get("knowledge_points"):
                    question["knowledge_points"] = step_kps
                question["course_name"] = path.course_name
            content["questions"] = questions
            content["path_check"] = {
                "path_id": path.id,
                "step_order": step_order,
                "passing_score": passing_score,
            }
            valid_check, invalid_reason = _validate_check_content(content)
            if not valid_check:
                _discard_invalid_check_resource(db, resource)
                return {"ok": False, "error": f"检查题生成失败：{invalid_reason}", "step": step, **_path_payload(path)}
            resource.title = f"{path.course_name} · {step.get('title')} 检查题"
            resource.content = content
            resource.course_name = path.course_name
            resource.knowledge_points = step_kps
            resource.kp_weights = {kp: round(1 / max(len(step_kps), 1), 4) for kp in step_kps}
            set_resource_lineage(
                resource,
                relation_type="path_check",
                group_id=f"path:{path.id}:step:{step_order}",
                group_type="path_step",
                source_module="learning_path",
                source_context={
                    "path_id": path.id,
                    "course_name": path.course_name,
                    "step_order": step_order,
                    "step_title": step.get("title"),
                    "passing_score": passing_score,
                },
            )

        step["check_resource_id"] = int(rid)
        step["passing_score"] = passing_score
        step["mastery_status"] = "unverified"
        step["resource_ids"] = list(dict.fromkeys([*_as_list(step.get("resource_ids")), int(rid)]))
        resources = [item for item in _as_list(step.get("resources")) if isinstance(item, dict)]
        if not any(int(item.get("id", 0) or 0) == int(rid) for item in resources):
            resources.append({"id": int(rid), "title": resource.title if resource else "步骤检查题", "type": "quiz"})
        step["resources"] = resources
        if force:
            attempts = [item for item in _as_list(step.get("remediation_attempts")) if isinstance(item, dict)]
            if attempts:
                attempts[-1]["new_check_resource_id"] = int(rid)
                attempts[-1]["new_check_created_at"] = datetime.now(timezone.utc).isoformat()
                step["remediation_attempts"] = attempts

        _recalculate_path_progress(path, steps)
        db.commit()
        db.refresh(path)
        return {"ok": True, "resource": _resource_payload(resource), "step": step, **_path_payload(path)}
    finally:
        db.close()


@router.post("/{path_id}/step/{step_order}/verify")
def verify_step_check(path_id: int, step_order: int):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            return {"ok": False, "error": "路径不存在"}
        steps, step = _find_step(path, step_order)
        if not step:
            return {"ok": False, "error": "步骤不存在"}

        check_resource_id = step.get("check_resource_id")
        if not check_resource_id:
            return {"ok": True, "passed": False, "score": None, "step": step, "message": "请先生成步骤检查题"}

        record = (
            db.query(QuizRecord)
            .filter(
                QuizRecord.user_id == path.user_id,
                QuizRecord.resource_id == int(check_resource_id),
            )
            .order_by(QuizRecord.created_at.desc())
            .first()
        )
        resource = db.query(LearningResource).get(check_resource_id)
        if not record:
            return {
                "ok": True,
                "passed": False,
                "score": None,
                "passing_score": float(step.get("passing_score") or PASSING_SCORE),
                "step": step,
                "weak_knowledge_points": [],
                "message": "请先完成检查题提交",
            }

        score = float(record.score or 0)
        passing_score = float(step.get("passing_score") or PASSING_SCORE)
        passed = score >= passing_score
        evidence = dict(step.get("evidence") or {})
        evidence.update(
            {
                "quiz_record_id": record.id,
                "score": round(score, 4),
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        step["evidence"] = evidence
        if passed:
            step["status"] = "done"
            step["mastery_status"] = "verified"
            step["completed_at"] = evidence["verified_at"]
        else:
            step["status"] = "learning"
            step["mastery_status"] = "failed"
            step["completed_at"] = None

        weak_kps = _wrong_knowledge_points(resource, record) or ([] if passed else _step_kps(step))
        _recalculate_path_progress(path, steps)
        db.commit()

        if passed:
            apply_path_step_completed(
                db=db,
                user_id=path.user_id,
                course_name=path.course_name,
                step_title=str(step.get("title") or f"步骤{step_order}"),
                matched_kps=_step_kps(step),
                course_completed=path.status == "completed",
            )

        db.refresh(path)
        return {
            "ok": True,
            "passed": passed,
            "score": round(score, 4),
            "passing_score": passing_score,
            "step": step,
            "weak_knowledge_points": weak_kps,
            **_path_payload(path),
        }
    finally:
        db.close()


@router.post("/{path_id}/step/{step_order}/remediate")
async def remediate_step(path_id: int, step_order: int, generate_resources: bool = Query(False)):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            return {"ok": False, "error": "学习路径不存在"}
        steps, step = _find_step(path, step_order)
        if not step:
            return {"ok": False, "error": "步骤不存在"}

        resource, record = _latest_step_check_record(db, path, step)
        if not record:
            return {
                "ok": False,
                "error": "请先完成并提交本步骤检查题",
                "step": step,
                **_path_payload(path),
            }

        score = float(record.score or 0)
        passing_score = float(step.get("passing_score") or PASSING_SCORE)
        if score >= passing_score:
            return {
                "ok": True,
                "passed": True,
                "message": "最近一次检查已通过，无需继续补弱",
                "score": round(score, 4),
                "passing_score": passing_score,
                "step": step,
                **_path_payload(path),
            }

        wrong_questions = _wrong_question_items(resource, record)
        wrong_kps = _wrong_knowledge_points(resource, record) or _step_kps(step)
        attempts = [item for item in _as_list(step.get("remediation_attempts")) if isinstance(item, dict)]
        existing_attempt = next(
            (
                item
                for item in attempts
                if int(item.get("failed_quiz_record_id") or 0) == int(record.id)
            ),
            None,
        )
        attempt = existing_attempt or _build_remediation_attempt(
            step=step,
            record=record,
            resource=resource,
            wrong_kps=wrong_kps,
            wrong_questions=wrong_questions,
            attempt_no=len(attempts) + 1,
        )

        if generate_resources:
            resource_types = _remediation_resource_types(step, wrong_kps)
            existing_ids = set(int(rid) for rid in _as_list(step.get("resource_ids")) if str(rid).isdigit())
            generated = [item for item in _as_list(step.get("resources")) if isinstance(item, dict)]
            attempt_resources = [item for item in _as_list(attempt.get("resources")) if isinstance(item, dict)]
            attempt["resources"] = attempt_resources
            attempt["resource_ids"] = [int(rid) for rid in _as_list(attempt.get("resource_ids")) if str(rid).isdigit()]
            attempt["resource_failures"] = [
                item for item in _as_list(attempt.get("resource_failures")) if isinstance(item, dict)
            ]
            existing_attempt_types = {str(item.get("type")) for item in attempt_resources if item.get("type")}
            remediation_step = {
                **step,
                "title": f"{step.get('title') or f'步骤 {step_order}'} 补弱",
                "description": (
                    f"针对检查未通过的知识点进行补弱：{', '.join(wrong_kps) if wrong_kps else '本步骤知识点'}。"
                    "先复盘概念，再完成巩固练习。"
                ),
                "knowledge_points": wrong_kps,
                "resource_types": resource_types,
            }
            for resource_type in resource_types:
                if resource_type in existing_attempt_types:
                    continue
                try:
                    state = await _generate_step_resource(path.user_id, path, remediation_step, resource_type)
                    rid = state.get("resource_db_id")
                    if not rid:
                        attempt["resource_failures"].append({"type": resource_type, "error": "未返回资源 ID"})
                        continue
                    res = db.query(LearningResource).get(rid)
                    if not res:
                        attempt["resource_failures"].append({"type": resource_type, "error": f"资源 {rid} 不存在"})
                        continue
                    content = dict(res.content) if isinstance(res.content, dict) else {"text": res.content}
                    content["path_remediation"] = {
                        "path_id": path.id,
                        "course_name": path.course_name,
                        "step_order": step_order,
                        "attempt_no": attempt["attempt_no"],
                        "weak_knowledge_points": wrong_kps,
                        "failed_quiz_record_id": record.id,
                    }
                    res.content = content
                    res.course_name = res.course_name or path.course_name
                    res.knowledge_points = wrong_kps
                    res.kp_weights = {kp: round(1 / max(len(wrong_kps), 1), 4) for kp in wrong_kps}
                    set_resource_lineage(
                        res,
                        relation_type="remediation",
                        parent_resource_ids=[int(resource.id)] if resource else [],
                        root_resource_id=int(resource.id) if resource else None,
                        group_id=f"path:{path.id}:step:{step_order}:remediation:{attempt['attempt_no']}",
                        group_type="path_remediation",
                        source_module="learning_path",
                        source_context=content["path_remediation"],
                    )
                    existing_ids.add(int(rid))
                    item = {"id": int(rid), "title": res.title, "type": res.resource_type}
                    attempt["resource_ids"].append(int(rid))
                    attempt["resources"].append(item)
                    existing_attempt_types.add(str(res.resource_type))
                    generated.append(item)
                except Exception as exc:
                    attempt["resource_failures"].append({"type": resource_type, "error": str(exc)})

            step["resource_ids"] = list(existing_ids)
            step["resources"] = generated
            if not existing_attempt:
                attempts.append(attempt)
            step["remediation_attempts"] = attempts
            step["status"] = "learning"
            step["mastery_status"] = "failed"
            _recalculate_path_progress(path, steps)
            db.commit()
            db.refresh(path)

        return {
            "ok": True,
            "passed": False,
            "score": round(score, 4),
            "passing_score": passing_score,
            "weak_knowledge_points": wrong_kps,
            "wrong_questions": wrong_questions,
            "attempt": attempt,
            "remediation_attempts": _as_list(step.get("remediation_attempts")),
            "step": step,
            **_path_payload(path),
        }
    finally:
        db.close()


@router.post("/{path_id}/generate-resources")
async def generate_resources_for_path(path_id: int):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).get(path_id)
        if not path:
            return {"ok": False, "error": "路径不存在"}

        steps = [_step_with_defaults(step) for step in (path.steps or []) if isinstance(step, dict)]

        async def run_one(step: dict, resource_type: str, existing_types: set) -> dict | None:
            """每个资源类型用独立 db session，避免并发共享 session 导致状态混乱。"""
            if resource_type in existing_types:
                return None
            try:
                state = await _generate_step_resource(path.user_id, path, step, resource_type)
                if resource_type == "ppt":
                    session = state.get("ppt_session")
                    if session:
                        return {"type": "ppt_session", "data": session}
                    return {"type": "failure", "resource_type": resource_type, "error": "未创建 AiPPT 分步会话"}
                rid = state.get("resource_db_id")
                if not rid:
                    return {"type": "failure", "resource_type": resource_type, "error": "未返回资源 ID"}

                # 用独立 session 写入路径上下文，避免并发 session 冲突
                inner_db = SessionLocal()
                try:
                    res = inner_db.query(LearningResource).get(rid)
                    if not res:
                        return {"type": "failure", "resource_type": resource_type, "error": f"资源 {rid} 不存在"}
                    content = dict(res.content) if isinstance(res.content, dict) else {"text": res.content}
                    content["path_context"] = {
                        "path_id": path.id,
                        "course_name": path.course_name,
                        "step_order": step.get("order"),
                        "step_title": step.get("title"),
                        "knowledge_points": _step_kps(step),
                    }
                    res.content = content
                    if not res.course_name:
                        res.course_name = path.course_name
                    if not res.knowledge_points:
                        res.knowledge_points = _step_kps(step)
                    set_resource_lineage(
                        res,
                        relation_type="path_step",
                        group_id=f"path:{path.id}:step:{step.get('order')}",
                        group_type="path_step",
                        source_module="learning_path",
                        source_context=content["path_context"],
                    )
                    inner_db.commit()
                    return {"type": "resource", "id": int(rid), "title": res.title, "resource_type": res.resource_type}
                except Exception as exc:
                    inner_db.rollback()
                    raise
                finally:
                    inner_db.close()
            except Exception as exc:
                import traceback
                error_msg = f"{type(exc).__name__}: {str(exc)}"
                print(f"[generate_resources] step={step.get('order')} type={resource_type} error: {error_msg}")
                traceback.print_exc()
                return {"type": "failure", "resource_type": resource_type, "error": error_msg}

        async def gen_for_step(step: dict):
            resource_types = _normalize_resource_types(
                step.get("resource_types"),
                " ".join([str(step.get("title") or ""), str(step.get("description") or "")]),
            )
            check_rid = step.get("check_resource_id")
            current_resources = [r for r in _as_list(step.get("resources")) if isinstance(r, dict)]
            preserved_ids: set[int] = set()
            for item in current_resources:
                try:
                    resource_id = int(item.get("id", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if resource_id > 0:
                    preserved_ids.add(resource_id)
            if check_rid:
                preserved_ids.add(int(check_rid))
            preserved_resources = current_resources
            ppt_sessions = [item for item in _as_list(step.get("ppt_sessions")) if isinstance(item, dict)]
            existing_ids: set[int] = set(preserved_ids)
            generated: list[dict] = list(preserved_resources)
            failures: list[dict] = []
            existing_types: set[str] = set()
            for item in current_resources:
                try:
                    resource_id = int(item.get("id", 0) or 0)
                except (TypeError, ValueError):
                    resource_id = 0
                if item.get("type") and resource_id != int(check_rid or 0):
                    existing_types.add(str(item.get("type")))
            if ppt_sessions:
                existing_types.add("ppt")

            import asyncio as _asyncio
            results = await _asyncio.gather(
                *[run_one(step, rt, existing_types) for rt in resource_types],
                return_exceptions=False,
            )

            for result in results:
                if result is None:
                    continue
                if result["type"] == "resource":
                    rid = result["id"]
                    if rid not in existing_ids:
                        existing_ids.add(rid)
                        generated.append({"id": rid, "title": result["title"], "type": result["resource_type"]})
                elif result["type"] == "ppt_session":
                    ppt_sessions.append(result["data"])
                elif result["type"] == "failure":
                    failures.append({"type": result["resource_type"], "error": result["error"]})

            step["resource_types"] = resource_types
            step["resource_ids"] = list(existing_ids)
            step["resources"] = generated
            step["ppt_sessions"] = ppt_sessions
            step["resource_failures"] = failures

        for step in steps:
            await gen_for_step(step)

        _recalculate_path_progress(path, steps)
        db.commit()
        db.refresh(path)
        return {"ok": True, **_path_payload(path)}
    finally:
        db.close()
