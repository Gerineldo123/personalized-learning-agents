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


def _apply_skill_routing_guards(message: str, selected_skills: list, code_needed: bool, code_lang: str, code_desc: str):
    valid_skills = get_all_skills()
    normalized = [skill for skill in selected_skills if skill in valid_skills]

    if _requires_visual_code_artifact(message) and "code_gen" in valid_skills:
        normalized = [skill for skill in normalized if skill != "code_analysis"]
        if "code_gen" not in normalized:
            normalized.insert(0, "code_gen")
        code_needed = True
        code_lang = "html"
        code_desc = (code_desc or message).strip()

    return normalized, code_needed, code_lang, code_desc


def _requires_resource_orchestration(message: str) -> bool:
    text = (message or "").lower()
    create_terms = ["生成", "制作", "创建", "规划", "设计", "给我"]
    resource_terms = ["资源包", "多模态", "完整资源", "学习方案", "学习资料", "学习路径", "闭环资源"]
    return any(term in text for term in create_terms) and any(term in text for term in resource_terms)


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
    use_resource_orchestration = _requires_resource_orchestration(user_message)
    session_id = state.get("_session_id", "")
    sse_queue = _get_sse_queue(session_id)

    # 获取可用 skills 描述
    skills_desc = get_skills_description()

    if use_llm:
        profile_text = state.get("profile_text", "暂无画像")
        history = state.get("history", [])[-6:]
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

        user = f"""请对以下任务进行规划：

学生画像：{profile_text}
任务：{user_message}{history_text}

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
- 只有任务明确需要搜索外部资料时才选 deep_search
- 如果是简单概念解释、代码问题、直接推理可解决的任务，不需要 deep_search
- 如果任务涉及代码分析、解释、调试、优化，加入 code_analysis
- 如果任务需要生成代码示例、可视化动画、实操案例，加入 code_gen
- 如果任务需要知识梳理，加入 mindmap_gen
- 如果任务需要练习巩固，加入 quiz_gen
- 如果任务需要视频学习，加入 video_search
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

        try:
            if "{" in thinking_content and "}" in thinking_content:
                json_str = thinking_content[thinking_content.index("{"):thinking_content.rindex("}") + 1]
                plan_json = json.loads(json_str)
                search_keywords = plan_json.get("search_keywords", user_message)
                code_needed = plan_json.get("needs_code", False)
                code_lang = plan_json.get("code_lang", "python")
                code_desc = plan_json.get("code_desc", "")
                raw_skills = plan_json.get("selected_skills", [])
                # 校验 skill 名称有效性
                valid_skills = get_all_skills()
                selected_skills = [s for s in raw_skills if s in valid_skills]
                # 如果需要代码但没选任何代码相关 skill，默认 fallback 到 code_analysis
                if code_needed and "code_analysis" not in selected_skills and "code_gen" not in selected_skills:
                    selected_skills.append("code_analysis")
        except Exception:
            pass

        if _has_mistake_intent(user_message) and any(keyword in user_message for keyword in ["练习", "题", "巩固", "专项"]):
            if "quiz_gen" not in selected_skills and "quiz_gen" in get_all_skills():
                selected_skills.append("quiz_gen")

        selected_skills, code_needed, code_lang, code_desc = _apply_skill_routing_guards(
            user_message, selected_skills, code_needed, code_lang, code_desc
        )
        if use_resource_orchestration:
            selected_skills = ["resource_orchestration"]

        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "completed", "title": "分析任务需求", "agent_name": "规划智能体", "data": {"content": thinking_content}})
    else:
        thinking_content = f"分析任务：{user_message}"
        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "running", "title": "分析任务需求", "data": {"content": thinking_content}})
        selected_skills, code_needed, code_lang, code_desc = _apply_skill_routing_guards(
            user_message, selected_skills, code_needed, code_lang, code_desc
        )
        if use_resource_orchestration:
            selected_skills = ["resource_orchestration"]
        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "completed", "title": "分析任务需求", "agent_name": "规划智能体", "data": {"content": thinking_content}})

    execution_route = "resource_orchestration" if use_resource_orchestration else ("skill" if selected_skills else "direct_answer")
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
