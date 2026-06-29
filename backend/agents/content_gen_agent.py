import json
import re
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.resource import LearningResource
from services.safety_service import check_text, hallu_rules
from services.rag_service import index_resource
from services.kp_service import infer_resource_tags
from services.ppt_model_service import generate_ppt_json, is_ppt_model_configured


def _safe_json_loads(raw: str) -> dict:
    """解析 LLM 返回的 JSON，自动处理 LaTeX 反斜杠转义问题"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    # 始终预处理：将 $...$ / $$...$$ 公式内的 \指令 转义为合法 JSON
    preprocessed = _escape_math_backslashes(cleaned)
    return json.loads(preprocessed)


def _normalize_choice_options(options) -> list[str]:
    if not isinstance(options, list) or len(options) != 4:
        return []
    normalized: list[str] = []
    expected_keys = ["A", "B", "C", "D"]
    for index, option in enumerate(options):
        key = expected_keys[index]
        if isinstance(option, dict):
            raw_key = str(option.get("key") or key).strip().upper()[:1] or key
            text = str(option.get("text") or option.get("label") or "").strip()
            if raw_key in expected_keys:
                key = raw_key
        else:
            text = str(option or "").strip()
            if len(text) >= 2 and text[0].upper() in expected_keys and text[1] in ".．、)） ":
                key = text[0].upper()
                text = text[2:].strip()
        if not text:
            return []
        normalized.append(f"{key}. {text}")
    if {item[0] for item in normalized} != set(expected_keys):
        return []
    return sorted(normalized, key=lambda item: expected_keys.index(item[0]))


def _normalize_answer_key(answer, options: list[str]) -> str:
    raw = str(answer or "").strip()
    if raw[:1].upper() in {"A", "B", "C", "D"}:
        return raw[:1].upper()
    for option in options:
        if raw and (raw == option or raw == option[2:].strip()):
            return option[0]
    return ""


def _normalize_quiz_data(quiz_data: dict, question_count: int) -> dict:
    if not isinstance(quiz_data, dict):
        raise ValueError("题库生成结果不是合法 JSON 对象")
    questions = quiz_data.get("questions")
    if not isinstance(questions, list):
        raise ValueError("题库生成结果缺少 questions 数组")

    normalized_questions: list[dict] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        raw_type = str(item.get("type") or "").strip().lower()
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        if not question or not answer:
            continue

        if raw_type in {"coding", "code"}:
            test_cases = item.get("test_cases") if isinstance(item.get("test_cases"), list) else []
            if not item.get("function_signature") or len(test_cases) < 2:
                continue
            normalized_questions.append({
                **item,
                "type": "coding",
                "question": question,
                "answer": answer,
                "explanation": explanation,
                "test_cases": test_cases,
            })
            continue

        if raw_type in {"fill_blank", "blank", "short_answer", "short-answer", "简答题", "填空题"}:
            normalized_questions.append({
                **item,
                "type": "fill_blank",
                "question": question,
                "answer": answer,
                "explanation": explanation,
            })
            continue

        options = _normalize_choice_options(item.get("options"))
        answer_key = _normalize_answer_key(answer, options)
        if not options or not answer_key:
            continue
        normalized_questions.append({
            **item,
            "type": "single_choice",
            "question": question,
            "options": options,
            "answer": answer_key,
            "explanation": explanation,
        })

    normalized_questions = normalized_questions[:question_count]
    if not normalized_questions:
        raise ValueError("题库生成失败：没有可作答的有效题目")
    for index, question in enumerate(normalized_questions, start=1):
        question["id"] = index
    return {
        **quiz_data,
        "questions": normalized_questions,
    }


def _normalize_requested_question_types(raw_types) -> str:
    values = [item.strip().lower() for item in str(raw_types or "").split(",") if item.strip()]
    normalized: list[str] = []
    for value in values:
        if value in {"single_choice", "choice", "multiple_choice"}:
            normalized.append("single_choice")
        elif value in {"fill_blank", "blank", "short_answer"}:
            normalized.append("fill_blank")
        elif value in {"coding", "code"}:
            normalized.append("coding")
    if not normalized:
        normalized = ["single_choice"]
    return ",".join(dict.fromkeys(normalized))


_MATH_DISPLAY = re.compile(r'\$\$([^$]+)\$\$')
_MATH_INLINE = re.compile(r'\$([^$]+)\$')


def _escape_math_backslashes(text: str) -> str:
    """将 $...$ / $$...$$ 公式内的 \指令 转义为 \\指令，避免 JSON 将 \f \t \b 等误解为控制字符"""

    def _fix(m: re.Match) -> str:
        formula = m.group(1)
        delim = '$$' if m.group(0).startswith('$$') else '$'
        # 只修复未被转义的单反斜杠（LLM 已输出的 \\ 不处理）
        escaped = re.sub(r'(?<!\\)\\([a-zA-Z]+|[{}#_^&%$~])', r'\\\\\1', formula)
        return delim + escaped + delim
    # 先处理 $$...$$（display），再处理 $...$（inline）
    step1 = _MATH_DISPLAY.sub(_fix, text)
    return _MATH_INLINE.sub(_fix, step1)

ARTICLE_PROMPT = """你是一个知识讲解专家。根据学生画像和需求，生成一篇结构清晰的学习文章。

学生画像：{profile}
学习需求：{topic}

要求：
- 使用Markdown格式
- 包含标题、小节、示例、总结
- 难度适配学生的知识基础
- 500-1000字
- {hallu}"""

QUIZ_PROMPT = """你是一个高校课程教学评估专家。根据学生画像和知识点，生成一套适用于大学生的混合题型练习题。

学生画像：{profile}
知识点：{topic}
目标难度：{difficulty}
题目数量：{question_count}
题型要求：{question_types}
编程语言：{code_lang}

返回JSON格式（只允许 single_choice、fill_blank、coding 三种 type；每种题型示例如下）：
{{
  "title": "题目集标题",
  "questions": [
    {{
      "id": 1,
      "type": "single_choice",
      "question": "题目内容",
      "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"],
      "answer": "A",
      "explanation": "解析"
    }},
    {{
      "id": 2,
      "type": "fill_blank",
      "question": "在{{code_lang}}中，___关键字用于定义常量。",
      "answer": "根据语言填写",
      "explanation": "解析"
    }},
    {{
      "id": 3,
      "type": "coding",
      "question": "实现一个函数，返回列表中第k大的元素。",
      "function_signature": "根据{{code_lang}}语法提供函数签名",
      "code_lang": "{{code_lang}}",
      "test_cases": [
        {{{{"input": "[3,2,1,5,6,4], 2", "expected": "5"}}}},
        {{{{"input": "[3,2,3,1,2,4,5,5,6], 4", "expected": "4"}}}}
      ],
      "answer": "根据{{code_lang}}语法提供该语言的标准解法代码",
      "explanation": "排序后取第k个元素"
    }}
  ]
}}

出题规则：
- 题目必须符合"大学课程"层次，不得使用幼儿/小学级别常识题。
- 优先考察概念理解、原理推导、应用分析、综合判断。
- 题干要与知识点强相关，避免泛化空题。
- single_choice：选项应具有区分度，干扰项要合理。
- single_choice：必须提供4个options，格式为["A. xxx","B. xxx","C. xxx","D. xxx"]，answer只能是"A"/"B"/"C"/"D"。
- fill_blank：答案应为简短精确的词/短语/表达式，answer字段为标准答案。
- coding：编程题使用{{code_lang}}语言，必须提供可直接运行的完整函数，test_cases至少2个，input格式为函数参数字符串（如"nums, k"），expected为str(返回值)。同时提供answer字段的标准解法。
- explanation 给出关键理由，而不是仅重复答案。
- 按照题型要求"{question_types}"分配题目，若包含多种题型则均衡分布。
- 不要生成 multiple_choice、short_answer 或其它未列出的 type。
- 数学公式必须使用 LaTeX，并用 $...$ 包裹；例如 $\\lim_{{h\\to 0}} \\frac{{f(x_0+h)-f(x_0)}}{{h}}$。

生成 {question_count} 道题，整体难度按"{difficulty}"控制。{hallu}
只返回JSON，不要其他内容。"""

CODE_PROMPT = """你是一个编程教学专家。根据学生画像和知识点，生成代码教学案例。

学生画像：{profile}
知识点：{topic}
编程语言：{code_lang}

要求：
- 使用{code_lang}语言编写完整的可运行代码示例
- 逐行注释解释关键逻辑
- 难度适配学生水平（{level}）
- 使用Markdown代码块格式
- 包含运行结果说明
- {hallu}"""

PPT_PROMPT = """你是一个课件设计专家。根据学生画像和知识点，生成一份结构化的PPT课件内容。

学生画像：{profile}
主题：{topic}

返回JSON格式：
{{
  "title": "课件标题",
  "slides": [
    {{"title": "幻灯片标题", "content": ["要点1", "要点2"], "notes": "讲师备注"}}
  ]
}}
生成5-8张幻灯片。{hallu}
只返回JSON，不要其他内容。"""


class ContentGenAgent(BaseAgent):
    name = "content_gen"
    description = "生成个性化学习资源：PPT、题库、代码案例、阅读材料"

    OUTPUT_HANDLERS = {
        "ppt": "_generate_ppt",
        "quiz": "_generate_quiz",
        "article": "_generate_article",
        "code": "_generate_code_case",
    }

    async def process(self, state: AgentState) -> AgentState:
        resource_type = state.get("resource_type", "article")
        handler_name = self.OUTPUT_HANDLERS.get(resource_type, "_generate_article")
        handler = getattr(self, handler_name)
        await handler(state)
        return state

    async def _generate_article(self, state: AgentState):
        message = state.user_message
        profile = self._profile_text(state)
        resp = await chat_completion([
            {"role": "user", "content": ARTICLE_PROMPT.format(profile=profile, topic=message, hallu=hallu_rules())}
        ], temperature=0.7)
        content = resp.choices[0].message.content
        safe_content, _ = await check_text(content)
        self._save_resource(state, "article", safe_content)
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "article", "content": safe_content
        }, ensure_ascii=False)

    async def _generate_quiz(self, state: AgentState):
        message = state.user_message
        profile = self._profile_text(state)
        question_count = int(state.get("question_count", 5) or 5)
        question_count = max(3, min(question_count, 30))
        difficulty = str(state.get("difficulty", "中等") or "中等")
        raw_types = state.get("question_types", "single_choice")
        question_types = _normalize_requested_question_types(raw_types)
        code_lang = str(state.get("code_language", "python") or "python")
        resp = await chat_completion([
            {"role": "user", "content": QUIZ_PROMPT.format(
                profile=profile,
                topic=message,
                question_count=question_count,
                difficulty=difficulty,
                question_types=question_types,
                code_lang=code_lang,
                hallu=hallu_rules(),
            )}
        ], temperature=0.5)
        raw = resp.choices[0].message.content.strip()
        quiz_data = _safe_json_loads(raw)
        safe_quiz, _ = await check_text(json.dumps(quiz_data, ensure_ascii=False))
        if safe_quiz != json.dumps(quiz_data, ensure_ascii=False):
            quiz_data = {"title": "内容已过滤", "questions": []}
        elif isinstance(quiz_data, dict) and isinstance(quiz_data.get("questions"), list):
            quiz_data = _normalize_quiz_data(quiz_data, question_count)
        self._save_resource(state, "quiz", quiz_data)
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "quiz", "content": quiz_data
        }, ensure_ascii=False)

    async def _generate_code_case(self, state: AgentState):
        message = state.user_message
        profile = self._profile_text(state)
        code_lang = str(state.get("code_language", "python") or "python")
        kb = state.profile.knowledge_base if state.profile else {}
        level = "初级"
        for name, score in kb.items():
            if score >= 0.7:
                level = "高级"
            elif score >= 0.4 and level == "初级":
                level = "中级"
        resp = await chat_completion([
            {"role": "user", "content": CODE_PROMPT.format(profile=profile, topic=message, code_lang=code_lang, level=level, hallu=hallu_rules())}
        ], temperature=0.5)
        content = resp.choices[0].message.content
        safe_content, _ = await check_text(content)
        self._save_resource(state, "code", {"code": safe_content, "language": code_lang})
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "code", "content": safe_content
        }, ensure_ascii=False)

    async def _generate_ppt(self, state: AgentState):
        message = state.user_message
        profile = self._profile_text(state)

        # First choice: a dedicated PPT model API configured under /api/config/ppt.
        if is_ppt_model_configured():
            try:
                ppt_data = await generate_ppt_json(message, profile, user_id=state.user_id or "default")
                safe_ppt, _ = await check_text(json.dumps(ppt_data, ensure_ascii=False))
                if safe_ppt != json.dumps(ppt_data, ensure_ascii=False):
                    ppt_data = {"title": "内容已过滤", "slides": []}
                if not ppt_data.get("pptx_url"):
                    ppt_data = await self._attach_pptx(ppt_data)
                self._save_resource(state, "ppt", ppt_data)
                state["response"] = json.dumps({
                    "agent": self.name,
                    "resource_type": "ppt",
                    "content": ppt_data,
                    "model_source": "ppt_model_api",
                }, ensure_ascii=False)
                return
            except Exception as exc:
                raise RuntimeError(f"PPT API 生成失败：{exc}") from exc

        # 优先使用 PptGenSkill（支持 .pptx 导出）
        try:
            from agents.skills import get_skill
            from services.config_service import is_configured as _is_configured
            skill = get_skill("ppt_gen")
            if skill:
                result = await skill.execute({
                    "user_message": message,
                    "user_id": state.user_id,
                    "profile": state.get("profile"),
                }, [])
                if result.success and result.data.get("ppt_json"):
                    ppt_data = result.data["ppt_json"]
                    pptx_url = result.data.get("pptx_url", "")
                    if pptx_url:
                        ppt_data["pptx_url"] = pptx_url
                        try:
                            import os
                            ppt_data["pptx_file"] = os.path.basename(pptx_url)
                        except Exception:
                            pass
                    self._save_resource(state, "ppt", ppt_data)
                    state["response"] = json.dumps({
                        "agent": self.name,
                        "resource_type": "ppt",
                        "content": ppt_data,
                        "pptx_url": pptx_url,
                        "skill_used": "ppt_gen",
                    }, ensure_ascii=False)
                    return
        except Exception:
            pass

        # fallback：使用通用 LLM
        resp = await chat_completion([
            {"role": "user", "content": PPT_PROMPT.format(profile=profile, topic=message, hallu=hallu_rules())}
        ], temperature=0.5)
        raw = resp.choices[0].message.content.strip()
        ppt_data = _safe_json_loads(raw)
        safe_ppt, _ = await check_text(json.dumps(ppt_data, ensure_ascii=False))
        if safe_ppt != json.dumps(ppt_data, ensure_ascii=False):
            ppt_data = {"title": "内容已过滤", "slides": []}
        ppt_data = await self._attach_pptx(ppt_data)
        self._save_resource(state, "ppt", ppt_data)
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "ppt", "content": ppt_data
        }, ensure_ascii=False)

    async def _attach_pptx(self, ppt_data: dict) -> dict:
        try:
            from services.ppt_service import generate_pptx
            result = await generate_pptx(ppt_data)
            pptx_path = result.get("pptx_path", "")
            if pptx_path:
                import os
                filename = os.path.basename(pptx_path)
                ppt_data["pptx_file"] = filename
                ppt_data["pptx_url"] = f"/static/ppt/{filename}"
        except Exception:
            pass
        return ppt_data

    def _profile_text(self, state: AgentState) -> str:
        profile_context = state.get("profile_context")
        if profile_context:
            return str(profile_context)
        p = state.get("profile")
        if not p:
            return "暂无学生画像"
        return (
            f"专业：{p.major or '未知'}，年级：{p.grade or '未知'}，"
            f"知识基础：{json.dumps(p.knowledge_base or {}, ensure_ascii=False)}，"
            f"学习目标：{p.learning_goal or '无'}"
        )

    def _save_resource(self, state: AgentState, resource_type: str, content):
        prev_id = state.get("resource_db_id")
        title = self._extract_title(content, resource_type)
        text = " ".join([
            str(state.get("user_message", "")),
            title,
            json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content),
        ])
        graph_tags = infer_resource_tags(
            text,
            course_name=state.get("course_name"),
            knowledge_points=state.get("knowledge_points") or [],
        )
        tags = list(dict.fromkeys(
            [resource_type]
            + [x for x in [graph_tags.get("course_name")] if x]
            + list(graph_tags.get("knowledge_points") or [])
        ))
        db = SessionLocal()
        try:
            resource = LearningResource(
                user_id=state.user_id,
                resource_type=resource_type,
                title=title,
                content=content if isinstance(content, dict) else {"text": content},
                tags=tags,
                course_name=graph_tags.get("course_name"),
                knowledge_points=graph_tags.get("knowledge_points") or [],
                kp_weights=graph_tags.get("kp_weights") or {},
                tag_confidence=graph_tags.get("tag_confidence") or 0,
            )
            db.add(resource)
            db.flush()
            db.commit()

            if resource_type == "ppt":
                try:
                    from services.ppt_preview_service import schedule_ppt_preview
                    schedule_ppt_preview(resource.id)
                except Exception:
                    pass

            text = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
            index_resource(resource.id, state.user_id or "", text[:4000], resource_type)
            if not prev_id:
                state["resource_db_id"] = resource.id
            state["resource_title"] = title
        finally:
            db.close()

    def _extract_title(self, content, resource_type: str) -> str:
        topic = ""
        if isinstance(content, dict):
            topic = content.get("title", "")
        elif isinstance(content, str):
            text = content[:100]
            if text.startswith("# "):
                topic = text.split("\n")[0].replace("# ", "").strip()
        return topic or f"{resource_type}_resource"


if __name__ == "__main__":
    import sys, asyncio
    sys.stdout.reconfigure(encoding="utf-8")
    agent = ContentGenAgent()
    state = AgentState(user_id="test", user_message="Python装饰器", resource_type="article")
    result = asyncio.run(agent.process(state))
    print(result.get("response", "")[:300])

