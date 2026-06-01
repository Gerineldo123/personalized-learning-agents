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
        if not p:
            return "暂无学生画像"
        return json.dumps({
            "major": p.major,
            "grade": p.grade,
            "knowledge_base": p.knowledge_base,
            "weak_points": p.weak_points,
            "learning_goal": p.learning_goal,
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
