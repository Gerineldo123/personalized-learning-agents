"""
OrchestratorAgent: 协同编排多智能体资源生成
流水线：ProfileAnalysis → Article → (MindMap 消费文章内容) + Quiz + Video 并行
"""
import json
import asyncio
from agents.base import BaseAgent, AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from core.llm_client import chat_completion


PROFILE_ANALYSIS_PROMPT = """分析学生画像，输出学习重点和资源生成策略。

学生画像：{profile}
学习主题：{topic}

返回JSON：
{{
  "core_concepts": ["核心概念1", "核心概念2"],
  "difficulty_level": "初级/中级/高级",
  "focus_subtopics": ["重点子主题1", "重点子主题2"],
  "suggested_sequence": "建议学习顺序说明"
}}
只返回JSON。"""


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"
    description = "多智能体协同编排：分析画像→生成文章→基于文章生成思维导图，同时并行生成题库和视频推荐"

    async def process(self, state: AgentState) -> AgentState:
        topic = state.user_message
        profile = state.get("profile")

        # Step 1: 画像分析
        profile_analysis = await self._analyze_profile(topic, profile)
        state["profile_analysis"] = profile_analysis

        # Step 2: 先生成文章（思维导图依赖文章内容）
        article_state = AgentState(**{**state, "resource_type": "article"})
        await ContentGenAgent().process(article_state)
        article_content = ""
        try:
            resp = json.loads(article_state.get("response", "{}"))
            article_content = resp.get("content", "")
        except Exception:
            pass

        # Step 3: 思维导图以文章内容为输入（体现协同），其他任务并行
        mindmap_topic = f"{topic}\n\n参考内容：\n{article_content[:1500]}" if article_content else topic
        mindmap_state = AgentState(**{**state, "user_message": mindmap_topic, "resource_type": "mindmap"})
        quiz_state = AgentState(**{**state, "resource_type": "quiz"})
        video_state = AgentState(**{**state, "resource_type": "video"})

        await asyncio.gather(
            MindMapAgent().process(mindmap_state),
            ContentGenAgent().process(quiz_state),
            VideoAgent().process(video_state),
        )

        state["response"] = json.dumps({
            "agent": self.name,
            "orchestration": "article→(mindmap+quiz+video)",
            "profile_analysis": profile_analysis,
            "steps_completed": ["article", "mindmap", "quiz", "video"],
        }, ensure_ascii=False)
        return state

    async def _analyze_profile(self, topic: str, profile) -> dict:
        profile_text = "暂无画像"
        if profile:
            profile_text = (
                f"专业:{getattr(profile,'major','未知')} 年级:{getattr(profile,'grade','未知')} "
                f"薄弱点:{json.dumps(getattr(profile,'weak_points',[]),ensure_ascii=False)} "
                f"目标:{getattr(profile,'learning_goal','无')}"
            )
        try:
            resp = await chat_completion([
                {"role": "user", "content": PROFILE_ANALYSIS_PROMPT.format(profile=profile_text, topic=topic)}
            ], temperature=0.3)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            return json.loads(raw)
        except Exception:
            return {"core_concepts": [], "difficulty_level": "中级", "focus_subtopics": [], "suggested_sequence": ""}
