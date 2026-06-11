from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable


def search_learning_resources(query: str, user_id: str) -> list[dict]:
    from services.rag_service import search_rag
    result = search_rag(query, user_id, top_k=3)
    docs = result.get("documents", [])
    ids = result.get("ids", [])
    return [{"content": d[:500], "id": i} for d, i in zip(docs, ids)]


def query_mistake_history(user_id: str, topic: str = "") -> list[dict]:
    from core.database import SessionLocal
    from models.mistake_question import MistakeQuestion
    db = SessionLocal()
    try:
        q = db.query(MistakeQuestion).filter(MistakeQuestion.user_id == user_id)
        records = q.order_by(MistakeQuestion.created_at.desc()).limit(20).all()
        return [{"question": r.question, "user_answer": r.user_answer, "correct_answer": r.correct_answer} for r in records]
    finally:
        db.close()


def get_student_profile(user_id: str) -> dict:
    from core.database import SessionLocal
    from models.student import StudentProfile
    db = SessionLocal()
    try:
        p = db.query(StudentProfile).filter(StudentProfile.user_id == user_id).first()
        if not p:
            return {}
        return {"major": p.major, "grade": p.grade, "knowledge_base": p.knowledge_base,
                "weak_points": p.weak_points, "learning_goal": p.learning_goal}
    finally:
        db.close()


import os
import httpx


async def tavily_search(query: str, max_results: int = 5, include_domains: list[str] | None = None) -> dict:
    from services.config_service import get_tavily_api_key
    api_key = get_tavily_api_key()
    if not api_key:
        return {"error": "未配置 Tavily API Key，请在【API配置 → Tavily 搜索】中填入以 tvly- 开头的密钥", "results": [], "answer": "", "query": query}
    if not api_key.startswith("tvly-"):
        return {"error": f"Tavily API Key 格式错误（应以 tvly- 开头，当前为 {api_key[:6]}...）。请在【API配置】中修正", "results": [], "answer": "", "query": query}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                    "search_depth": "advanced",
                    **({"include_domains": include_domains} if include_domains else {}),
                },
            )
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}", "results": [], "answer": "", "query": query}
            data = resp.json()
            results = data.get("results", [])
            return {
                "query": query,
                "answer": data.get("answer", ""),
                "results": [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:500]} for r in results],
            }
    except Exception as e:
        return {"error": str(e), "query": query, "results": [], "answer": ""}


async def web_scrape(url: str) -> dict:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            content_type = resp.headers.get("content-type", "")
            text = resp.text
            if "text/html" in content_type:
                from html.parser import HTMLParser

                class TextExtractor(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.text = []
                        self.skip = False

                    def handle_starttag(self, tag, attrs):
                        if tag in ("script", "style", "noscript"):
                            self.skip = True

                    def handle_endtag(self, tag):
                        if tag in ("script", "style", "noscript"):
                            self.skip = False

                    def handle_data(self, data):
                        if not self.skip:
                            stripped = data.strip()
                            if stripped:
                                self.text.append(stripped)

                extractor = TextExtractor()
                extractor.feed(text)
                extracted = " ".join(extractor.text)[:2000]
            else:
                extracted = text[:2000]
            return {"url": url, "content": extracted, "status_code": resp.status_code}
    except Exception as e:
        return {"url": url, "content": "", "error": str(e), "status_code": 0}


TOOLS = [
    Tool("search_resources", "搜索学习资源库", search_learning_resources),
    Tool("query_mistakes", "查询学生错题记录", query_mistake_history),
    Tool("get_profile", "获取学生画像", get_student_profile),
    Tool("tavily_search", "Tavily 互联网搜索", tavily_search),
    Tool("web_scrape", "抓取网页内容", web_scrape),
]

TOOL_MAP = {t.name: t.handler for t in TOOLS}
TOOL_DESC = "\n".join([f"- {t.name}: {t.description}" for t in TOOLS])
