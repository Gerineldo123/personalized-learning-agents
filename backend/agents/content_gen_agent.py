import json
import re
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.resource import LearningResource
from services.safety_service import check_text, hallu_rules
from services.rag_service import index_resource


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

QUIZ_PROMPT = """你是一个高校课程教学评估专家。根据学生画像和知识点，生成一套适用于大学生的练习题。

学生画像：{profile}
知识点：{topic}
目标难度：{difficulty}
题目数量：{question_count}

返回JSON格式：
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
    }}
  ]
}}

出题规则：
- 题目必须符合“大学课程”层次，不得使用幼儿/小学级别常识题（如“apple是什么意思”）。
- 优先考察概念理解、原理推导、应用分析、综合判断，不要只考词汇记忆。
- 题干要与知识点强相关，避免泛化空题。
- 选项应具有区分度，干扰项要合理。
- explanation 给出关键理由，而不是仅重复答案。
- 若 topic 明确是“大学英语/学术英语”场景，也必须使用大学层次语境（学术阅读、语法辨析、语篇理解），不得出现低龄词汇释义题。

生成 {question_count} 道题，整体难度按“{difficulty}”控制。{hallu}
只返回JSON，不要其他内容。"""

CODE_PROMPT = """你是一个编程教学专家。根据学生画像和知识点，生成代码教学案例。

学生画像：{profile}
知识点：{topic}

要求：
- 包含完整的可运行代码示例
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
        resp = await chat_completion([
            {"role": "user", "content": QUIZ_PROMPT.format(
                profile=profile,
                topic=message,
                question_count=question_count,
                difficulty=difficulty,
                hallu=hallu_rules(),
            )}
        ], temperature=0.5)
        raw = resp.choices[0].message.content.strip()
        quiz_data = _safe_json_loads(raw)
        safe_quiz, _ = await check_text(json.dumps(quiz_data, ensure_ascii=False))
        if safe_quiz != json.dumps(quiz_data, ensure_ascii=False):
            quiz_data = {"title": "内容已过滤", "questions": []}
        elif isinstance(quiz_data, dict) and isinstance(quiz_data.get("questions"), list):
            quiz_data["questions"] = quiz_data["questions"][:question_count]
        self._save_resource(state, "quiz", quiz_data)
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "quiz", "content": quiz_data
        }, ensure_ascii=False)

    async def _generate_code_case(self, state: AgentState):
        message = state.user_message
        profile = self._profile_text(state)
        kb = state.profile.knowledge_base if state.profile else {}
        level = "初级"
        for name, score in kb.items():
            if score >= 0.7:
                level = "高级"
            elif score >= 0.4 and level == "初级":
                level = "中级"
        resp = await chat_completion([
            {"role": "user", "content": CODE_PROMPT.format(profile=profile, topic=message, level=level, hallu=hallu_rules())}
        ], temperature=0.5)
        content = resp.choices[0].message.content
        safe_content, _ = await check_text(content)
        self._save_resource(state, "code", {"code": safe_content, "language": "python"})
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "code", "content": safe_content
        }, ensure_ascii=False)

    async def _generate_ppt(self, state: AgentState):
        message = state.user_message
        profile = self._profile_text(state)
        resp = await chat_completion([
            {"role": "user", "content": PPT_PROMPT.format(profile=profile, topic=message, hallu=hallu_rules())}
        ], temperature=0.5)
        raw = resp.choices[0].message.content.strip()
        ppt_data = _safe_json_loads(raw)
        safe_ppt, _ = await check_text(json.dumps(ppt_data, ensure_ascii=False))
        if safe_ppt != json.dumps(ppt_data, ensure_ascii=False):
            ppt_data = {"title": "内容已过滤", "slides": []}
        self._save_resource(state, "ppt", ppt_data)
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "ppt", "content": ppt_data
        }, ensure_ascii=False)

    def _profile_text(self, state: AgentState) -> str:
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
        db = SessionLocal()
        try:
            resource = LearningResource(
                user_id=state.user_id,
                resource_type=resource_type,
                title=title,
                content=content if isinstance(content, dict) else {"text": content},
                tags=[resource_type],
            )
            db.add(resource)
            db.flush()
            db.commit()

            text = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
            index_resource(resource.id, state.user_id or "", text[:4000], resource_type)
            if not prev_id:
                state["resource_db_id"] = resource.id
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

