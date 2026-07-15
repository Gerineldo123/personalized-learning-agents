import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from agents.base import AgentState  # noqa: E402
from agents.mindmap_agent import MindMapAgent  # noqa: E402
from agents.skills import MindmapSkill  # noqa: E402


class MindMapAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_draft_mode_streams_markdown_without_saving(self):
        async def chunks():
            for text in ["# 树与二叉树\n", "## 遍历：前中后序\n", "### 递归实现"]:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
                )

        tokens = []
        state = AgentState(
            user_id="test-user",
            user_message="树与二叉树",
            profile=None,
            persist=False,
        )
        agent = MindMapAgent()
        with patch(
            "agents.mindmap_agent.chat_completion",
            new=AsyncMock(return_value=chunks()),
        ), patch(
            "agents.mindmap_agent.check_text",
            new=AsyncMock(side_effect=lambda text: (text, [])),
        ), patch.object(agent, "_save_to_db") as save_to_db:
            await agent.process(state, on_token=tokens.append)

        response = json.loads(state["response"])
        self.assertEqual(response["title"], "树与二叉树")
        self.assertTrue(response["content"].startswith("# 树与二叉树"))
        self.assertEqual("".join(tokens), response["content"])
        save_to_db.assert_not_called()


class MindmapSkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_builds_markmap_draft_with_graph_bindings(self):
        markdown = "# 树与二叉树\n## 遍历\n### 前序遍历：根左右"

        async def fake_process(_agent, state, on_token=None):
            if on_token:
                on_token(markdown)
            state["response"] = json.dumps({
                "agent": "mindmap",
                "resource_type": "mindmap",
                "title": "树与二叉树",
                "content": markdown,
            }, ensure_ascii=False)
            return state

        binding = {
            "course_name": "数据结构",
            "knowledge_points": ["树与二叉树", "二叉树遍历"],
            "kp_weights": {"树与二叉树": 0.5, "二叉树遍历": 0.5},
            "course_bindings": [{
                "course_name": "数据结构",
                "knowledge_points": ["树与二叉树", "二叉树遍历"],
                "kp_weights": {"树与二叉树": 0.5, "二叉树遍历": 0.5},
            }],
        }
        workflow = []
        with patch("agents.mindmap_agent.MindMapAgent.process", new=fake_process), patch(
            "agents.skills.infer_draft_resource_binding",
            return_value=binding,
        ):
            result = await MindmapSkill().execute({
                "user_id": "test-user",
                "user_message": "生成数据结构中树与二叉树的思维导图",
                "skill_instruction": "只生成树与二叉树思维导图",
                "profile": None,
                "course_name": "数据结构",
                "knowledge_points": ["树与二叉树", "二叉树遍历"],
            }, workflow)

        self.assertTrue(result.success)
        self.assertEqual(result.data["markdown"], markdown)
        draft = result.data["draft_resource"]
        self.assertEqual(draft["resource_type"], "mindmap")
        self.assertEqual(draft["content"], {"markdown": markdown})
        self.assertEqual(draft["course_name"], "数据结构")
        self.assertEqual(draft["knowledge_points"], ["树与二叉树", "二叉树遍历"])
        self.assertEqual(draft["course_bindings"], binding["course_bindings"])
        completed = [event for event in workflow if event.get("status") == "completed"][-1]
        self.assertEqual(completed["data"]["render_type"], "markmap")
        self.assertEqual(completed["data"]["draft_resource"], draft)


if __name__ == "__main__":
    unittest.main()
