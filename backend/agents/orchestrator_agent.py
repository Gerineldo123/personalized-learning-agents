import asyncio
import json

from agents.base import BaseAgent, AgentState
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.video_agent import VideoAgent
from core.llm_client import chat_completion
from services.kp_service import default_focus_kps, infer_course_from_text


PROFILE_ANALYSIS_PROMPT = """你是多智能体学习系统的诊断规划智能体。请根据学生画像和主题输出资源生成策略。

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
    description = "多智能体协同编排：画像诊断、资源规划、并行生成、知识点绑定"

    async def process(self, state: AgentState) -> AgentState:
        topic = state.user_message
        profile = state.get("profile")
        course_name = state.get("course_name") or infer_course_from_text(topic, default="数据结构")
        focus_kps = state.get("knowledge_points") or default_focus_kps(course_name, topic, limit=4)

        profile_analysis = await self._analyze_profile(topic, profile)
        state["profile_analysis"] = profile_analysis
        state["course_name"] = course_name
        state["knowledge_points"] = focus_kps

        article_state = self._make_child_state(state, "article", topic, course_name, focus_kps)
        await ContentGenAgent().process(article_state)
        article_content = self._extract_content(article_state)

        mindmap_topic = f"{topic}\n\n参考讲解内容：\n{article_content[:1500]}" if article_content else topic
        parallel_specs = [
            ("mindmap", MindMapAgent(), mindmap_topic),
            ("quiz", ContentGenAgent(), topic),
            ("code", ContentGenAgent(), topic),
            ("ppt", ContentGenAgent(), topic),
            ("video", VideoAgent(), topic),
        ]

        async def run_one(resource_type: str, agent, message: str) -> tuple[str, AgentState, str | None]:
            child = self._make_child_state(state, resource_type, message, course_name, focus_kps)
            try:
                await agent.process(child)
                return resource_type, child, None
            except Exception as exc:
                return resource_type, child, str(exc)

        results = await asyncio.gather(*[
            run_one(resource_type, agent, message)
            for resource_type, agent, message in parallel_specs
        ])

        resources = [self._resource_info("article", article_state)]
        failures: list[dict] = []
        for resource_type, child, error in results:
            if error:
                failures.append({"resource_type": resource_type, "error": error})
            else:
                resources.append(self._resource_info(resource_type, child))

        resources = [r for r in resources if r.get("resource_id")]
        state["generated_resources"] = resources
        state["orchestration_failures"] = failures
        state["response"] = json.dumps({
            "agent": self.name,
            "orchestration": "profile_analysis -> article -> mindmap+quiz+code+ppt+video -> graph_tagging",
            "course_name": course_name,
            "knowledge_points": focus_kps,
            "profile_analysis": profile_analysis,
            "generated_resources": resources,
            "failures": failures,
            "steps_completed": ["article", "mindmap", "quiz", "code", "ppt", "video"],
        }, ensure_ascii=False)
        return state

    def _make_child_state(
        self,
        state: AgentState,
        resource_type: str,
        message: str,
        course_name: str | None,
        knowledge_points: list[str],
    ) -> AgentState:
        child = AgentState(**{
            **state,
            "user_message": message,
            "resource_type": resource_type,
            "course_name": course_name,
            "knowledge_points": knowledge_points,
        })
        child.pop("resource_db_id", None)
        return child

    def _resource_info(self, resource_type: str, state: AgentState) -> dict:
        return {
            "resource_type": resource_type,
            "resource_id": state.get("resource_db_id"),
            "title": state.get("resource_title") or state.get("user_message") or resource_type,
        }

    def _extract_content(self, state: AgentState) -> str:
        try:
            resp = json.loads(state.get("response", "{}"))
            content = resp.get("content", "")
            return json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
        except Exception:
            return ""

    async def _analyze_profile(self, topic: str, profile) -> dict:
        profile_text = "暂无画像"
        if profile:
            profile_text = (
                f"专业:{getattr(profile, 'major', '未知')} 年级:{getattr(profile, 'grade', '未知')} "
                f"薄弱点:{json.dumps(getattr(profile, 'weak_points', []), ensure_ascii=False)} "
                f"目标:{getattr(profile, 'learning_goal', '无')}"
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
            return {
                "core_concepts": [],
                "difficulty_level": "中级",
                "focus_subtopics": [],
                "suggested_sequence": "先补齐核心概念，再通过练习和代码案例巩固。",
            }
