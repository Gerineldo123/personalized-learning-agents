import json
import uuid
from langgraph.graph import StateGraph, START, END
from graph.state import AgentGraphState
from agents.tools import tavily_search
from agents.skills import get_skill, get_all_skills, get_skills_description, SkillResult


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
- 如果任务涉及编程，加入 code_analysis
- 如果任务需要知识梳理，加入 mindmap_gen
- 如果任务需要练习巩固，加入 quiz_gen
- 如果任务需要视频学习，加入 video_search
- selected_skills 可以为空数组（表示直接用LLM回答）"""

        async for token in _llm_stream(system, user):
            thinking_content += token
            wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "running", "title": "分析任务需求", "data": {"content": thinking_content}})

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
                # 如果需要代码但没选 code_analysis，自动加入
                if code_needed and "code_analysis" not in selected_skills:
                    selected_skills.append("code_analysis")
        except Exception:
            pass

        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "completed", "title": "分析任务需求", "data": {"content": thinking_content}})
    else:
        thinking_content = f"分析任务：{user_message}"
        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "running", "title": "分析任务需求", "data": {"content": thinking_content}})
        wf.append({"type": "step", "step_type": "thinking", "step_id": step_id, "status": "completed", "title": "分析任务需求", "data": {"content": thinking_content}})

    return {
        **state,
        "workflow_outputs": wf,
        "all_modules_data": {
            **(state.get("all_modules_data") or {}),
            "search_keywords": search_keywords,
            "code_needed": code_needed,
            "code_lang": code_lang,
            "code_desc": code_desc,
            "selected_skills": selected_skills,
        },
    }


async def skills_node(state: AgentGraphState) -> AgentGraphState:
    """Skills 执行节点：按顺序执行 plan 选定的 skills"""
    user_message = state.get("user_message", "")
    user_id = state.get("user_id", "")
    wf = state.get("workflow_outputs", [])
    ad = state.get("all_modules_data") or {}
    selected_skills = ad.get("selected_skills", ["deep_search"])

    skill_results = {}
    context = {
        "user_message": user_message,
        "user_id": user_id,
        "all_modules_data": ad,
        "profile": state.get("profile"),
    }

    for skill_name in selected_skills:
        skill = get_skill(skill_name)
        if not skill:
            continue
        try:
            result = await skill.execute(context, wf)
            skill_results[skill_name] = result.data if result.success else {"error": result.error}

            # 将 deep_search 结果写入 all_modules_data 供后续 result 节点使用
            if skill_name == "deep_search" and result.success:
                ad["search_result"] = {
                    "results": result.data.get("search_results", []),
                    "answer": result.data.get("answer", ""),
                    "query": ad.get("search_keywords", user_message),
                }
                # 更新 context 以便后续 skill 可使用搜索结果
                context["all_modules_data"] = ad
        except Exception as e:
            skill_results[skill_name] = {"error": str(e)}

    ad["skill_results"] = skill_results

    return {
        **state,
        "workflow_outputs": wf,
        "all_modules_data": ad,
    }


async def result_node(state: AgentGraphState) -> AgentGraphState:
    """结果汇总节点：整合所有 skill 执行结果生成最终报告"""
    user_message = state.get("user_message", "")
    wf = state.get("workflow_outputs", [])
    ad = state.get("all_modules_data") or {}
    search_result = ad.get("search_result", {})
    skill_results = ad.get("skill_results", {})
    selected_skills = ad.get("selected_skills", [])
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

        direct_prompt = f"""学生画像：{profile_text}
任务/问题：{user_message}{history_text}{rag_context}

请直接回答上述问题，使用Markdown格式，包含必要的代码块和公式。

【主动建议规则】回答末尾可根据情况附加一条建议（格式：[建议] 内容）：
- 涉及系统学习某主题 → [建议] 系统学习【主题】
- 涉及错题复习 → [建议] 分析错题
- 涉及水平评估 → [建议] 学习评估
- 涉及视频学习 → [建议] 搜索视频【主题】
没有合适情况则不写建议。"""

        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "AI 回答", "data": {"content": ""}})
        final_md = ""
        if use_llm:
            async for token in _llm_stream("你是个性化学习AI助手，根据学生画像给出精准、有深度的回答。", direct_prompt):
                final_md += token
                wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "AI 回答", "data": {"content": final_md}})
        else:
            final_md = f"**{user_message}**\n\n（LLM 未配置，无法回答）"

        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "completed", "title": "AI 回答", "data": {"content": final_md}})
        return {**state, "workflow_outputs": wf, "response": final_md, "all_modules_data": ad}

    # ── 有 skill 模式：整合各 skill 结果 ──
    has_search = "deep_search" in selected_skills and results

    result_header = f"## {user_message}\n\n"
    if has_search:
        result_header += f"### 搜索摘要\n{answer or '（未获取AI摘要）'}\n\n### 相关资源\n"
        for r in results[:5]:
            result_header += f"\n- **[{r.get('title', '链接')}]({r.get('url', '#')})**"

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
                video_text = "\n### 推荐视频\n"
                for v in sdata["videos"][:3]:
                    title = v.get("title", "").replace('<em class="keyword">', "").replace("</em>", "")
                    video_text += f"\n- **[{title}]({v.get('url', '#')})** {v.get('author', '')} {v.get('play_count', '')}\n"
                skill_summary_parts.append(video_text)

    llm_summary = ""
    if use_llm and has_search:
        rag_context = ""
        try:
            from services.rag_service import search_rag
            rag_res = search_rag(user_message, state.get("user_id", ""), top_k=3)
            docs = rag_res.get("documents", [])
            if docs:
                rag_context = "\n\n学生已有学习资料：\n" + "\n---\n".join(d[:600] for d in docs[:3])
        except Exception:
            pass

        summary_prompt = f"""将搜索结果整合为简明分析报告（300字以内）：

学生画像：{profile_text}
任务：{user_message}
Tavily摘要：{answer}
搜索结果：
{chr(10).join([f"- {r.get('title', '')}: {r.get('snippet', '')[:300]}" for r in results[:5]])}
{rag_context}

请回答任务问题并简短总结。

【主动建议规则】回答末尾可附加一条建议（格式：[建议] 内容）：
- 系统学习 → [建议] 系统学习【主题】  分析错题 → [建议] 分析错题
- 学习评估 → [建议] 学习评估  视频学习 → [建议] 搜索视频【主题】"""

        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "汇总分析报告", "data": {"content": result_header}})
        async for token in _llm_stream("你是数据分析专家，基于搜索结果进行分析并报告。", summary_prompt):
            llm_summary += token
            wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "汇总分析报告", "data": {"content": result_header + "\n\n### AI 分析\n" + llm_summary}})

    final_md = result_header
    if llm_summary:
        final_md += f"\n\n### AI 分析\n{llm_summary}"
    for part in skill_summary_parts:
        final_md += part

    skill_names_display = {"deep_search": "深度搜索", "code_analysis": "代码生成", "mindmap_gen": "思维导图", "quiz_gen": "习题生成", "video_search": "视频检索"}
    stats_rows = "| 需求分析 | ✅ | 完成 |\n"
    for sname in selected_skills:
        sdata = skill_results.get(sname, {})
        status = "❌" if isinstance(sdata, dict) and sdata.get("error") else "✅"
        err = sdata.get("error", "")[:30] if isinstance(sdata, dict) else ""
        stats_rows += f"| {skill_names_display.get(sname, sname)} | {status} | {err or '完成'} |\n"

    final_md += f"\n### 执行统计\n| 步骤 | 状态 | 说明 |\n|------|------|------|\n{stats_rows}"

    wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "completed", "title": "汇总分析报告", "data": {"content": final_md}})
    return {**state, "workflow_outputs": wf, "response": final_md, "all_modules_data": ad}


def build_agent_execute_graph():
    """构建 Agent 执行图：plan → skills → result"""
    b = StateGraph(AgentGraphState)
    b.add_node("plan", plan_node)
    b.add_node("skills", skills_node)
    b.add_node("result", result_node)

    b.add_edge(START, "plan")
    b.add_edge("plan", "skills")
    b.add_edge("skills", "result")
    b.add_edge("result", END)

    return b.compile()


agent_execute_graph = build_agent_execute_graph()
