import json
import httpx
from urllib.parse import quote
from agents.base import BaseAgent, AgentState
from core.llm_client import chat_completion

KEYWORD_PROMPT = """你是教学视频推荐助手。根据学生画像，推荐 2~3 个 B站 搜索关键词。

学生画像：
- 专业：{major}，年级：{grade}
- 当前水平：{level}
- 薄弱知识点：{weak_points}
- 学习目标：{learning_goal}

要求：
1. 关键词要精准、组合（如"导数 链式法则 例题"），便于搜到高质量中文教学视频
2. 每个关键词说明为什么选择它（结合画像）

只返回 JSON：
{{
  "keywords": [
    {{"query": "搜索词", "reason": "推荐理由"}}
  ],
  "search_summary": "一句话概括"
}}"""

BILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
BILI_VIDEO_URL = "https://www.bilibili.com/video/{}"


class VideoAgent(BaseAgent):
    name = "video"
    description = "根据学生画像搜索 B站教学视频，返回直达播放链接"

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
            kw_result = {"keywords": [], "search_summary": "搜索失败"}

        keywords = kw_result.get("keywords", [])
        videos = await self._search_bilibili(keywords[:3])

        state["response"] = json.dumps({
            "agent": "video",
            "videos": videos,
            "search_summary": kw_result.get("search_summary", ""),
        }, ensure_ascii=False)
        return state

    async def _search_bilibili(self, keywords: list[dict]) -> list[dict]:
        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
            await client.get("https://www.bilibili.com/")
            for kw in keywords:
                query = kw.get("query", "")
                if not query:
                    continue
                try:
                    r = await client.get(BILI_SEARCH_API, params={
                        "search_type": "video", "keyword": query, "page": 1,
                    })
                    r.raise_for_status()
                    data = r.json()
                    video_list = (data.get("data") or {}).get("result") or []
                    found = False
                    for v in video_list[:3]:
                        bvid = v.get("bvid", "")
                        if not bvid:
                            continue
                        found = True
                        arcurl = v.get("arcurl", "")
                        url = arcurl if arcurl and "video" in arcurl else BILI_VIDEO_URL.format(bvid)
                        pic = v.get("pic", "")
                        if pic and not pic.startswith("http"):
                            pic = "https:" + pic
                        results.append({
                            "title": v.get("title", query).replace('<em class="keyword">', "").replace("</em>", ""),
                            "url": url,
                            "cover": pic,
                            "duration": v.get("duration", ""),
                            "source": f"B站 · {v.get('author', '') or ''} · {self._fmt_play(v.get('play', 0))}播放",
                            "reason": kw.get("reason", ""),
                        })
                    if not found:
                        results.append({
                            "title": query,
                            "url": f"https://search.bilibili.com/all?keyword={quote(query)}",
                            "source": "B站",
                            "reason": kw.get("reason", "") + " (未找到匹配视频)",
                        })
                except Exception:
                    results.append({
                        "title": query,
                        "url": f"https://search.bilibili.com/all?keyword={quote(query)}",
                        "source": "B站",
                        "reason": kw.get("reason", ""),
                    })
        return results[:5]

    def _fmt_play(self, n: int) -> str:
        if n >= 10000:
            return f"{n / 10000:.1f}万"
        return str(n)
