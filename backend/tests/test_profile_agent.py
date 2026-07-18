from agents.profile_agent import ProfileAgent
from models.student import StudentProfile


def test_merge_profile_updates_summary_and_evidence():
    profile = StudentProfile(
        user_id="profile-test",
        learning_goal="旧目标",
        cognitive_style="视觉型",
        preferred_format=["视频"],
        ability_summary="旧摘要",
    )

    ProfileAgent()._merge_profile(profile, {
        "learning_goal": "夯实基础",
        "cognitive_style": "实践型",
        "preferred_format": ["动画"],
        "ability_summary": "偏好通过动画和实践案例补强基础知识。",
    })

    assert profile.learning_goal == "夯实基础"
    assert profile.cognitive_style == "实践型"
    assert set(profile.preferred_format) == {"视频", "动画"}
    assert profile.ability_summary == "偏好通过动画和实践案例补强基础知识。"
    assert profile.profile_evidence["ability_summary"] == "AI助手历史对话分析"


def test_parse_profile_json_from_code_fence():
    parsed = ProfileAgent._parse_extracted('```json\n{"ability_summary":"摘要"}\n```')
    assert parsed == {"ability_summary": "摘要"}


def test_parse_profile_json_from_mixed_text():
    parsed = ProfileAgent._parse_extracted('分析结果如下：\n{"learning_goal":"补基础"}\n请查收')
    assert parsed == {"learning_goal": "补基础"}


def test_parse_plain_text_as_summary_only():
    parsed = ProfileAgent._parse_extracted("建议先巩固基础，再完成专项练习。")
    assert parsed == {"ability_summary": "建议先巩固基础，再完成专项练习。"}


def test_parse_empty_profile_response_fails_cleanly():
    try:
        ProfileAgent._parse_extracted("")
    except ValueError as exc:
        assert "未返回有效内容" in str(exc)
    else:
        raise AssertionError("空响应应触发 ValueError")
