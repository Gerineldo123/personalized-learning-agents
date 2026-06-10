import json
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.resource import LearningResource
from services.safety_service import check_text, hallu_rules
from services.rag_service import index_resource

MINDMAP_PROMPT = """你是一个知识体系整理专家。根据主题生成一个层级化的Markdown思维导图结构。

主题：{topic}
学生画像：{profile}

规则：
- 使用 # ## ### #### 构建层级树，最低到 4 级
- # 是根节点（主题名称），## 是一级分支，### 是二级分支，#### 是三级细节
- 尽量覆盖该知识点的完整体系
- 每个分支节点简洁明了（5-15字）
- 适配学生当前的知识水平
- {hallu}
- 只返回Markdown，不要其他说明"""


class MindMapAgent(BaseAgent):
    name = "mindmap"
    description = "将知识体系整理为思维导图结构"

    async def process(self, state: AgentState) -> AgentState:
        topic = state.user_message
        profile_text = self._profile_text(state)
        resp = await chat_completion([
            {"role": "user", "content": MINDMAP_PROMPT.format(topic=topic, profile=profile_text, hallu=hallu_rules())}
        ], temperature=0.4)
        markdown = resp.choices[0].message.content.strip()
        if markdown.startswith("```"):
            markdown = markdown.strip("`").strip()
            if markdown.startswith("markdown"):
                markdown = markdown[8:].strip()
        safe_markdown, _ = await check_text(markdown)
        title = topic
        for line in safe_markdown.split("\n"):
            if line.startswith("# ") and not line.startswith("## "):
                title = line.replace("# ", "").strip()
                break
        self._save_to_db(state, title, safe_markdown)
        state["response"] = json.dumps({
            "agent": self.name, "resource_type": "mindmap", "title": title, "content": safe_markdown,
        }, ensure_ascii=False)
        return state

    def _profile_text(self, state: AgentState) -> str:
        p = state.get("profile")
        if not p:
            return "暂无学生画像"
        return f"专业：{p.major or '未知'}，年级：{p.grade or '未知'}，知识基础：{json.dumps(p.knowledge_base or {}, ensure_ascii=False)}"

    def _save_to_db(self, state: AgentState, title: str, markdown: str):
        db = SessionLocal()
        try:
            resource = LearningResource(user_id=state.user_id, resource_type="mindmap", title=title, content={"markdown": markdown}, tags=["mindmap"])
            db.add(resource)
            db.commit()
            index_resource(resource.id, state.user_id or "", markdown, "mindmap")
        finally:
            db.close()


if __name__ == "__main__":
    import sys, asyncio
    sys.stdout.reconfigure(encoding="utf-8")
    agent = MindMapAgent()
    state = AgentState(user_id="test", user_message="Python装饰器")
    result = asyncio.run(agent.process(state))
    print(result.get("response", "")[:500])
