import json
import os

from models.student import StudentProfile

_KP_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "kp")
_CURRICULA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "curricula")

course_kp_map: dict[str, list[str]] = {}
kp_course_map: dict[str, str] = {}
course_graph_map: dict[str, dict] = {}

_KP_ALIASES: dict[str, tuple[str, str]] = {
    "k-means": ("机器学习", "无监督学习"),
    "kmeans": ("机器学习", "无监督学习"),
    "k均值": ("机器学习", "无监督学习"),
    "k 均值": ("机器学习", "无监督学习"),
    "聚类算法": ("机器学习", "无监督学习"),
    "聚类": ("机器学习", "无监督学习"),
    "无监督": ("机器学习", "无监督学习"),
    "决策树": ("机器学习", "决策树与集成方法"),
    "随机森林": ("机器学习", "决策树与集成方法"),
    "集成学习": ("机器学习", "决策树与集成方法"),
    "svm": ("机器学习", "支持向量机"),
    "支持向量": ("机器学习", "支持向量机"),
    "特征选择": ("机器学习", "特征工程"),
    "特征处理": ("机器学习", "特征工程"),
    "过拟合": ("机器学习", "模型评估与调优"),
    "欠拟合": ("机器学习", "模型评估与调优"),
    "条件概率": ("概率论与数理统计", "条件概率与独立性"),
    "贝叶斯": ("概率论与数理统计", "条件概率与独立性"),
    "贝叶斯更新": ("概率论与数理统计", "条件概率与独立性"),
    "独立性": ("概率论与数理统计", "条件概率与独立性"),
    "样本空间": ("概率论与数理统计", "随机事件与概率"),
    "随机事件": ("概率论与数理统计", "随机事件与概率"),
    "概率公式": ("概率论与数理统计", "随机事件与概率"),
    "全概率": ("概率论与数理统计", "条件概率与独立性"),
    "中心极限定理": ("概率论与数理统计", "大数定律与中心极限定理"),
    "大数定律": ("概率论与数理统计", "大数定律与中心极限定理"),
    "假设检验": ("概率论与数理统计", "假设检验"),
    "参数估计": ("概率论与数理统计", "参数估计"),
    "方差分析": ("概率论与数理统计", "方差分析与回归"),
    "回归": ("概率论与数理统计", "方差分析与回归"),
    "随机变量": ("概率论与数理统计", "随机变量与分布"),
    "概率分布": ("概率论与数理统计", "随机变量与分布"),
    "期望": ("概率论与数理统计", "数字特征"),
    "方差": ("概率论与数理统计", "数字特征"),
}


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


def _prune_generic_kps(matches: list[str]) -> list[str]:
    unique = list(dict.fromkeys(matches))
    has_specific = any(len(kp.strip()) >= 2 for kp in unique)
    if not has_specific:
        return unique
    return [kp for kp in unique if len(kp.strip()) >= 2]


def match_kp(text: str) -> list[str]:
    return _prune_generic_kps([kp for kp in kp_course_map if kp in (text or "")])


def _course_matches(text: str) -> list[str]:
    content = text or ""
    return sorted(
        [course for course in course_kp_map if course and course in content],
        key=len,
        reverse=True,
    )


def _match_kps_for_inference(text: str, course_context: str | None = None) -> list[str]:
    content = text or ""
    content_lower = content.lower()
    allowed = set(course_kp_map.get(course_context, [])) if course_context else None
    matches: list[str] = []
    for kp in kp_course_map:
        if kp not in content:
            continue
        if allowed is not None and kp not in allowed:
            continue
        if allowed is None and len(kp.strip()) < 2:
            continue
        matches.append(kp)
    for alias, (alias_course, alias_kp) in _KP_ALIASES.items():
        if alias.lower() not in content_lower:
            continue
        if alias_kp not in kp_course_map:
            continue
        if course_context and alias_course != course_context and alias_kp not in (allowed or set()):
            continue
        if allowed is not None and alias_kp not in allowed:
            continue
        matches.append(alias_kp)
    return _prune_generic_kps(matches)


def get_course_kps(course_name: str | None) -> list[str]:
    if not course_name:
        return []
    return list(course_kp_map.get(course_name, []))


def infer_course_from_text(text: str, default: str | None = None) -> str | None:
    content = text or ""
    course_matches = _course_matches(content)
    if course_matches:
        return course_matches[0]
    matched = _match_kps_for_inference(content)
    if matched:
        return kp_course_map.get(matched[0])
    return default


def default_focus_kps(course_name: str | None, text: str = "", limit: int = 4) -> list[str]:
    matched = _match_kps_for_inference(text or "", course_name)
    if matched:
        return list(dict.fromkeys(matched))[:limit]
    nodes = get_course_kps(course_name)
    return nodes[:limit]


def course_coverage(db, user_id: str, course_name: str) -> dict:
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
    kb = dict(profile.knowledge_base or {}) if profile else {}
    kps = get_course_kps(course_name)
    items = [{"knowledge_point": kp, "mastery": float(kb.get(kp, 0) or 0)} for kp in kps]
    measured_items = [item for item in items if item["knowledge_point"] in kb]
    avg = round(sum(x["mastery"] for x in measured_items) / len(measured_items), 4) if measured_items else 0
    overall_avg = round(sum(x["mastery"] for x in items) / len(items), 4) if items else 0
    return {
        "course_name": course_name,
        "total": len(items),
        "measured": len(measured_items),
        "coverage_ratio": round(len(measured_items) / len(items), 4) if items else 0,
        "average_mastery": avg,
        "overall_mastery": overall_avg,
        "items": items,
    }


def infer_resource_tags(
    text: str,
    course_name: str | None = None,
    knowledge_points: list[str] | None = None,
) -> dict:
    explicit_kps = [kp for kp in (knowledge_points or []) if kp in kp_course_map]
    explicit_course = bool(course_name)
    course_matches = _course_matches(text or "")

    if course_name:
        course = course_name
    elif course_matches:
        course = course_matches[0]
    else:
        course = None

    matched_kps = explicit_kps or _match_kps_for_inference(text or "", course)

    if course:
        allowed = set(course_kp_map.get(course, []))
        if allowed:
            matched_kps = [kp for kp in matched_kps if kp in allowed]
    elif matched_kps:
        counts: dict[str, int] = {}
        for kp in matched_kps:
            course = kp_course_map.get(kp)
            if course:
                counts[course] = counts.get(course, 0) + 1
        course = max(counts, key=counts.get) if counts else None

    if explicit_course and course and course in course_kp_map:
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

    grouped_kps: dict[str, list[str]] = {}
    for kp in unique_kps:
        kp_course = kp_course_map.get(kp) or course
        if kp_course:
            grouped_kps.setdefault(kp_course, []).append(kp)
    if course and course not in grouped_kps and not grouped_kps:
        grouped_kps[course] = []

    total_kps = max(len(unique_kps), 1)
    course_bindings = []
    for binding_course, binding_kps in grouped_kps.items():
        binding_kps = list(dict.fromkeys(binding_kps))
        binding_weight = round(len(binding_kps) / total_kps, 4) if unique_kps else 1.0
        binding_kp_weights = {}
        if binding_kps:
            per_kp = round(1 / len(binding_kps), 4)
            binding_kp_weights = {kp: per_kp for kp in binding_kps}
        course_bindings.append({
            "course_name": binding_course,
            "knowledge_points": binding_kps,
            "weight": binding_weight,
            "kp_weights": binding_kp_weights,
        })

    return {
        "course_name": course,
        "knowledge_points": unique_kps,
        "kp_weights": kp_weights,
        "tag_confidence": confidence,
        "course_bindings": course_bindings,
    }


def update_knowledge_base(db, user_id: str, kp_scores: dict[str, float], alpha: float = 0.3):
    return


def set_course_kp_scores(db, user_id: str, course_name: str, score: float):
    return
