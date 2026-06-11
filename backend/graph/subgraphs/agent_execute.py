import json
import uuid
from langgraph.graph import StateGraph, START, END
from graph.state import AgentGraphState
from agents.tools import tavily_search


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

    if use_llm:
        system = "你是一个AI Agent任务规划器。收到任务后输出JSON配置和计划说明。先输出计划文本，最后用JSON块输出配置。"
        user = f"""请对以下任务进行规划：

任务：{user_message}

输出要求：
1. 先用1-2句话分析任务
2. 列出3-5个执行步骤（每行一个）
3. 输出一个JSON块：{{"search_keywords": "精准搜索短语", "needs_code": true/false, "code_lang": "python|javascript", "code_desc": "代码描述"}}
注意：search_keywords 是2-4个核心词的短语（用空格分隔代表"与"关系），不要用逗号或长句"""

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
        },
    }


def _merge_search_results(primary: dict, secondary: dict) -> dict:
    seen_urls = set()
    merged = []
    for r in primary.get("results", []) + secondary.get("results", []):
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(r)
    answer = primary.get("answer", "") or secondary.get("answer", "")
    return {"query": primary.get("query", ""), "answer": answer, "results": merged, "error": primary.get("error", "")}


async def search_node(state: AgentGraphState) -> AgentGraphState:
    user_message = state.get("user_message", "")
    wf = state.get("workflow_outputs", [])
    ad = state.get("all_modules_data") or {}
    search_keywords = ad.get("search_keywords", user_message)

    cn_platforms = [
        "bilibili.com", "icourse163.org", "xuetangx.com", "zhihu.com",
        "csdn.net", "cnblogs.com", "juejin.cn", "segmentfault.com",
        "jianshu.com", "cnki.net", "developer.aliyun.com",
    ]

    query_phrase = search_keywords.replace("，", " ").replace(",", " ").strip()
    query_phrase = " ".join(query_phrase.split())

    step_id = str(uuid.uuid4())[:8]
    title = f"Tavily Search: {query_phrase[:40]}"
    wf.append({"type": "step", "step_type": "search", "step_id": step_id, "status": "running", "title": title, "data": {"query": query_phrase, "results": [], "answer": ""}})

    kw_result = await tavily_search(query_phrase, max_results=5, include_domains=cn_platforms)
    msg_result = await tavily_search(user_message, max_results=3, include_domains=cn_platforms)

    search_result = _merge_search_results(kw_result, msg_result)

    if search_result.get("error"):
        print(f"[Tavily Error] {search_result['error']}")

    if len(search_result.get("results", [])) == 0:
        search_result["error"] = "中文平台未找到结果，请尝试更具体的关键词"

    wf.append({"type": "step", "step_type": "search", "step_id": step_id, "status": "completed", "title": title, "data": search_result})

    return {
        **state,
        "workflow_outputs": wf,
        "all_modules_data": {**ad, "search_result": search_result},
    }


async def memory_node(state: AgentGraphState) -> AgentGraphState:
    wf = state.get("workflow_outputs", [])
    ad = state.get("all_modules_data") or {}
    search_result = ad.get("search_result", {})
    result_count = len(search_result.get("results", []))

    step_id = str(uuid.uuid4())[:8]
    wf.append({"type": "step", "step_type": "memory", "step_id": step_id, "status": "completed", "title": "处理搜索结果", "data": {"action": "write", "key": "search_results", "value": f"已获取 {result_count} 条搜索结果，正在整合分析..."}})

    return {
        **state,
        "workflow_outputs": wf,
        "all_modules_data": ad,
    }


async def code_node(state: AgentGraphState) -> AgentGraphState:
    user_message = state.get("user_message", "")
    wf = state.get("workflow_outputs", [])
    ad = state.get("all_modules_data") or {}
    search_result = ad.get("search_result", {})
    code_needed = ad.get("code_needed", False)
    code_lang = ad.get("code_lang", "python")
    code_desc = ad.get("code_desc", "")

    step_id = str(uuid.uuid4())[:8]

    if code_needed and code_desc:
        code_content = ""
        code_prompt = f"只输出代码，不要解释。\n{code_desc}\n任务上下文：{user_message}\n搜索结果：{search_result.get('answer', '')[:300]}"

        async for token in _llm_stream("你是一个代码专家，只输出可执行代码，不要包含markdown标记。", code_prompt):
            code_content += token
            wf.append({"type": "step", "step_type": "code", "step_id": step_id, "status": "running", "title": f"代码实现 ({code_lang})", "data": {"language": code_lang, "code": code_content, "output": "", "status": "running"}})

        clean_code = code_content.strip("`").removeprefix("python").removeprefix("javascript").strip()
        wf.append({"type": "step", "step_type": "code", "step_id": step_id, "status": "completed", "title": f"代码实现 ({code_lang})", "data": {"language": code_lang, "code": clean_code, "output": "代码已生成，可在实际环境中运行验证", "status": "completed"}})
    else:
        ad["code_needed"] = False

    return {
        **state,
        "workflow_outputs": wf,
        "all_modules_data": ad,
    }


async def result_node(state: AgentGraphState) -> AgentGraphState:
    user_message = state.get("user_message", "")
    wf = state.get("workflow_outputs", [])
    ad = state.get("all_modules_data") or {}
    search_result = ad.get("search_result", {})
    code_needed = ad.get("code_needed", False)

    results = search_result.get("results", [])
    answer = search_result.get("answer", "")
    use_llm = True
    try:
        from services.config_service import is_configured
        use_llm = is_configured("main")
    except Exception:
        use_llm = False

    step_id = str(uuid.uuid4())[:8]
    result_header = f"""## 任务执行报告

### 任务描述
{user_message}

### 搜索摘要
{answer or '（未获取AI摘要）'}

### 相关资源
"""
    for i, r in enumerate(results[:5]):
        result_header += f"\n- **[{r.get('title', '链接')}]({r.get('url', '#')})**"

    if use_llm and results:
        summary_prompt = f"""将搜索结果整合为一份简明分析报告（300字以内），直接回答以下任务：

任务：{user_message}

Tavily AI摘要：{answer}

搜索结果：
{chr(10).join([f"- {r.get('title', '')}: {r.get('snippet', '')[:300]}" for r in results[:5]])}

请先用搜索数据回答任务问题，然后做简短总结。"""
        wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "汇总分析报告", "data": {"content": result_header}})

        llm_summary = ""
        async for token in _llm_stream("你是数据分析专家，基于搜索结果的精华部分进行分析并报告。", summary_prompt):
            llm_summary += token
            wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "running", "title": "汇总分析报告", "data": {"content": result_header + "\n\n### AI 分析\n" + llm_summary}})
    else:
        if not results:
            result_header += "\n\n⚠️ 搜索未返回结果，请检查 Tavily API 配置或尝试更换查询关键词。"
        llm_summary = ""

    final_md = result_header
    if llm_summary:
        final_md += f"\n\n### AI 分析\n{llm_summary}"

    final_md += f"""
### 执行统计
| 步骤 | 状态 | 说明 |
|------|------|------|
| 需求分析 | ✅ | 完成 |
| 资料搜索 | ✅ | 返回 {len(results)} 条结果 |
| {'代码生成' if code_needed else '代码生成'} | {'✅' if code_needed else '⏭️'} | {'LLM动态生成' if code_needed else '无需代码'} |
| 报告汇总 | ✅ | 完成 |
"""
    wf.append({"type": "step", "step_type": "result", "step_id": step_id, "status": "completed", "title": "汇总分析报告", "data": {"content": final_md}})

    return {
        **state,
        "workflow_outputs": wf,
        "response": final_md,
        "all_modules_data": ad,
    }


def build_agent_execute_graph():
    b = StateGraph(AgentGraphState)
    b.add_node("plan", plan_node)
    b.add_node("search", search_node)
    b.add_node("memory", memory_node)
    b.add_node("code", code_node)
    b.add_node("result", result_node)

    b.add_edge(START, "plan")
    b.add_edge("plan", "search")
    b.add_edge("search", "memory")
    b.add_edge("memory", "code")
    b.add_edge("code", "result")
    b.add_edge("result", END)

    return b.compile()


agent_execute_graph = build_agent_execute_graph()
