import hashlib
import json
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE_DIR = BACKEND_DIR / "data" / "knowledge_base"
DATA_STRUCTURES_DIR = KNOWLEDGE_BASE_DIR / "data_structures"
DATA_STRUCTURES_MANIFEST = DATA_STRUCTURES_DIR / "manifest.json"
DATA_STRUCTURES_KP_FILE = BACKEND_DIR / "static" / "kp" / "数据结构.json"


def load_course_manifest() -> dict:
    with DATA_STRUCTURES_MANIFEST.open(encoding="utf-8") as handle:
        return json.load(handle)


def _allowed_knowledge_points() -> set[str]:
    with DATA_STRUCTURES_KP_FILE.open(encoding="utf-8") as handle:
        graph = json.load(handle)
    return {
        str(node.get("id") or "").strip()
        for node in graph.get("nodes", [])
        if str(node.get("id") or "").strip()
    }


def _practice_appendix(title: str, focuses: list[str]) -> str:
    modes = [
        (
            "概念辨析",
            "先写出对象、输入规模和操作约束，再比较容易混淆的概念。答案必须指出结论成立的前提，不能只写算法名称。",
            "核对是否定义了研究对象，是否说明边界条件，是否把平均情况、最坏情况和一次实际运行混为一谈。",
        ),
        (
            "过程推演",
            "选择一组规模不超过十的数据，逐步记录结构状态、关键变量和每次操作后的不变量，最后再总结一般规律。",
            "核对每一步是否保存了必要的中间状态，是否存在遗漏元素、重复访问、错误覆盖或指针断链。",
        ),
        (
            "边界测试",
            "分别考虑空输入、单元素、重复元素、极端有序或极端不平衡情况，并说明实现应返回什么以及为什么。",
            "核对循环是否必然收敛，数组下标是否越界，空结构操作是否有清晰约定，异常输入是否被静默吞掉。",
        ),
        (
            "复杂度与工程选择",
            "分别估算时间、额外空间和数据移动代价，再结合查询频率、更新频率、数据规模和缓存局部性给出选择。",
            "核对复杂度是否使用正确输入规模，是否忽略构建成本，是否把理论上界直接等同于所有场景的实际性能。",
        ),
    ]
    sections = ["\n## 结构化变式练习库\n", "以下练习由团队编写的知识主题确定性展开，用于形成稳定的初始诊断与检索语料，不依赖运行时大模型。\n"]
    sequence = 1
    for focus in focuses:
        for mode, requirement, checklist in modes:
            sections.append(
                f"\n### 变式练习 {sequence}：{focus}·{mode}\n\n"
                f"**任务情境：** 在《{title}》的学习过程中，围绕“{focus}”设计一个可复现的小规模案例。"
                f"案例必须给出原始数据、目标操作和预期结果，并解释选择当前数据结构或算法的理由。\n\n"
                f"**作答要求：** {requirement} 除最终结论外，还要写出至少一个不适用当前方法的反例，"
                "并说明若输入规模扩大十倍，原方案的主要瓶颈会出现在哪里。\n\n"
                f"**参考解析框架：** 首先明确“{focus}”对应的结构不变量和算法前提；其次用具体数据逐步执行，"
                "记录比较、移动、入栈出栈、指针变化或访问标记等关键动作；然后计算主要操作次数并给出渐进复杂度；"
                "最后从正确性、可维护性、内存开销和异常处理四个角度评价方案。参考答案不要求与某段固定代码一致，"
                "但每一步必须能由前一步推导，且不得使用尚未满足前提的算法。\n\n"
                f"**自检清单：** {checklist} 若发现结论依赖隐含条件，应把条件补写在答案中，再重新判断。\n"
            )
            sequence += 1
    return "".join(sections)


def load_course_documents(expand_practice: bool = True) -> list[dict]:
    manifest = load_course_manifest()
    allowed = _allowed_knowledge_points()
    documents: list[dict] = []
    errors: list[str] = []

    for item in manifest.get("documents", []):
        path = DATA_STRUCTURES_DIR / str(item.get("file") or "")
        if not path.is_file():
            errors.append(f"缺少课程文档：{path.name}")
            continue

        knowledge_points = [str(value).strip() for value in item.get("knowledge_points", []) if str(value).strip()]
        invalid = [value for value in knowledge_points if value not in allowed]
        if invalid:
            errors.append(f"{path.name} 包含未在知识图谱中定义的知识点：{', '.join(invalid)}")
            continue
        if not knowledge_points:
            errors.append(f"{path.name} 未绑定知识点")
            continue

        raw = path.read_text(encoding="utf-8").strip()
        content = raw
        if expand_practice:
            content += _practice_appendix(
                str(item.get("title") or path.stem),
                [str(value).strip() for value in item.get("practice_focus", []) if str(value).strip()],
            )
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        documents.append({
            **item,
            "course_id": manifest.get("course_id"),
            "course_name": manifest.get("course_name"),
            "version": manifest.get("version"),
            "source": manifest.get("source", "team_constructed"),
            "license": manifest.get("license", ""),
            "path": str(path),
            "content": content,
            "content_hash": content_hash,
        })

    if errors:
        raise ValueError("；".join(errors))

    minimum = int(manifest.get("minimum_rendered_characters") or 0)
    total_characters = sum(len(item["content"]) for item in documents)
    if expand_practice and minimum and total_characters < minimum:
        raise ValueError(f"课程知识库正文不足：{total_characters} < {minimum}")
    return documents


def validate_course_corpus() -> dict:
    manifest = load_course_manifest()
    documents = load_course_documents(expand_practice=True)
    source_character_count = sum(
        len(Path(item["path"]).read_text(encoding="utf-8"))
        for item in documents
    )
    return {
        "ready": True,
        "course_name": manifest.get("course_name"),
        "version": manifest.get("version"),
        "document_count": len(documents),
        "source_character_count": source_character_count,
        "rendered_character_count": sum(len(item["content"]) for item in documents),
        "knowledge_points": sorted({kp for item in documents for kp in item.get("knowledge_points", [])}),
    }
