import json
import re
from typing import AsyncGenerator
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from services.safety_service import check_text, hallu_rules
from services.rag_service import search_rag

SYSTEM_PROMPT = """你是“智途”个性化学习智能体系统的 AI 助手。

【核心规则 - 必须严格遵守】
每次回答中，你必须将所有学科专业术语用双方括号标记：[[术语名称]]。
这是强制性格式要求，是系统功能的一部分，请不要忽略。

标记范围：
- 数学：[[微积分]]、[[导数]]、[[矩阵]]、[[傅里叶变换]]
- 物理：[[高斯定理]]、[[电场]]、[[库仑定律]]、[[麦克斯韦方程组]]
- 计算机：[[算法]]、[[数据结构]]、[[时间复杂度]]
- 以及任何教科书/论文中公认的专业术语

不要标记：
- 普通日常词汇（"学习"、"理解"、"问题"等）
- LaTeX 数学公式中的符号（\\mathbf、\\frac 等）
- 已经在代码块/公式块中的内容

你可以帮助学生解答各种学习问题、提供知识讲解、进行学习规划讨论等。
如果你认为需要构建画像、生成学习资源、规划路径等，可以建议用户说明需求。

【回答格式要求 — 请参照以下模板组织你的回答】

使用 ### 作为小节标题，用 --- 分隔不同小节。整体结构清晰、层级分明。

涉及代码时，必须：
- 使用围栏代码块 ```语言名 标记语言类型
- 代码用空格缩进（不用 Tab），每行适当换行，确保可直接复制运行
- 在关键行添加简洁注释，示例：students.append("David")  # 在末尾追加
- 输出示例用 # 注释标注在 print 语句旁边
- 代码块之后紧跟一个 **要点解析** 小节，用 - 列表逐条解释关键知识点

涉及概念对比或信息汇总时，优先使用 Markdown 表格。表格必须使用标准 Markdown 多行格式：
- 表头、分隔行、每一行数据都必须单独换行
- 不要把整张表压成一行
- 不要使用 `||` 表示换行

回答末尾可根据情况添加：
- **扩展思考**：与本知识点相关的进阶话题或跨学科联系
- 进一步学习的建议，引导学生继续探索

重要：禁止输出任何 `[建议]`、`【建议】` 或类似可点击建议按钮的标记。需要工具完成的任务由前端任务模式入口承接。

{hallu}

学生画像与系统模块上下文：{profile}

【系统数据使用要求】
- 上下文中包含系统已读取到的错题本、学习资源、学习路径、知识图谱和专注记录。
- 当这些列表非空时，不要回答“没有具体错题内容”或“无法访问资源/路径/图谱”。
- 分析错题时必须引用错题本中的题目、学生答案、正确答案和知识点。
- 使用预制课程知识库内容时，在相关段落末尾用“资料依据：课程·章节”标注来源；没有资料时不得编造引用。
- 如果检索资料正文明确包含问题答案，必须说明知识库已提供该信息并据此回答；禁止一边引用资料，一边声称“知识库未直接提供”。
- 只有在下方没有出现“资料检索状态：已命中”时，才可以说明未命中预制课程资料。

{rag_context}
"""


class ChatAgent(BaseAgent):
    name = "chat"
    description = "通用 AI 对话助手，回答学习问题、提供知识讲解"

    async def process(self, state: AgentState) -> AgentState:
        return state

    async def stream(self, state: AgentState) -> AsyncGenerator[str, None]:
        profile_text = self._profile_text(state)
        history = state.get("history", [])[-20:]
        rag_context = self._build_rag_context(state)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(profile=profile_text, hallu=hallu_rules(), rag_context=rag_context)},
        ]
        for h in history:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": state.user_message})

        stream_resp = await chat_completion(messages, temperature=0.4, stream=True)

        collected = ""
        async for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if not delta.content:
                continue
            collected += delta.content
            yield delta.content
        state["response"] = collected

    def _profile_text(self, state: AgentState) -> str:
        user_id = state.get("user_id", "")
        try:
            from core.database import SessionLocal
            from models.student import StudentProfile
            from services.agent_context_service import build_agent_context, build_agent_context_text
            db = SessionLocal()
            try:
                profile = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
                return build_agent_context_text(build_agent_context(db, user_id, profile))
            finally:
                db.close()
        except Exception:
            p = state.get("profile")
            if not p:
                return "暂无学生画像"
            return json.dumps({
                "专业": p.major,
                "年级": p.grade,
                "知识基础": p.knowledge_base,
                "薄弱知识点": p.weak_points,
                "学习目标": p.learning_goal,
            }, ensure_ascii=False)

    def _build_rag_context(self, state: AgentState) -> str:
        try:
            query = self._rag_query(state.user_message)
            results = search_rag(query, state.get("user_id", ""), top_k=6)
            docs = results.get("documents", [])
            if not docs:
                return ""
            sources = results.get("sources", [])
            ranked = sorted(
                [
                    (document, sources[index] if index < len(sources) else {})
                    for index, document in enumerate(docs)
                ],
                key=lambda item: self._rag_relevance(query, item[0], item[1]),
                reverse=True,
            )
            sections = []
            for document, source in ranked[:3]:
                label = " · ".join(filter(None, [
                    str(source.get("course_name") or ""),
                    str(source.get("chapter") or source.get("title") or "用户学习资源"),
                ]))
                sections.append(f"【资料来源：{label or '用户学习资源'}】\n{document[:1000]}")
            return (
                "资料检索状态：已命中。以下内容是系统实际检索到的资料；"
                "若正文直接包含答案，不得声称知识库未提供。\n"
                "相关学习资料（仅在与问题相关时使用）：\n"
                + "\n---\n".join(sections)
            )
        except Exception:
            return ""

    @staticmethod
    def _rag_query(message: str) -> str:
        query = str(message or "").strip()
        fillers = (
            "请根据预制课程知识库回答并标明资料来源",
            "请根据预制课程知识库回答",
            "请结合预制课程知识库回答",
            "请根据预制课程知识库",
            "并标明资料来源",
            "请标明资料来源",
            "标明资料来源",
        )
        for filler in fillers:
            query = query.replace(filler, "")
        cleaned = query.strip(" \t\r\n，。！？；：,.!?;:")
        return cleaned or str(message or "").strip()

    @staticmethod
    def _rag_relevance(query: str, document: str, source: dict) -> int:
        normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(query or ""))
        source_text = "".join([
            str(source.get("title") or ""),
            str(source.get("chapter") or ""),
            "".join(str(value) for value in source.get("knowledge_points") or []),
        ])
        searchable = re.sub(
            r"[^0-9A-Za-z\u4e00-\u9fff]+",
            "",
            source_text + str(document or ""),
        )
        if not normalized or not searchable:
            return 0

        subject = normalized
        for prefix in ("请问", "请解释", "解释一下", "为什么", "如何", "怎么"):
            if subject.startswith(prefix):
                subject = subject[len(prefix):]
        subject = subject.split("的", 1)[0]

        score = 0
        if 2 <= len(subject) <= 16 and subject in searchable:
            score += 500
            if subject in source_text:
                score += 500

        max_size = min(8, len(normalized))
        for size in range(2, max_size + 1):
            grams = {normalized[index:index + size] for index in range(len(normalized) - size + 1)}
            for gram in grams:
                if gram in searchable:
                    score += size * size
                if gram in source_text:
                    score += size * size
        return score


if __name__ == "__main__":
    import sys
    import asyncio

    sys.stdout.reconfigure(encoding="utf-8")
    agent = ChatAgent()
    state = AgentState(
        user_id="test",
        user_message="装饰器是什么，用一句话解释",
    )
    async def run():
        async for chunk in agent.stream(state):
            print(chunk, end="", flush=True)
        print()
    asyncio.run(run())
