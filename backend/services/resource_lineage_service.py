from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.resource import LearningResource


LINEAGE_VERSION = 1
LINEAGE_RELATION_TYPES = {
    "generated_from_article",
    "generated_from_quiz",
    "same_package",
    "path_step",
    "path_check",
    "remediation",
    "ppt_session",
    "manual",
    "unknown",
}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _as_int_list(value) -> list[int]:
    ids: list[int] = []
    for item in _as_list(value):
        try:
            resource_id = int(item)
        except (TypeError, ValueError):
            continue
        if resource_id > 0 and resource_id not in ids:
            ids.append(resource_id)
    return ids


def _content_dict(resource: LearningResource) -> dict:
    return dict(resource.content) if isinstance(resource.content, dict) else {"text": resource.content}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def normalize_lineage(raw: Any) -> dict:
    data = dict(raw) if isinstance(raw, dict) else {}
    relation_type = str(data.get("relation_type") or "unknown")
    if relation_type not in LINEAGE_RELATION_TYPES:
        relation_type = "unknown"
    return {
        "version": int(data.get("version") or LINEAGE_VERSION),
        "relation_type": relation_type,
        "parent_resource_ids": _as_int_list(data.get("parent_resource_ids")),
        "root_resource_id": int(data.get("root_resource_id") or 0) or None,
        "group_id": str(data.get("group_id") or "").strip() or None,
        "group_type": str(data.get("group_type") or "").strip() or None,
        "source_module": str(data.get("source_module") or "").strip() or None,
        "source_context": data.get("source_context") if isinstance(data.get("source_context"), dict) else {},
        "created_at": data.get("created_at") or None,
        "updated_at": data.get("updated_at") or None,
    }


def get_resource_lineage(resource: LearningResource | None) -> dict:
    if not resource:
        return normalize_lineage({})
    content = resource.content if isinstance(resource.content, dict) else {}
    return normalize_lineage(content.get("lineage"))


def set_resource_lineage(
    resource: LearningResource,
    relation_type: str,
    parent_resource_ids: list[int] | None = None,
    root_resource_id: int | None = None,
    group_id: str | None = None,
    group_type: str | None = None,
    source_module: str | None = None,
    source_context: dict | None = None,
    preserve_created_at: bool = True,
) -> dict:
    parent_ids = _as_int_list(parent_resource_ids or [])
    existing = get_resource_lineage(resource)
    if relation_type not in LINEAGE_RELATION_TYPES:
        relation_type = "unknown"
    lineage = {
        "version": LINEAGE_VERSION,
        "relation_type": relation_type,
        "parent_resource_ids": parent_ids,
        "root_resource_id": root_resource_id or existing.get("root_resource_id") or (parent_ids[0] if parent_ids else None),
        "group_id": group_id or existing.get("group_id"),
        "group_type": group_type or existing.get("group_type"),
        "source_module": source_module or existing.get("source_module"),
        "source_context": source_context if isinstance(source_context, dict) else existing.get("source_context") or {},
        "created_at": existing.get("created_at") if preserve_created_at and existing.get("created_at") else _now_iso(),
        "updated_at": _now_iso(),
    }
    content = _content_dict(resource)
    content["lineage"] = lineage
    resource.content = content
    return lineage


def resource_lineage_node(resource: LearningResource | None, missing_id: int | None = None) -> dict:
    if not resource:
        return {
            "id": missing_id,
            "missing": True,
            "title": "来源资源已删除",
            "resource_type": "unknown",
            "lineage": normalize_lineage({}),
        }
    return {
        "id": resource.id,
        "title": resource.title,
        "resource_type": resource.resource_type,
        "course_name": resource.course_name,
        "knowledge_points": _as_list(resource.knowledge_points),
        "learning_status": resource.learning_status or "not_started",
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
        "lineage": get_resource_lineage(resource),
    }


def build_lineage_summary_map(resources: list[LearningResource]) -> dict[int, dict]:
    id_map = {int(resource.id): resource for resource in resources if resource.id is not None}
    summaries: dict[int, dict] = {}
    for resource_id, resource in id_map.items():
        lineage = get_resource_lineage(resource)
        group_id = lineage.get("group_id")
        parents = [pid for pid in lineage.get("parent_resource_ids", []) if pid in id_map]
        children = [
            other.id
            for other in resources
            if resource_id in get_resource_lineage(other).get("parent_resource_ids", [])
        ]
        same_group = [
            other.id
            for other in resources
            if other.id != resource_id
            and group_id
            and get_resource_lineage(other).get("group_id") == group_id
        ]
        summaries[resource_id] = {
            "relation_type": lineage.get("relation_type") or "unknown",
            "parent_count": len(parents),
            "child_count": len(children),
            "group_count": len(same_group),
            "group_id": group_id,
            "group_type": lineage.get("group_type"),
            "has_lineage": bool(
                parents
                or children
                or same_group
                or lineage.get("relation_type") not in {None, "", "unknown"}
            ),
        }
    return summaries


def build_resource_lineage(db: Session, resource: LearningResource, user_id: str | None = None) -> dict:
    owner_id = user_id or resource.user_id
    resources = db.query(LearningResource).filter(LearningResource.user_id == owner_id).all()
    id_map = {int(item.id): item for item in resources if item.id is not None}
    lineage = get_resource_lineage(resource)
    parent_ids = lineage.get("parent_resource_ids", [])
    parents = [resource_lineage_node(id_map.get(pid), pid) for pid in parent_ids]
    group_id = lineage.get("group_id")
    children = [
        resource_lineage_node(item)
        for item in resources
        if resource.id in get_resource_lineage(item).get("parent_resource_ids", [])
    ]
    group_resources = [
        resource_lineage_node(item)
        for item in resources
        if item.id != resource.id
        and group_id
        and get_resource_lineage(item).get("group_id") == group_id
    ]
    root = id_map.get(int(lineage.get("root_resource_id") or 0))
    return {
        "ok": True,
        "current": resource_lineage_node(resource),
        "lineage": lineage,
        "root_resource": resource_lineage_node(root) if root else None,
        "parent_resources": parents,
        "child_resources": children,
        "group_resources": group_resources,
        "lineage_summary": build_lineage_summary_map(resources).get(resource.id, {}),
    }


def infer_lineage_from_content(resource: LearningResource) -> dict | None:
    content = resource.content if isinstance(resource.content, dict) else {}
    existing = content.get("lineage")
    if isinstance(existing, dict) and existing:
        return normalize_lineage(existing)
    if isinstance(content.get("path_remediation"), dict):
        ctx = content["path_remediation"]
        return normalize_lineage(
            {
                "relation_type": "remediation",
                "group_id": f"path:{ctx.get('path_id')}:step:{ctx.get('step_order')}:remediation",
                "group_type": "path_remediation",
                "source_module": "learning_path",
                "source_context": ctx,
            }
        )
    if isinstance(content.get("path_check"), dict):
        ctx = content["path_check"]
        return normalize_lineage(
            {
                "relation_type": "path_check",
                "group_id": f"path:{ctx.get('path_id')}:step:{ctx.get('step_order')}",
                "group_type": "path_step",
                "source_module": "learning_path",
                "source_context": ctx,
            }
        )
    if isinstance(content.get("path_context"), dict):
        ctx = content["path_context"]
        return normalize_lineage(
            {
                "relation_type": "path_step",
                "group_id": f"path:{ctx.get('path_id')}:step:{ctx.get('step_order')}",
                "group_type": "path_step",
                "source_module": "learning_path",
                "source_context": ctx,
            }
        )
    if isinstance(content.get("course_bindings"), list) and content.get("course_bindings"):
        return normalize_lineage(
            {
                "relation_type": "unknown",
                "source_module": "rebuild",
                "source_context": {"course_bindings": content.get("course_bindings")},
            }
        )
    return normalize_lineage({"relation_type": "unknown", "source_module": "rebuild"})


def rebuild_resource_lineage(db: Session, user_id: str) -> dict:
    resources = db.query(LearningResource).filter(LearningResource.user_id == user_id).all()
    updated_ids: list[int] = []
    compare_keys = [
        "relation_type",
        "parent_resource_ids",
        "root_resource_id",
        "group_id",
        "group_type",
        "source_module",
        "source_context",
    ]
    for resource in resources:
        inferred = infer_lineage_from_content(resource)
        if not inferred:
            continue
        current = get_resource_lineage(resource)
        content = resource.content if isinstance(resource.content, dict) else {}
        if isinstance(content.get("lineage"), dict) and all(current.get(key) == inferred.get(key) for key in compare_keys):
            continue
        set_resource_lineage(
            resource,
            relation_type=inferred.get("relation_type") or "unknown",
            parent_resource_ids=inferred.get("parent_resource_ids") or [],
            root_resource_id=inferred.get("root_resource_id"),
            group_id=inferred.get("group_id"),
            group_type=inferred.get("group_type"),
            source_module=inferred.get("source_module"),
            source_context=inferred.get("source_context") or {},
        )
        updated_ids.append(resource.id)
    db.commit()
    return {"ok": True, "updated": len(updated_ids), "ids": updated_ids}
