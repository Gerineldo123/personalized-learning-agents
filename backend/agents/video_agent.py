import json
import uuid

from agents.base import BaseAgent, AgentState
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.resource import LearningResource
from services.bilibili_video_service import search_bilibili_videos
from services.kp_service import infer_resource_tags
from services.rag_service import index_resource


KEYWORD_PROMPT = """你是教学视频推荐助手。请根据学生画像和当前学习需求，推荐 2~3 个 B 站搜索关键词。

学生画像：
- 专业：{major}，年级：{grade}
- 当前水平：{level}
- 薄弱知识点：{weak_points}
- 学习目标：{learning_goal}

要求：
1. 关键词要精准、可检索，尽量包含课程名、知识点和教学场景，例如“数据结构 二叉树 遍历 动画讲解”。
2. 每个关键词说明选择原因，原因需要结合学生画像和学习目标。

只返回 JSON：
{{
  "keywords": [
    {{"query": "搜索词", "reason": "推荐理由"}}
  ],
  "search_summary": "一句话概括推荐方向"
}}"""


class VideoAgent(BaseAgent):
    name = "video"
    description = "根据学生画像搜索 B 站教学视频，返回具体视频直达链接"

    async def process(self, state: AgentState) -> AgentState:
        profile = state.get("profile")
        profile_state = state.get("profile_analysis") or {}

        prompt = KEYWORD_PROMPT.format(
            major=getattr(profile, "major", "未知"),
            grade=getattr(profile, "grade", "未知"),
            level=profile_state.get("current_level", "中级"),
            weak_points=json.dumps(getattr(profile, "weak_points", []), ensure_ascii=False),
            learning_goal=getattr(profile, "learning_goal", "未知"),
        )

        resp = await chat_completion(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": state["user_message"]},
            ],
            temperature=0.5,
        )

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        try:
            kw_result = json.loads(raw)
        except json.JSONDecodeError:
            kw_result = {"keywords": [], "search_summary": "关键词生成失败"}

        search_result = await search_bilibili_videos(
            kw_result.get("keywords", [])[:3],
            per_keyword=2,
            total_limit=5,
        )
        videos = search_result.get("videos", [])
        failures = search_result.get("failures", [])

        self._save_or_draft_videos(state, videos, kw_result.get("search_summary", ""))
        state["response"] = json.dumps(
            {
                "agent": "video",
                "videos": videos,
                "failures": failures,
                "search_summary": kw_result.get("search_summary", ""),
            },
            ensure_ascii=False,
        )
        return state

    def _save_videos(self, state: AgentState, videos: list[dict], summary: str):
        if not videos:
            return
        graph_tags = infer_resource_tags(
            " ".join([state.get("user_message", ""), summary, json.dumps(videos, ensure_ascii=False)]),
            course_name=state.get("course_name"),
            knowledge_points=state.get("knowledge_points") or [],
        )
        tags = list(dict.fromkeys(
            ["video"]
            + [x for x in [graph_tags.get("course_name")] if x]
            + list(graph_tags.get("knowledge_points") or [])
        ))
        db = SessionLocal()
        try:
            first_id = None
            first_title = ""
            for video in videos:
                title = video.get("title") or "视频推荐"
                resource = LearningResource(
                    user_id=state.user_id,
                    resource_type="video",
                    title=title,
                    content=video,
                    tags=tags,
                    course_name=graph_tags.get("course_name"),
                    knowledge_points=graph_tags.get("knowledge_points") or [],
                    kp_weights=graph_tags.get("kp_weights") or {},
                    tag_confidence=graph_tags.get("tag_confidence") or 0,
                )
                db.add(resource)
                db.flush()
                if first_id is None:
                    first_id = resource.id
                    first_title = title
                index_resource(resource.id, state.user_id or "", title, "video")
            db.commit()
            if first_id is not None:
                state["resource_db_id"] = first_id
                state["resource_title"] = first_title
        finally:
            db.close()

    def _save_or_draft_videos(self, state: AgentState, videos: list[dict], summary: str):
        if state.get("persist", True) is False:
            title = f"视频推荐：{state.get('user_message', '')[:30]}" if state.get("user_message") else "视频推荐"
            state["resource_title"] = title
            state["draft_resource"] = {
                "client_draft_id": state.get("client_draft_id") or uuid.uuid4().hex,
                "resource_type": "video",
                "title": title,
                "content": {"videos": videos, "search_summary": summary},
                "course_name": state.get("course_name"),
                "knowledge_points": state.get("knowledge_points") or [],
                "kp_weights": state.get("kp_weights") or {},
                "save_required": True,
            }
            return
        self._save_videos(state, videos, summary)
