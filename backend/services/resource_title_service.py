import re
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_title(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"```[\s\S]*?```", " ", value)
    value = _TAG_RE.sub(" ", value)
    value = value.replace("【", "").replace("】", "")
    value = value.replace('"', "").replace("“", "").replace("”", "")
    value = re.sub(r"^(请|帮我|给我|为我|生成|写一个|做一个|制作|创建|设计|讲解一下|请帮我)\s*", "", value)
    value = re.sub(r"(的)?(代码案例|代码资源|可视化动画|动画资源|学习资源|PPT|课件)$", "", value)
    value = _SPACE_RE.sub(" ", value).strip(" ：:-_，,。.")
    return value[:36]


def _extract_from_content(content: Any) -> str:
    if isinstance(content, dict):
        for key in ("title", "topic", "task_desc", "name"):
            title = _clean_title(content.get(key))
            if title:
                return title
        code = str(content.get("code") or content.get("html") or content.get("text") or "")
        html_title = re.search(r"<title>(.*?)</title>", code, re.IGNORECASE | re.DOTALL)
        if html_title:
            title = _clean_title(html_title.group(1))
            if title:
                return title
        heading = re.search(r"^\s*#{1,3}\s+(.+)$", code, re.MULTILINE)
        if heading:
            title = _clean_title(heading.group(1))
            if title:
                return title
    elif isinstance(content, str):
        heading = re.search(r"^\s*#{1,3}\s+(.+)$", content, re.MULTILINE)
        if heading:
            title = _clean_title(heading.group(1))
            if title:
                return title
        return _clean_title(content[:120])
    return ""


def build_resource_title(
    resource_type: str,
    content: Any = None,
    *,
    fallback_text: str | None = None,
    course_name: str | None = None,
    knowledge_points: list[str] | None = None,
) -> str:
    topic = _extract_from_content(content) or _clean_title(fallback_text)
    if not topic and knowledge_points:
        topic = _clean_title("、".join(knowledge_points[:2]))
    if not topic and course_name:
        topic = _clean_title(course_name)

    if resource_type == "code":
        return f"代码案例：{topic or '未命名'}"
    if resource_type == "anime":
        return f"动画：{topic or '未命名'}"
    if resource_type == "ppt":
        return topic or "PPT课件"
    return topic or f"{resource_type}_resource"


def repair_legacy_code_resource_titles(session_factory) -> int:
    from models.course_path import CoursePath
    from models.resource import LearningResource

    db = session_factory()
    changed = 0
    try:
        resources = db.query(LearningResource).filter(
            LearningResource.resource_type == "code",
            LearningResource.title == "code_resource",
        ).all()
        id_to_title: dict[int, str] = {}
        for resource in resources:
            title = build_resource_title(
                "code",
                resource.content,
                fallback_text=" ".join([resource.course_name or "", "、".join(resource.knowledge_points or [])]),
                course_name=resource.course_name,
                knowledge_points=resource.knowledge_points or [],
            )
            resource.title = title
            id_to_title[resource.id] = title
            changed += 1

        if id_to_title:
            from sqlalchemy.orm.attributes import flag_modified
            paths = db.query(CoursePath).all()
            for path in paths:
                steps = path.steps or []
                touched = False
                for step in steps if isinstance(steps, list) else []:
                    for item in step.get("resources") or []:
                        rid = item.get("id")
                        if item.get("type") == "code" and item.get("title") == "code_resource" and rid in id_to_title:
                            item["title"] = id_to_title[rid]
                            touched = True
                if touched:
                    path.steps = steps
                    flag_modified(path, "steps")
        db.commit()
        return changed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
