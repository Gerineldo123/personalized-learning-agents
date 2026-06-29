import json
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion
from core.database import SessionLocal
from models.resource import LearningResource
from services.safety_service import check_text, hallu_rules
from services.rag_service import index_resource
from services.kp_service import infer_resource_tags

MINDMAP_PROMPT = """你是一位知识体系整理专家兼学科教师。请根据主题生成一份**知识点详尽的层级思维导图**，而非目录大纲。

主题：{topic}
学生画像：{profile}

【核心原则】
- 思维导图的每个节点必须承载**具体知识内容**，而非空洞的章节标题
- 禁止出现仅有名词而无解释的节点（如只写"定义""特点""应用"而不写具体内容）
- 叶节点（#### 三级细节）必须包含：概念精要、公式、定理陈述、关键参数含义、或一句话示例

【结构规范】
- 使用 Markdown 标题层级：# 根 → ## 一级 → ### 二级 → #### 三级（最多4级）
- # 根节点：主题名称（5-15字）
- ## 一级分支：知识大类，附带概括说明（15-25字）
- ### 二级分支：具体知识点名称及精炼定义（15-40字）
- #### 三级细节：公式/定理/参数/示例/易错点等具体内容（20-60字），必须有实质信息

【内容要求】
- 覆盖该主题的完整知识链路：概念 → 原理 → 方法 → 应用 → 易错/对比
- 涉及理科（数学/物理等）时，必须包含核心公式或定理
- 涉及编程时，必须包含关键语法描述或代码逻辑
- 针对学生薄弱点 {weak_points} 的部分，节点数量应更密集，并在对应节点中标注易错警告
- 对照学生画像的知识基础，避免超出当前阶段过多的内容

【格式示例 — 好的节点 vs 坏的节点】
坏节点（空洞）：
  ### 基本概念
  #### 定义

好节点（有知识）：
  ### 装饰器本质：接受函数参数并返回新函数的高阶函数
  #### @语法糖：@decorator 等价于 func = decorator(func)，在定义时立即执行
  #### 常见内置装饰器：@staticmethod（无self/cls参数）、@property（方法变属性访问）

{hallu}
只返回 Markdown，不要任何开头结尾的闲聊说明。"""


class MindMapAgent(BaseAgent):
    name = "mindmap"
    description = "将知识体系整理为思维导图结构"

    async def process(self, state: AgentState) -> AgentState:
        topic = state.user_message
        profile_text, weak_points_text = self._profile_text(state)
        resp = await chat_completion([
            {"role": "user", "content": MINDMAP_PROMPT.format(topic=topic, profile=profile_text, weak_points=weak_points_text, hallu=hallu_rules())}
        ], temperature=0.55)
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
            "resource_db_id": state.get("resource_db_id"),
        }, ensure_ascii=False)
        return state

    def _profile_text(self, state: AgentState) -> tuple[str, str]:
        p = state.get("profile")
        if not p:
            return "暂无学生画像", "无记录"
        profile_parts = [
            f"专业：{p.major or '未知'}",
            f"年级/阶段：{p.grade or '未知'}/{p.education_level or '未知'}",
            f"已掌握基础：{json.dumps(p.knowledge_base or {}, ensure_ascii=False)}",
            f"学习目标：{p.learning_goal or '未设定'}",
        ]
        weak_text = "无记录"
        if p.weak_points:
            if isinstance(p.weak_points, list):
                weak_text = "、".join(str(w) for w in p.weak_points)
            else:
                weak_text = str(p.weak_points)
        return "；".join(profile_parts), weak_text

    def _save_to_db(self, state: AgentState, title: str, markdown: str):
        prev_id = state.get("resource_db_id")
        graph_tags = infer_resource_tags(
            f"{state.get('user_message', '')} {title} {markdown}",
            course_name=state.get("course_name"),
            knowledge_points=state.get("knowledge_points") or [],
        )
        tags = list(dict.fromkeys(
            ["mindmap"]
            + [x for x in [graph_tags.get("course_name")] if x]
            + list(graph_tags.get("knowledge_points") or [])
        ))
        db = SessionLocal()
        try:
            resource = LearningResource(
                user_id=state.user_id,
                resource_type="mindmap",
                title=title,
                content={"markdown": markdown},
                tags=tags,
                course_name=graph_tags.get("course_name"),
                knowledge_points=graph_tags.get("knowledge_points") or [],
                kp_weights=graph_tags.get("kp_weights") or {},
                tag_confidence=graph_tags.get("tag_confidence") or 0,
            )
            db.add(resource)
            db.commit()
            index_resource(resource.id, state.user_id or "", markdown[:4000], "mindmap")
            if not prev_id:
                state["resource_db_id"] = resource.id
            state["resource_title"] = title
        finally:
            db.close()


if __name__ == "__main__":
    import sys, asyncio
    sys.stdout.reconfigure(encoding="utf-8")
    agent = MindMapAgent()
    state = AgentState(user_id="test", user_message="Python装饰器")
    result = asyncio.run(agent.process(state))
    print(result.get("response", "")[:500])
