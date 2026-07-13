import json
import re
import uuid
from langgraph.constants import Send
from langgraph.graph import StateGraph, START, END
from graph.state import AgentGraphState
from agents.tools import tavily_search
from agents.skills import get_skill, get_all_skills, get_skills_description, SkillResult
from graph.subgraphs.resource_orchestration import resource_orchestration_graph


def _strip_suggestion_lines(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"(?m)^\s*[\[【]建议[\]】].*(?:\n|$)", "", text).strip()


def _get_sse_queue(session_id: str):
    """从全局队列字典取出 SSE 队列"""
    from core.sse_registry import get
    return get(session_id)


async def _llm_stream(system_prompt: str, user_prompt: str):
    from core.llm_client import chat_completion
    from services.config_service import is_configured
    if not is_configured("main"):
        yield ""
        return
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        stream = await chat_completion(messages, stream=True, max_tokens=800)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else ""
            if delta:
                yield delta
    except Exception:
        yield ""


def _has_mistake_intent(message: str) -> bool:
    return any(keyword in message for keyword in ["错题", "错因", "错误题", "薄弱题", "错题本"])


SKILL_ALIASES = {
    "搜索智能体": "deep_search",
    "深度搜索": "deep_search",
    "代码分析智能体": "code_analysis",
    "代码分析": "code_analysis",
    "代码智能体": "code_gen",
    "动画智能体": "code_gen",
    "代码/动画智能体": "code_gen",
    "code_generation": "code_gen",
    "导图智能体": "mindmap_gen",
    "思维导图智能体": "mindmap_gen",
    "mindmap": "mindmap_gen",
    "出题智能体": "quiz_gen",
    "题库智能体": "quiz_gen",
    "quiz_generation": "quiz_gen",
    "视频智能体": "video_search",
    "视频搜索": "video_search",
    "video_gen": "video_search",
    "课件智能体": "ppt_gen",
    "ppt_generation": "ppt_gen",
    "文章智能体": "article_gen",
    "article_generation": "article_gen",
    "实践案例智能体": "practice_case",
}


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _has_action_object(text: str, actions: list[str], objects: list[str]) -> bool:
    return _contains_any(text, actions) and _contains_any(text, objects)


def _normalize_task_message(message: str, history: list[dict] | None = None) -> str:
    text = (message or "").strip()
    vague_terms = ["这个", "那个", "它", "上述", "刚才", "前面", "助我理解", "帮助我理解"]
    if not text or not _contains_any(text, vague_terms):
        return text
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if not content or content == text:
            continue
        return f"{text}\n相关对话主题：{content[:300]}"
    return text


def _normalize_skill_names(skills, valid_skills: dict) -> tuple[list[str], list[str]]:
    if isinstance(skills, str):
        skills = re.split(r"[,，\s]+", skills)
    normalized = []
    corrections = []
    for raw_name in skills or []:
        name = str(raw_name or "").strip()
        if not name:
            continue
        canonical = SKILL_ALIASES.get(name, SKILL_ALIASES.get(name.lower(), name.lower()))
        if canonical != name:
            corrections.append(f"{name} → {canonical}")
        if canonical not in valid_skills:
            corrections.append(f"忽略未注册 Skill：{name}")
            continue
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized, corrections


def _infer_explicit_skill_intent(message: str) -> dict:
    text = (message or "").lower()
    create_actions = ["生成", "制作", "创建", "设计", "实现", "开发", "写一个", "写个", "给我一个", "给我生成", "给我做"]
    selected = []
    intents = []

    def add(skill_name: str, intent: str):
        if skill_name not in selected:
            selected.append(skill_name)
        if intent not in intents:
            intents.append(intent)

    if _requires_resource_orchestration(text):
        return {
            "intent": "resource_orchestration",
            "selected_skills": ["resource_orchestration"],
            "execution_route": "resource_orchestration",
            "confidence": 1.0,
        }

    if _requires_visual_code_artifact(text):
        add("code_gen", "generate_animation")
    if _has_action_object(text, ["推荐", "搜索", "查找", "检索", "找几个", "找一些", "给我找"], ["视频", "b站", "bilibili", "哔哩哔哩"]):
        add("video_search", "search_video")
    if _has_action_object(text, create_actions, ["ppt", "课件", "幻灯片"]):
        add("ppt_gen", "generate_ppt")
    if _has_action_object(text, create_actions + ["出一套", "来一套"], ["题库", "练习题", "测试题", "测验题", "习题"]):
        add("quiz_gen", "generate_quiz")
    if _has_action_object(text, create_actions + ["整理"], ["思维导图", "知识导图", "导图"]):
        add("mindmap_gen", "generate_mindmap")
    if _has_action_object(text, create_actions + ["撰写"], ["文章", "讲解文档", "学习文档", "阅读材料"]):
        add("article_gen", "generate_article")
    if _has_action_object(text, create_actions, ["实操案例", "实践案例", "项目案例", "实践项目"]):
        add("practice_case", "generate_practice_case")

    code_objects = ["代码", "程序", "脚本", "算法实现", "html", "javascript", "python", "java", "c++"]
    code_create = _has_action_object(text, create_actions + ["编写"], code_objects)
    code_analysis = _has_action_object(text, ["分析", "解释", "调试", "排查", "优化", "检查", "修复"], code_objects)
    if code_create:
        add("code_gen", "generate_code")
    elif code_analysis:
        add("code_analysis", "analyze_code")

    if _has_mistake_intent(text) and _contains_any(text, ["练习", "题", "巩固", "专项"]):
        add("quiz_gen", "mistake_remediation")
    if "video_search" not in selected and _has_action_object(
        text,
        ["搜索", "查找", "检索", "查资料", "联网搜索"],
        ["资料", "文献", "论文", "信息", "来源"],
    ):
        add("deep_search", "deep_search")

    return {
        "intent": "+".join(intents) if intents else "",
        "selected_skills": selected,
        "execution_route": "skill" if selected else "",
        "confidence": 0.95 if selected else 0.0,
    }


def _requires_visual_code_artifact(message: str) -> bool:
    text = (message or "").lower()
    visual_terms = [
        "可视化动画",
        "动画演示",
        "可视化演示",
        "交互演示",
        "动态演示",
        "步骤动画",
        "可视化",
        "动画",
        "visualization",
        "visual",
        "animation",
        "animate",
    ]
    create_terms = [
        "生成",
        "制作",
        "创建",
        "设计",
        "实现",
        "开发",
        "写一个",
        "写个",
        "做一个",
        "做个",
        "画一个",
        "画个",
        "给我生成",
        "给我做",
        "给我写",
        "给我一个",
        "给我多种",
    ]
    explain_only_terms = ["解释", "分析", "评价", "怎么看", "为什么"]
    video_search_terms = ["推荐视频", "搜索视频", "视频资源", "b站", "bilibili", "哔哩哔哩"]

    asks_visual = any(term in text for term in visual_terms)
    asks_create = any(term in text for term in create_terms)
    asks_video_search = any(term in text for term in video_search_terms)
    explain_only = any(term in text for term in explain_only_terms) and not asks_create
    return asks_visual and asks_create and not asks_video_search and not explain_only


def _resolve_skill_routing(
    message: str,
    selected_skills,
    code_needed: bool,
    code_lang: str,
    code_desc: str,
    explicit_message: str | None = None,
) -> dict:
    valid_skills = get_all_skills()
    planner_skills, corrections = _normalize_skill_names(selected_skills, valid_skills)
    intent_message = (explicit_message if explicit_message is not None else message).strip()
    explicit = _infer_explicit_skill_intent(intent_message)
    if explicit.get("execution_route") == "resource_orchestration":
        return {
            "intent": explicit["intent"],
            "selected_skills": ["resource_orchestration"],
            "execution_route": "resource_orchestration",
            "code_needed": code_needed,
            "code_lang": code_lang,
            "code_desc": code_desc,
            "route_source": "explicit_rule",
            "corrections": corrections,
        }

    explicit_skills = [skill for skill in explicit.get("selected_skills", []) if skill in valid_skills]
    normalized = []
    routing_candidates = explicit_skills or planner_skills
    if explicit_skills:
        ignored_planner_skills = [skill for skill in planner_skills if skill not in explicit_skills]
        if ignored_planner_skills:
            corrections.append(
                "明确任务仅执行用户指定能力，忽略规划模型追加 Skill："
                + "、".join(ignored_planner_skills)
            )
    for skill in routing_candidates:
        if skill not in normalized:
            normalized.append(skill)

    if not explicit_skills and code_needed and "code_analysis" not in normalized and "code_gen" not in normalized:
        code_generation_terms = ["生成", "制作", "创建", "实现", "开发", "写", "编写"]
        fallback = "code_gen" if _contains_any(intent_message.lower(), code_generation_terms) else "code_analysis"
        if fallback in valid_skills:
            normalized.append(fallback)
            corrections.append(f"needs_code 兜底 → {fallback}")

    if _requires_visual_code_artifact(intent_message) and "code_gen" in valid_skills:
        if "code_analysis" in normalized:
            corrections.append("可视化生成任务移除 code_analysis")
        normalized = [skill for skill in normalized if skill != "code_analysis"]
        if "code_gen" not in normalized:
            normalized.insert(0, "code_gen")
        code_needed = True
        code_lang = "html"
        code_desc = (code_desc or message).strip()

    if "code_gen" in normalized and "code_analysis" in normalized:
        if _contains_any(intent_message.lower(), ["生成", "制作", "创建", "实现", "写", "编写", "动画", "可视化"]):
            normalized.remove("code_analysis")
            corrections.append("代码生成任务移除 code_analysis")
        else:
            normalized.remove("code_gen")
            corrections.append("代码分析任务移除 code_gen")

    return {
        "intent": explicit.get("intent") or "llm_planned",
        "selected_skills": normalized,
        "execution_route": "skill" if normalized else "direct_answer",
        "code_needed": code_needed,
        "code_lang": code_lang,
        "code_desc": code_desc,
        "route_source": "explicit_rule" if explicit_skills else ("llm_plan" if planner_skills else "fallback"),
        "corrections": corrections,
    }


def _apply_skill_routing_guards(message: str, selected_skills: list, code_needed: bool, code_lang: str, code_desc: str):
    routing = _resolve_skill_routing(message, selected_skills, code_needed, code_lang, code_desc)
    return (
        routing["selected_skills"],
        routing["code_needed"],
        routing["code_lang"],
        routing["code_desc"],
    )


def _requires_resource_orchestration(message: str) -> bool:
    text = (message or "").lower()
    create_terms = ["生成", "制作", "创建", "规划", "设计", "给我"]
    resource_terms = ["资源包", "多模态", "完整资源", "整套资源", "一套学习资料", "多种学习资料", "学习方案", "学习路径"]
    return any(term in text for term in create_terms) and any(term in text for term in resource_terms)


def _parse_plan_json(text: str) -> tuple[dict | None, str]:
    if not (text or "").strip():
        return None, "规划模型未返回内容"
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates = fenced + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value, ""
    return None, "规划模型未返回有效 JSON 配置"


def _json_preview(value, limit: int = 3000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _skill_results_for_summary(skill_results: dict) -> dict:
    """压缩技能结果给汇总智能体，避免大段代码/HTML 覆盖任务主题。"""
    compact = {}
    for skill_name, value in (skill_results or {}).items():
        if not isinstance(value, dict):
            compact[skill_name] = value
            continue
        if skill_name in {"code_gen", "code_analysis"}:
            item = {k: v for k, v in value.items() if k not in {"code"}}
            code = value.get("code") or ""
            if code:
                item["code_preview"] = str(code)[:800]
            compact[skill_name] = item
        else:
            compact[skill_name] = value
    return compact


async def plan_node(state: AgentGraphState) -> AgentGraphState:
    """任务规划节点：分析任务并选择需要调用的 skills"""
    user_message = state.get("user_message", "")
    user_id = state.get("user_id", "")
    wf = state.get("workflow_outputs", [])
    use_llm = True
    try:
        from services.config_service import is_configured
        use_llm = is_configured("main")
    except Exception:
        use_llm = False

    step_id = str(uuid.uuid4())[:8]
    thinking_content = ""
    search_keywords = user_message
    code_needed = False
    code_lang = "python"
    code_desc = ""
    selected_skills = []  # 默认不强制使用任何skill，由LLM决定
    raw_planner_skills = []
    planning_error = ""
    history = state.get("history", [])[-6:]
    routing_message = _normalize_task_message(user_message, history)
    use_resource_orchestration = False
    session_id = state.get("_session_id", "")
    sse_queue = _get_sse_queue(session_id)

    # 获取可用 skills 描述
    skills_desc = get_skills_description()

    if use_llm:
        profile_text = state.get("profile_text", "暂无画像")
        history_text = ""
        if history:
            history_text = "\n\n对话历史（最近几轮）：\n" + "\n".join(
                f"{'用户' if h.get('role') == 'user' else 'AI'}: {h.get('content', '')[:200]}"
                for h in history
            )

        system = """你是一个AI Agent任务规划器。收到任务后，分析任务需求并选择合适的skills来完成。

学生画像中包含系统已读取到的真实模块上下文，包括错题本、学习资源、学习路径、知识图谱和专注记录。
如果任务涉及错题、资源、路径或图谱，必须优先利用这些上下文，不要要求用户重复提供系统已经有的数据。

可用的Skills列表：
""" + skills_desc + """

你需要：
1. 分析任务并输出计划
2. 选择1-3个最合适的skills
3. 输出JSON配置"""

        original_task_text = f"\n用户原始输入：{user_message}" if routing_message != user_message else ""
        user = f"""请对以下任务进行规划：

学生画像：{profile_text}
任务：{routing_message}{original_task_text}{history_text}

输出要求：
1. 先用1-2句话分析任务
2. 列出执行步骤
3. 输出一个JSON块：
{{
  "search_keywords": "精准搜索短语（2-4个核心词，空格分隔）",
  "selected_skills": ["skill名称1", "skill名称2"],
  "needs_code": true/false,
  "code_lang": "python|cpp|java|javascript|c",
  "code_desc": "代码描述（如果needs_code为true）"
}}

选择skills的原则（可以只选1个，也可以不选某个）：
- 只选择用户明确要求的产物或工具，不要擅自追加练习、导图、视频等辅助产物
- 用户只要求一种明确产物时，只选择对应的一个 Skill；只有用户明确要求多个产物时才组合多个 Skill
- 只有任务明确需要搜索外部资料时才选 deep_search
- 如果是简单概念解释、代码问题、直接推理可解决的任务，不需要 deep_search
- 如果任务涉及代码分析、解释、调试、优化，加入 code_analysis
- 如果任务需要生成代码示例、可视化动画、实操案例，加入 code_gen
- 如果任务需要知识梳理，加入 mindmap_gen
- 如果任务需要练习巩固，加入 quiz_gen
- 如果任务需要视频学习，加入 video_search
- 如果任务需要生成PPT或课件，加入 ppt_gen
- 如果任务需要生成学习文章或讲解文档，加入 article_gen
- 如果任务需要生成实操或实践案例，加入 practice_case
- code_analysis 和 code_gen 是独立的：请根据任务需求只选一个，一般不要同时选
- selected_skills 可以为空数组（表示直接用LLM回答）"""

        running_event = {
            "type": "step",
            "step_type": "thinking",
            "step_id": step_id,
            "status": "running",
            "title": "分析任务需求",
            "agent_name": "规划智能体",
            "_live_pushed": sse_queue is not None,
            "data": {"content": ""},
        }
        wf.append(running_event)
        if sse_queue:
            try:
                sse_queue.put_nowait(running_event)
            except Exception:
                pass

        async for token in _llm_stream(system, user):
            thinking_content += token
            token_event = {"type": "token", "step_id": step_id, "delta": token}
            wf.append(token_event)
            if sse_queue:
                try:
                    sse_queue.put_nowait(token_event)
                    from core.sse_registry import mark_live_token_step
                    mark_live_token_step(session_id, step_id)
                except Exception:
                    pass

        plan_json, planning_error = _parse_plan_json(thinking_content)
        if plan_json is None:
            retry_text = ""
            retry_user = user + "\n\n上一次输出无法解析。现在只输出符合要求的JSON对象，不要输出分析文字或Markdown代码块。"
            async for token in _llm_stream(system, retry_user):
                retry_text += token
            plan_json, planning_error = _parse_plan_json(retry_text)
            if plan_json is not None:
                thinking_content += "\n\n规划配置已自动修复。"

        if plan_json is not None:
            search_keywords = plan_json.get("search_keywords", routing_message)
            code_needed = bool(plan_json.get("needs_code", False))
            code_lang = str(plan_json.get("code_lang", "python") or "python")
            code_desc = str(plan_json.get("code_desc", "") or "")
            raw_planner_skills = plan_json.get("selected_skills", [])

        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "completed", "title": "分析任务需求", "agent_name": "规划智能体", "data": {"content": thinking_content}})
    else:
        thinking_content = f"分析任务：{user_message}"
        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "running", "title": "分析任务需求", "data": {"content": thinking_content}})
        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "completed", "title": "分析任务需求", "agent_name": "规划智能体", "data": {"content": thinking_content}})

    routing = _resolve_skill_routing(
        routing_message,
        raw_planner_skills,
        code_needed,
        code_lang,
        code_desc,
        explicit_message=user_message,
    )
    selected_skills = routing["selected_skills"]
    code_needed = routing["code_needed"]
    code_lang = routing["code_lang"]
    code_desc = routing["code_desc"]
    execution_route = routing["execution_route"]
    use_resource_orchestration = execution_route == "resource_orchestration"
    if raw_planner_skills and not selected_skills and not use_resource_orchestration and not planning_error:
        planning_error = "规划模型选择的 Skill 均未注册或无法识别"
    route_trace = {
        "original_request": user_message,
        "normalized_request": routing_message,
        "detected_intent": routing["intent"],
        "planner_skills": raw_planner_skills,
        "final_skills": selected_skills,
        "route_source": routing["route_source"],
        "corrections": routing["corrections"],
        "planning_error": planning_error,
    }
    return {
        "workflow_outputs": wf,
        "all_modules_data": {
            **(state.get("all_modules_data") or {}),
            "search_keywords": search_keywords,
            "code_needed": code_needed,
            "code_lang": code_lang,
            "code_desc": code_desc,
            "selected_skills": selected_skills,
            "use_resource_orchestration": use_resource_orchestration,
            "execution_route": execution_route,
            "planning_error": planning_error,
            "route_trace": route_trace,
        },
    }


def _dispatch_skill_nodes(state: AgentGraphState):
    ad = state.get("all_modules_data") or {}
    if ad.get("use_resource_orchestration"):
        return "resource_orchestration"
    selected_skills = ad.get("selected_skills", [])
    if not selected_skills:
        return "skill_collect"
    return [
        Send("skill_execute", {**state, "current_skill_name": skill_name})
        for skill_name in selected_skills
    ]


async def skill_execute_node(state: AgentGraphState) -> AgentGraphState:
    """单个 Skill 执行节点，由 LangGraph 动态并行派发"""
    user_message = state.get("user_message", "")
    user_id = state.get("user_id", "")
    wf = []
    ad = state.get("all_modules_data") or {}
    skill_name = state.get("current_skill_name", "")

    context = {
        "user_message": user_message,
        "user_id": user_id,
        "all_modules_data": ad,
        "profile": state.get("profile"),
        "profile_text": state.get("profile_text", ""),
        "course_name": state.get("course_name") or ad.get("course_name"),
        "knowledge_points": state.get("knowledge_points") or ad.get("knowledge_points") or [],
        "kp_weights": state.get("kp_weights") or ad.get("kp_weights") or {},
        "persist": False,
    }

    # 取出 SSE 队列（由 _agent_stream 注入到 state）
    sse_queue = _get_sse_queue(state.get("_session_id", ""))

    skill = get_skill(skill_name)
    if not skill:
        return {"skill_result_items": [{"skill_name": skill_name, "data": {"error": "未知 skill"}, "success": False}]}
    skill._sse_queue = sse_queue
    skill._session_id = state.get("_session_id", "")
    try:
        result = await skill.execute(context, wf)
        data = result.data if result.success else {"error": result.error}
        return {
            "skill_result_items": [{"skill_name": skill_name, "data": data, "success": result.success}],
            "skill_workflow_outputs": wf,
        }
    except Exception as e:
        return {
            "skill_result_items": [{"skill_name": skill_name, "data": {"error": str(e)}, "success": False}],
            "skill_workflow_outputs": wf,
        }
    finally:
        skill._sse_queue = None
        skill._session_id = ""


async def skill_collect_node(state: AgentGraphState) -> AgentGraphState:
    """汇总并行 skill 结果，写回原 all_modules_data 结构"""
    user_message = state.get("user_message", "")
    ad = dict(state.get("all_modules_data") or {})
    skill_results = {}
    for item in state.get("skill_result_items") or []:
        skill_name = item.get("skill_name")
        if not skill_name:
            continue
        data = item.get("data") or {}
        skill_results[skill_name] = data
        if skill_name == "deep_search" and item.get("success"):
            ad["search_result"] = {
                "results": data.get("search_results", []),
                "answer": data.get("answer", ""),
                "query": ad.get("search_keywords", user_message),
            }
    ad["skill_results"] = skill_results

    return {
        "workflow_outputs": list(state.get("workflow_outputs") or []) + list(state.get("skill_workflow_outputs") or []),
        "all_modules_data": ad,
    }


async def result_node(state: AgentGraphState) -> AgentGraphState:
    """结果汇总节点：整合所有 skill 执行结果生成最终报告"""
    user_message = state.get("user_message", "")
    wf = state.get("workflow_outputs", [])
    sse_queue = _get_sse_queue(state.get("_session_id", ""))
    ad = state.get("all_modules_data") or {}
    search_result = ad.get("search_result", {})
    skill_results = ad.get("skill_results", {})
    selected_skills = ad.get("selected_skills", [])
    agent_context = ad.get("agent_context") or {}
    mistakes = agent_context.get("mistakes") or {}
    mistake_total = int((mistakes or {}).get("total") or 0)
    mistake_prompt_context = ""
    if _has_mistake_intent(user_message):
        try:
            from services.agent_context_service import build_mistake_prompt_context
            mistake_prompt_context = build_mistake_prompt_context(mistakes)
        except Exception:
            mistake_prompt_context = ""
    if "resource_orchestration" in selected_skills:
        ad = dict(ad)
        skill_results = dict(skill_results or {})
        skill_results["resource_orchestration"] = {
            "resources": state.get("generated_resources") or [],
            "failures": state.get("orchestration_failures") or [],
            "course_name": state.get("course_name"),
            "knowledge_points": state.get("knowledge_points") or [],
        }
        ad["skill_results"] = skill_results
    profile_text = state.get("profile_text", "暂无画像")
    history = state.get("history", [])[-6:]

    results = search_result.get("results", [])
    answer = search_result.get("answer", "")
    use_llm = True
    try:
        from services.config_service import is_configured
        use_llm = is_configured("main")
    except Exception:
        use_llm = False

    step_id = str(uuid.uuid4())[:8]

    # ── 无 skill 模式：直接用 LLM 回答 ──
    if not selected_skills:
        planning_error = str(ad.get("planning_error") or "").strip()
        if planning_error:
            final_md = (
                "### 任务规划未完成\n\n"
                f"{planning_error}。系统未能可靠确定需要调用的工具，因此没有直接执行或生成可能错误的内容。"
                "请重试，或补充明确的任务类型和主题。"
            )
            wf.append({
                "type": "step",
                "step_type": "result",
                "step_id": step_id,
                "status": "error",
                "title": "任务规划失败",
                "agent_name": "规划智能体",
                "data": {"content": final_md},
            })
            return {"workflow_outputs": wf, "response": final_md, "all_modules_data": ad}

        rag_context = ""
        try:
            from services.rag_service import search_rag
            rag_res = search_rag(user_message, state.get("user_id", ""), top_k=3)
            docs = rag_res.get("documents", [])
            if docs:
                rag_context = "\n\n相关学习资料：\n" + "\n---\n".join(d[:600] for d in docs[:3])
        except Exception:
            pass

        history_text = ""
        if history:
            history_text = "\n\n对话历史：\n" + "\n".join(
                f"{'用户' if h.get('role') == 'user' else 'AI'}: {h.get('content', '')[:300]}"
                for h in history
            )

        direct_prompt = f"""学生画像与系统模块上下文：{profile_text}
任务/问题：{user_message}{history_text}{rag_context}

【系统数据使用要求】
- 学生画像字段中已包含错题本、学习资源、学习路径、知识图谱和专注记录。
- 当相关列表非空时，禁止声称“没有具体错题内容”或“无法访问系统数据”。
- 涉及错题分析时，必须基于错题本中的题目、学生答案、正确答案、解析和知识点给出结论。
- 涉及学习规划/资源推荐时，必须结合当前学习路径、资源状态和知识图谱课程状态。

请直接回答上述问题，使用Markdown格式，包含必要的代码块和公式。

禁止输出任何 `[建议]`、`【建议】` 或类似建议按钮格式。需要工具完成的任务由任务模式入口承接。"""

        if mistake_prompt_context:
            direct_prompt += (
                "\n\n【真实错题本摘要】\n"
                f"{mistake_prompt_context}\n"
                "如果上面显示已有错题记录，禁止声称错题本为空、没有历史错题或缺少错题内容。"
            )

        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "AI 回答", "agent_name": "对话智能体", "data": {"content": ""}})
        if sse_queue:
            try: sse_queue.put_nowait(wf[-1])
            except Exception: pass
        final_md = ""
        if use_llm:
            async for token in _llm_stream("你是个性化学习AI助手，根据学生画像给出精准、有深度的回答。", direct_prompt):
                final_md += token
                te = {"type": "token", "step_id": step_id, "delta": token}
                wf.append(te)
                if sse_queue:
                    try:
                        sse_queue.put_nowait(te)
                        from core.sse_registry import mark_live_token_step
                        mark_live_token_step(state.get("_session_id", ""), step_id)
                    except Exception: pass
        else:
            final_md = f"**{user_message}**\n\n（LLM 未配置，无法回答）"

        final_md = _strip_suggestion_lines(final_md)
        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "completed", "title": "AI 回答", "agent_name": "对话智能体", "data": {"content": final_md}})
        return {"workflow_outputs": wf, "response": final_md, "all_modules_data": ad}

    # ── 有 skill 模式：整合各 skill 结果 ──
    has_search = "deep_search" in selected_skills and results

    result_header = f"## {user_message}\n\n"
    if has_search:
        result_header += f"### 搜索摘要\n{answer or '（未获取AI摘要）'}\n\n### 相关资源\n"
        for r in results[:5]:
            result_header += f"\n- **[{r.get('title', '链接')}]({r.get('url', '#')})**"

    if _has_mistake_intent(user_message):
        if mistake_total > 0 and mistake_prompt_context:
            result_header += f"### 错题本依据\n{mistake_prompt_context}\n\n"
        else:
            result_header += "### 错题本状态\n当前没有读取到错题本记录，无法基于历史错题做个性化归因。\n\n"

    skill_summary_parts = []
    for skill_name, sdata in skill_results.items():
        if skill_name == "deep_search":
            continue
        if isinstance(sdata, dict) and not sdata.get("error"):
            if skill_name == "code_analysis" and sdata.get("code"):
                skill_summary_parts.append(f"\n### 代码实现\n```{sdata.get('language', 'python')}\n{sdata['code']}\n```")
            elif skill_name == "mindmap_gen" and sdata.get("markdown"):
                skill_summary_parts.append(f"\n### 知识导图\n{sdata['markdown'][:800]}")
            elif skill_name == "quiz_gen" and sdata.get("quiz"):
                quiz = sdata["quiz"]
                questions = quiz.get("questions", [])
                quiz_text = f"\n### 练习题 ({len(questions)} 题)\n"
                for q in questions[:3]:
                    quiz_text += f"\n**{q.get('id', '')}. {q.get('question', '')}**\n"
                    for opt in q.get("options", []):
                        quiz_text += f"  {opt}\n"
                if len(questions) > 3:
                    quiz_text += f"\n... 共 {len(questions)} 题"
                skill_summary_parts.append(quiz_text)
            elif skill_name == "video_search" and sdata.get("videos"):
                import html as _html
                video_html = '\n<div class="video-results">\n<div class="video-results-header">🎬 为你推荐的教学视频</div>\n'
                for v in sdata["videos"][:4]:
                    title = _html.escape(v.get("title", "").replace('<em class="keyword">', "").replace("</em>", ""))
                    author = _html.escape(v.get("author", ""))
                    play = _html.escape(str(v.get("play_count", "")))
                    duration = _html.escape(str(v.get("duration", "")))
                    url = v.get("url", "#")
                    cover = v.get("cover", "")
                    cover_html = f'<img src="{_html.escape(cover)}" alt="{title}" loading="lazy" referrerpolicy="no-referrer" />' if cover else '<span>🎬</span>'
                    video_html += f'''<a class="video-card" href="{_html.escape(url)}" target="_blank" rel="noopener">
  <div class="video-cover">{cover_html}<span class="video-duration">{duration}</span></div>
  <div class="video-info">
    <div class="video-title" title="{title}">{title}</div>
    <div class="video-meta"><span class="meta-author">{author}</span><span class="meta-play">▶ {play}</span></div>
  </div>
</a>\n'''
                video_html += '</div>'
                skill_summary_parts.append(video_html)
            elif skill_name == "resource_orchestration" and sdata.get("resources"):
                resources_text = "\n### 已生成学习资源\n"
                for resource in sdata.get("resources", [])[:8]:
                    resources_text += f"- {resource.get('resource_type', 'resource')}：{resource.get('title', '')}\n"
                failures = sdata.get("failures") or []
                if failures:
                    resources_text += f"\n失败项：{len(failures)} 个，已保留成功生成的资源。"
                skill_summary_parts.append(resources_text)
            elif skill_name == "code_gen" and sdata.get("code"):
                generated_type = sdata.get("type", "code")
                task_desc = sdata.get("task_desc") or user_message
                if generated_type == "anime":
                    skill_summary_parts.append(f"\n### 可视化动画\n已生成可视化动画草稿。\n\n**生成主题**：{task_desc}")
                else:
                    skill_summary_parts.append(f"\n### 代码案例\n已生成代码案例草稿。\n\n**生成主题**：{task_desc}")

    llm_summary = ""
    if use_llm and (has_search or selected_skills):
        rag_context = ""
        try:
            from services.rag_service import search_rag
            rag_res = search_rag(user_message, state.get("user_id", ""), top_k=3)
            docs = rag_res.get("documents", [])
            if docs:
                rag_context = "\n\n学生已有学习资料：\n" + "\n---\n".join(d[:600] for d in docs[:3])
        except Exception:
            pass

        search_block = ""
        if has_search:
            search_block = f"""Tavily摘要：{answer}
搜索结果：
{chr(10).join([f"- {r.get('title', '')}: {r.get('snippet', '')[:300]}" for r in results[:5]])}
"""

        summary_prompt = f"""基于系统上下文和技能结果完成用户任务，输出简明但可执行的分析报告：

学生画像与系统模块上下文：{profile_text}
任务：{user_message}
{search_block}
技能执行结果：{_json_preview(_skill_results_for_summary(skill_results))}
真实错题本摘要：
{mistake_prompt_context or '当前没有可用错题摘要。'}
{rag_context}

要求：
- 如果技能结果包含 task_desc，必须以 task_desc 作为已生成内容的主题依据。
- 如果 code_preview 或代码内容看起来与 task_desc 明显不一致，必须明确提示“生成内容与规划主题不一致”，不要把错误主题当作成功结果总结。
- 如果任务涉及错题，必须基于错题本中的题目、学生答案、正确答案和知识点分析薄弱点。
- 如果已生成练习题，说明这些题如何对应错题暴露出的薄弱点。
- 如果系统上下文中对应列表为空，才可以提示暂无对应数据。
- 请回答任务问题并简短总结。

禁止输出任何 `[建议]`、`【建议】` 或类似建议按钮格式。"""

        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "汇总分析报告", "agent_name": "汇总智能体", "data": {"content": result_header}})
        if sse_queue:
            try: sse_queue.put_nowait(wf[-1])
            except Exception: pass
        async for token in _llm_stream("你是数据分析专家，基于搜索结果进行分析并报告。", summary_prompt):
            llm_summary += token
            te = {"type": "token", "step_id": step_id, "delta": token}
            wf.append(te)
            if sse_queue:
                try:
                    sse_queue.put_nowait(te)
                    from core.sse_registry import mark_live_token_step
                    mark_live_token_step(state.get("_session_id", ""), step_id)
                except Exception: pass

    if mistake_total > 0 and any(text in llm_summary for text in ["错题本为空", "没有历史错题", "暂无错题", "缺少错题内容"]):
        llm_summary = (
            "已读取到你的错题本记录。下面的分析基于上方“错题本依据”中的真实题目、学生答案、正确答案和知识点展开。\n\n"
            + mistake_prompt_context
        )

    final_md = result_header
    if llm_summary:
        llm_summary = _strip_suggestion_lines(llm_summary)
        final_md += f"\n\n### AI 分析\n{llm_summary}"
    for part in skill_summary_parts:
        final_md += part

    skill_names_display = {"deep_search": "深度搜索", "code_analysis": "代码分析", "code_gen": "代码/动画生成", "mindmap_gen": "思维导图", "quiz_gen": "习题生成", "video_search": "视频检索", "resource_orchestration": "多智能体资源编排"}
    stats_rows = "| 需求分析 | ✅ | 完成 |\n"
    for sname in selected_skills:
        sdata = skill_results.get(sname, {})
        status = "❌" if isinstance(sdata, dict) and sdata.get("error") else "✅"
        err = sdata.get("error", "")[:30] if isinstance(sdata, dict) else ""
        stats_rows += f"| {skill_names_display.get(sname, sname)} | {status} | {err or '完成'} |\n"

    final_md += f"\n### 执行统计\n| 步骤 | 状态 | 说明 |\n|------|------|------|\n{stats_rows}"

    wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "completed", "title": "汇总分析报告", "agent_name": "汇总智能体", "data": {"content": final_md}})
    return {"workflow_outputs": wf, "response": final_md, "all_modules_data": ad}


def build_agent_execute_graph():
    """构建 Agent 执行图：plan → skills → result"""
    b = StateGraph(AgentGraphState)
    b.add_node("plan", plan_node)
    b.add_node("skill_execute", skill_execute_node)
    b.add_node("resource_orchestration", resource_orchestration_graph)
    b.add_node("skill_collect", skill_collect_node)
    b.add_node("result", result_node)

    b.add_edge(START, "plan")
    b.add_conditional_edges("plan", _dispatch_skill_nodes, ["skill_execute", "resource_orchestration", "skill_collect"])
    b.add_edge("skill_execute", "skill_collect")
    b.add_edge("resource_orchestration", "result")
    b.add_edge("skill_collect", "result")
    b.add_edge("result", END)

    return b.compile()


agent_execute_graph = build_agent_execute_graph()
