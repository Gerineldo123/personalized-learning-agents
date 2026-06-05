import json
from typing import AsyncGenerator
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from services.safety_service import check_text, hallu_rules
from services.rag_service import search_rag

SYSTEM_PROMPT = """你是一个个性化学习智能体系统的 AI 助手。

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

涉及概念对比时，优先使用 Markdown 表格，表头加粗，列对齐。

回答末尾可根据情况添加：
- **扩展思考**：与本知识点相关的进阶话题或跨学科联系
- 进一步学习的建议，引导学生继续探索

【主动建议规则】
如果检测到以下情况，在回答最末尾（换行后）附加建议，格式严格为：[建议] 内容
- 学生多次询问同类主题或表达困惑/不理解 → [建议] 系统学习【{{topic}}】（用具体主题替换{{topic}}）
- 学生提到做错题、不会做题、想巩固 → [建议] 分析错题
- 学生问到学习方向或评估水平 → [建议] 学习评估
- 学生明确询问视频/教学视频/视频推荐 → [建议] 搜索视频【{{topic}}】（用具体主题替换{{topic}}）
每次最多给出1条建议，没有合适情况则不写建议。

{hallu}

学生画像信息：{profile}

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

        stream_resp = await chat_completion(messages, temperature=0.7, stream=True)

        collected = ""
        async for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if delta.content:
                collected += delta.content
                yield delta.content

        safe_collected, ok = await check_text(collected)
        state["response"] = safe_collected

    def _profile_text(self, state: AgentState) -> str:
        p = state.get("profile")
        user_id = state.get("user_id", "")

        # 读取最近错题
        mistake_text = "无"
        try:
            from core.database import SessionLocal
            from models.mistake_question import MistakeQuestion
            db = SessionLocal()
            try:
                mistakes = db.query(MistakeQuestion).filter(
                    MistakeQuestion.user_id == user_id
                ).order_by(MistakeQuestion.created_at.desc()).limit(5).all()
                if mistakes:
                    mistake_text = "、".join([
                        (m.question.get("question", "")[:30] if m.question else "") for m in mistakes
                    ])
            finally:
                db.close()
        except Exception:
            pass

        # 读取专注数据
        focus_text = "无专注记录"
        try:
            from core.database import SessionLocal as SL2
            from models.focus import FocusSession
            db2 = SL2()
            try:
                sessions = db2.query(FocusSession).filter(
                    FocusSession.user_id == user_id
                ).order_by(FocusSession.started_at.desc()).limit(20).all()
                if sessions:
                    total = sum(s.duration_min for s in sessions)
                    done = sum(1 for s in sessions if s.completed)
                    focus_text = f"累计专注{total}分钟，完成{done}/{len(sessions)}次"
            finally:
                db2.close()
        except Exception:
            pass

        if not p:
            return json.dumps({"最近错题": mistake_text, "专注情况": focus_text}, ensure_ascii=False)

        return json.dumps({
            "专业": p.major,
            "年级": p.grade,
            "知识基础": p.knowledge_base,
            "薄弱知识点": p.weak_points,
            "学习目标": p.learning_goal,
            "最近错题": mistake_text,
            "专注情况": focus_text,
        }, ensure_ascii=False)

    def _build_rag_context(self, state: AgentState) -> str:
        try:
            results = search_rag(state.user_message, state.get("user_id", ""), top_k=3)
            docs = results.get("documents", [])
            if not docs:
                return ""
            return "相关学习资料：\n" + "\n---\n".join(d[:800] for d in docs[:3])
        except Exception:
            return ""


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
