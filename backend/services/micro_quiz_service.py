import json
import os
from collections import Counter
from typing import Any

from core.llm_client import chat_completion

MAX_MICRO_QUIZ_QUESTIONS = int(os.getenv("MICRO_QUIZ_MAX_QUESTIONS", "6"))
MICRO_QUIZ_TIMEOUT_SECONDS = float(os.getenv("MICRO_QUIZ_TIMEOUT_SECONDS", "30"))


LOW_QUALITY_PATTERNS = [
    "学习判断",
    "课程学分",
    "年级信息",
    "属于知识点",
    "本课程目标无关",
    "是否属于",
    "哪一项最合理",
]
OPTION_KEYS = {"A", "B", "C", "D"}


def _core_kps(graph: dict, limit: int) -> list[str]:
    nodes = [node.get("id") for node in graph.get("nodes", []) if node.get("id")]
    if not nodes:
        return []
    degree = Counter()
    for link in graph.get("links", []):
        if link.get("source"):
            degree[link["source"]] += 1
        if link.get("target"):
            degree[link["target"]] += 1
    return sorted(nodes, key=lambda kp: (-degree[kp], nodes.index(kp)))[:limit]


def _targets_for_courses(diagnostic_courses: list[dict], knowledge_graphs: dict) -> list[dict]:
    course_count = len(diagnostic_courses)
    if course_count <= 1:
        per_course_limit = min(4, MAX_MICRO_QUIZ_QUESTIONS)
    elif course_count == 2:
        per_course_limit = 2
    else:
        per_course_limit = 2

    targets: list[dict] = []
    for course in diagnostic_courses:
        course_name = course.get("course_name") or ""
        graph = knowledge_graphs.get(course_name) or {}
        for kp in _core_kps(graph, per_course_limit):
            targets.append({
                "course_id": course.get("course_id"),
                "course_name": course_name,
                "knowledge_point": kp,
            })
    return targets[:MAX_MICRO_QUIZ_QUESTIONS]


def _extract_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _prompt(targets: list[dict]) -> str:
    return f"""你是大学课程诊断题命题专家。请为“对话式学习画像建档”的微测验生成单选题。

严格要求：
1. 只围绕给定 targets 出题，每个 target 生成 1 道题。
2. course_id、course_name、knowledge_point 必须逐字复制 target，不得改写、概括或使用近义词。
3. 题目必须考察该知识点的真实概念、计算、辨析或应用，不允许问“它是不是知识点”“是否属于课程”“课程学分”“年级信息”等元问题。
4. 每题 4 个选项，key 必须是 A/B/C/D，answer 必须是其中一个 key。
5. explanation 必须解释为什么答案正确。
6. 只返回 JSON，不要 Markdown，不要额外文字。

返回格式：
{{
  "questions": [
    {{
      "course_id": "target中的course_id",
      "course_name": "target中的course_name",
      "knowledge_point": "target中的knowledge_point",
      "type": "single_choice",
      "question": "题干",
      "options": [
        {{"key": "A", "text": "选项A"}},
        {{"key": "B", "text": "选项B"}},
        {{"key": "C", "text": "选项C"}},
        {{"key": "D", "text": "选项D"}}
      ],
      "answer": "A",
      "explanation": "解析",
      "difficulty": "基础/中等"
    }}
  ]
}}

targets:
{json.dumps(targets, ensure_ascii=False, indent=2)}
"""


def _failure(course_name: str, knowledge_point: str, reason: str) -> dict:
    return {
        "course_name": course_name,
        "knowledge_point": knowledge_point,
        "reason": reason,
    }


def _validate_question(question: Any, allowed: dict[tuple[str, str], set[str]]) -> tuple[dict | None, dict | None]:
    if not isinstance(question, dict):
        return None, _failure("", "", "question_not_object")

    course_id = str(question.get("course_id") or "").strip()
    course_name = str(question.get("course_name") or "").strip()
    knowledge_point = str(question.get("knowledge_point") or "").strip()
    if not course_id or not course_name or not knowledge_point:
        return None, _failure(course_name, knowledge_point, "missing_course_or_knowledge_point")
    if knowledge_point not in allowed.get((course_id, course_name), set()):
        return None, _failure(course_name, knowledge_point, "knowledge_point_not_in_course_graph")

    prompt_text = str(question.get("question") or "").strip()
    if len(prompt_text) < 12:
        return None, _failure(course_name, knowledge_point, "question_too_short")
    if any(pattern in prompt_text for pattern in LOW_QUALITY_PATTERNS):
        return None, _failure(course_name, knowledge_point, "low_quality_meta_question")

    options = question.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return None, _failure(course_name, knowledge_point, "invalid_options_count")
    normalized_options = []
    seen_keys = set()
    for option in options:
        if not isinstance(option, dict):
            return None, _failure(course_name, knowledge_point, "option_not_object")
        key = str(option.get("key") or "").strip().upper()
        text = str(option.get("text") or "").strip()
        if key not in OPTION_KEYS or key in seen_keys or not text:
            return None, _failure(course_name, knowledge_point, "invalid_option")
        seen_keys.add(key)
        normalized_options.append({"key": key, "text": text})
    if seen_keys != OPTION_KEYS:
        return None, _failure(course_name, knowledge_point, "invalid_option_keys")

    answer = str(question.get("answer") or "").strip().upper()
    if answer not in OPTION_KEYS:
        return None, _failure(course_name, knowledge_point, "invalid_answer")
    explanation = str(question.get("explanation") or "").strip()
    if len(explanation) < 8:
        return None, _failure(course_name, knowledge_point, "missing_explanation")
    difficulty = str(question.get("difficulty") or "").strip()
    if not difficulty:
        return None, _failure(course_name, knowledge_point, "missing_difficulty")

    return {
        "course_id": course_id,
        "course_name": course_name,
        "knowledge_point": knowledge_point,
        "type": "single_choice",
        "question": prompt_text,
        "options": normalized_options,
        "answer": answer,
        "explanation": explanation,
        "difficulty": difficulty,
    }, None


def _allowed_kps(diagnostic_courses: list[dict], knowledge_graphs: dict) -> dict[tuple[str, str], set[str]]:
    allowed: dict[tuple[str, str], set[str]] = {}
    for course in diagnostic_courses:
        course_id = str(course.get("course_id") or "").strip()
        course_name = str(course.get("course_name") or "").strip()
        graph = knowledge_graphs.get(course_name) or {}
        points = {node.get("id") for node in graph.get("nodes", []) if node.get("id")}
        allowed[(course_id, course_name)] = points
    return allowed


async def generate_micro_quiz(diagnostic_courses: list[dict], knowledge_graphs: dict) -> dict:
    targets = _targets_for_courses(diagnostic_courses, knowledge_graphs)
    failures: list[dict] = []
    if not targets:
        return {
            "questions": [],
            "meta": {
                "generated_by": "llm",
                "generation_failures": [_failure("", "", "no_available_knowledge_points")],
            },
        }

    try:
        resp = await chat_completion([
            {"role": "system", "content": "你只输出严格 JSON。"},
            {"role": "user", "content": _prompt(targets)},
        ], temperature=0.2, timeout=MICRO_QUIZ_TIMEOUT_SECONDS, retries=0)
        raw = resp.choices[0].message.content
        data = _extract_json(raw)
    except Exception as exc:
        reason = f"llm_generation_failed: {str(exc)[:120]}"
        return {
            "questions": [],
            "meta": {
                "generated_by": "llm",
                "generation_failures": [
                    _failure(item["course_name"], item["knowledge_point"], reason)
                    for item in targets
                ],
            },
        }

    allowed = _allowed_kps(diagnostic_courses, knowledge_graphs)
    valid_questions: list[dict] = []
    generated_keys: set[tuple[str, str, str]] = set()
    for item in data.get("questions", []) if isinstance(data, dict) else []:
        valid, failure = _validate_question(item, allowed)
        if failure:
            failures.append(failure)
            continue
        key = (valid["course_id"], valid["course_name"], valid["knowledge_point"])
        if key in generated_keys:
            failures.append(_failure(valid["course_name"], valid["knowledge_point"], "duplicate_question"))
            continue
        generated_keys.add(key)
        valid["id"] = f"q{len(valid_questions) + 1}"
        valid_questions.append(valid)

    for target in targets:
        key = (str(target.get("course_id") or ""), target["course_name"], target["knowledge_point"])
        if key not in generated_keys:
            failures.append(_failure(target["course_name"], target["knowledge_point"], "missing_valid_question"))

    return {
        "questions": valid_questions[:MAX_MICRO_QUIZ_QUESTIONS],
        "meta": {
            "generated_by": "llm",
            "generation_failures": failures,
        },
    }
