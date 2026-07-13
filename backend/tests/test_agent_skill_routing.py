import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from agents.skills import (  # noqa: E402
    _validate_topic_alignment,
    get_all_skills,
    get_skill,
    init_skills,
)
from graph.subgraphs.agent_execute import (  # noqa: E402
    _normalize_task_message,
    _parse_plan_json,
    _resolve_skill_routing,
)


class AgentSkillRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_skills()

    def route(self, message, skills=None, needs_code=False):
        return _resolve_skill_routing(
            message,
            skills or [],
            needs_code,
            "python",
            "",
        )

    def test_all_builtin_skills_are_available(self):
        skills = get_all_skills()
        self.assertIn("code_gen", skills)
        self.assertIn("ppt_gen", skills)
        self.assertIn("video_search", skills)

    def test_get_skill_returns_request_scoped_instance(self):
        first = get_skill("code_gen")
        second = get_skill("code_gen")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)

    def test_explicit_routes(self):
        cases = {
            "生成排序算法可视化动画": ["code_gen"],
            "推荐几个概率论教学视频": ["video_search"],
            "生成中心极限定理PPT课件": ["ppt_gen"],
            "生成一套概率论练习题": ["quiz_gen"],
            "整理一个贝叶斯公式思维导图": ["mindmap_gen"],
            "写一个二叉树遍历程序": ["code_gen"],
            "分析下面这段Python代码": ["code_analysis"],
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(self.route(message)["selected_skills"], expected)

    def test_resource_package_uses_orchestration(self):
        result = self.route("生成一套机器学习多模态资源包")
        self.assertEqual(result["execution_route"], "resource_orchestration")
        self.assertEqual(result["selected_skills"], ["resource_orchestration"])

    def test_plain_explanation_stays_direct(self):
        result = self.route("解释贝叶斯公式")
        self.assertEqual(result["execution_route"], "direct_answer")
        self.assertEqual(result["selected_skills"], [])

    def test_skill_aliases_are_normalized_and_deduplicated(self):
        result = self.route("生成一个代码示例", ["代码智能体", "code_gen", "code_generation"])
        self.assertEqual(result["selected_skills"], ["code_gen"])

    def test_needs_code_generation_falls_back_to_code_gen(self):
        result = self.route("请写一个链表反转程序", [], needs_code=True)
        self.assertEqual(result["selected_skills"], ["code_gen"])

    def test_visual_generation_removes_code_analysis(self):
        result = self.route("生成快速排序可视化动画", ["code_analysis"])
        self.assertEqual(result["selected_skills"], ["code_gen"])
        self.assertEqual(result["code_lang"], "html")

    def test_explicit_animation_ignores_planner_quiz_addition(self):
        result = self.route("给我一个可视化动画", ["code_gen", "quiz_gen"])
        self.assertEqual(result["selected_skills"], ["code_gen"])
        self.assertTrue(any("quiz_gen" in item for item in result["corrections"]))

    def test_explicit_single_resource_ignores_incorrect_needs_code(self):
        result = self.route("推荐几个概率论教学视频", ["video_search"], needs_code=True)
        self.assertEqual(result["selected_skills"], ["video_search"])

    def test_explicit_multi_output_request_keeps_requested_skills(self):
        result = self.route("生成排序算法可视化动画并配套练习题", ["code_gen"])
        self.assertEqual(result["selected_skills"], ["code_gen", "quiz_gen"])

    def test_history_context_does_not_add_unrequested_quiz_skill(self):
        contextualized = "给我一个可视化动画助我理解\n相关对话主题：请生成一套概率论练习题"
        result = _resolve_skill_routing(
            contextualized,
            ["quiz_gen"],
            False,
            "python",
            "",
            explicit_message="给我一个可视化动画助我理解",
        )
        self.assertEqual(result["selected_skills"], ["code_gen"])
        self.assertEqual(result["code_lang"], "html")
        self.assertIn("相关对话主题", result["code_desc"])

    def test_planner_skills_remain_available_without_explicit_intent(self):
        result = self.route("帮我处理一下这个学习任务", ["quiz_gen"])
        self.assertEqual(result["selected_skills"], ["quiz_gen"])

    def test_plan_json_parser_accepts_markdown_and_surrounding_text(self):
        text = "分析完成。\n```json\n{\"selected_skills\":[\"video_search\"],\"needs_code\":false}\n```\n请执行。"
        value, error = _parse_plan_json(text)
        self.assertEqual(error, "")
        self.assertEqual(value["selected_skills"], ["video_search"])

    def test_plan_json_parser_reports_invalid_output(self):
        value, error = _parse_plan_json("这里只给出了分析，没有配置对象")
        self.assertIsNone(value)
        self.assertTrue(error)

    def test_vague_task_uses_recent_user_context(self):
        normalized = _normalize_task_message(
            "给我一个可视化动画助我理解",
            [{"role": "user", "content": "请讲解方差分析与回归建模"}],
        )
        self.assertIn("方差分析与回归建模", normalized)

    def test_topic_alignment_rejects_unrelated_template(self):
        valid, error = _validate_topic_alignment(
            "方差分析与回归建模",
            "<html><title>K-Means聚类算法</title><body>质心迭代</body></html>",
        )
        self.assertFalse(valid)
        self.assertTrue(error)

    def test_topic_alignment_accepts_expected_topic(self):
        valid, error = _validate_topic_alignment(
            "方差分析与回归建模",
            "<html><title>方差分析与回归建模</title></html>",
        )
        self.assertTrue(valid)
        self.assertEqual(error, "")


if __name__ == "__main__":
    unittest.main()
