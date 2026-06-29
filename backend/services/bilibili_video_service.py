from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote

import httpx


BILI_HOME = "https://www.bilibili.com/"
BILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
BILI_SEARCH_PAGE = "https://search.bilibili.com/all"
BILI_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
BILI_VIDEO_URL = "https://www.bilibili.com/video/{}"

BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _format_play(value: Any) -> str:
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        return ""
    if count >= 10000:
        return f"{count / 10000:.1f}万"
    return str(count)


def _normalize_pic(pic: str) -> str:
    if not pic:
        return ""
    if pic.startswith("//"):
        return "https:" + pic
    if not pic.startswith("http"):
        return "https:" + pic
    return pic


def _explicit_page_from_query(query: str) -> int | None:
    patterns = [
        r"第\s*(\d{1,3})\s*(?:集|讲|节|课|部分|章)",
        r"\b[pP]\s*(\d{1,3})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
    return [item for item in cleaned.split() if len(item) >= 2]


def _select_page(detail: dict, query: str) -> dict:
    pages = detail.get("pages") or []
    if not pages:
        return {"page": 1, "cid": detail.get("cid"), "part": "", "duration": detail.get("duration") or 0}

    explicit_page = _explicit_page_from_query(query)
    if explicit_page:
        for page in pages:
            if int(page.get("page") or 0) == explicit_page:
                return page

    query_tokens = _tokens(query)
    if not query_tokens:
        return pages[0]

    best_page = pages[0]
    best_score = 0
    for page in pages:
        part = _clean_text(page.get("part", ""))
        part_lower = part.lower()
        score = sum(1 for token in query_tokens if token in part_lower)
        if part and part in query:
            score += 3
        if score > best_score:
            best_score = score
            best_page = page
    return best_page


def _direct_video_url(bvid: str, page: int, total_pages: int) -> str:
    base = BILI_VIDEO_URL.format(bvid)
    if total_pages > 1:
        return f"{base}?p={max(1, page)}"
    return base


async def _fetch_detail(client: httpx.AsyncClient, bvid: str) -> dict:
    try:
        response = await client.get(BILI_VIEW_API, params={"bvid": bvid})
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") == 0 and isinstance(payload.get("data"), dict):
            return payload["data"]
    except Exception:
        return {}
    return {}


async def _video_item_from_bvid(
    client: httpx.AsyncClient,
    bvid: str,
    query: str,
    reason: str = "",
    search_item: dict | None = None,
) -> dict | None:
    detail = await _fetch_detail(client, bvid)
    if not detail and not search_item:
        return None

    search_item = search_item or {}
    pages = detail.get("pages") or []
    page_info = _select_page(detail, query) if detail else {"page": 1, "part": "", "duration": 0}
    page = int(page_info.get("page") or 1)
    page_title = _clean_text(page_info.get("part", ""))
    total_pages = max(1, len(pages))

    base_title = _clean_text(search_item.get("title")) or _clean_text(detail.get("title")) or query
    title = base_title
    if total_pages > 1 and page_title:
        title = f"{base_title} · P{page} {page_title}"

    owner = detail.get("owner") or {}
    stat = detail.get("stat") or {}
    play_count = _format_play(search_item.get("play") if search_item.get("play") is not None else stat.get("view"))
    author = _clean_text(search_item.get("author") or owner.get("name") or "")
    duration = search_item.get("duration") or _format_duration(int(page_info.get("duration") or detail.get("duration") or 0))

    return {
        "title": title,
        "url": _direct_video_url(bvid, page, total_pages),
        "cover": _normalize_pic(search_item.get("pic") or detail.get("pic") or ""),
        "duration": duration if isinstance(duration, str) else _format_duration(int(duration or 0)),
        "author": author,
        "play_count": play_count,
        "danmaku": _format_play(search_item.get("danmaku") if search_item.get("danmaku") is not None else stat.get("danmaku")),
        "bvid": bvid,
        "page": page,
        "cid": page_info.get("cid"),
        "episode_title": page_title,
        "episode_count": total_pages,
        "source": f"B站 · {author} · {play_count}播放",
        "reason": reason,
        "query": query,
        "direct": True,
    }


async def _search_by_api(client: httpx.AsyncClient, query: str, reason: str, per_keyword: int) -> list[dict]:
    response = await client.get(
        BILI_SEARCH_API,
        params={
            "search_type": "video",
            "keyword": query,
            "page": 1,
            "order": "click",
        },
    )
    response.raise_for_status()
    payload = response.json()
    video_list = (payload.get("data") or {}).get("result") or []
    items: list[dict] = []
    for video in video_list:
        bvid = video.get("bvid") or ""
        if not bvid:
            continue
        item = await _video_item_from_bvid(client, bvid, query, reason, video)
        if item:
            items.append(item)
        if len(items) >= per_keyword:
            break
    return items


async def _search_by_html(client: httpx.AsyncClient, query: str, reason: str, per_keyword: int) -> list[dict]:
    response = await client.get(BILI_SEARCH_PAGE, params={"keyword": query})
    response.raise_for_status()
    bvids = list(dict.fromkeys(BV_RE.findall(response.text)))
    items: list[dict] = []
    for bvid in bvids:
        item = await _video_item_from_bvid(client, bvid, query, reason)
        if item:
            items.append(item)
        if len(items) >= per_keyword:
            break
    return items


def _normalize_keywords(keywords: list[dict] | list[str] | str) -> list[dict]:
    if isinstance(keywords, str):
        query = _clean_text(keywords)
        return [{"query": query, "reason": ""}] if query else []
    normalized = []
    for item in keywords or []:
        if isinstance(item, dict):
            query = _clean_text(item.get("query") or item.get("keyword") or "")
            reason = _clean_text(item.get("reason") or "")
        else:
            query = _clean_text(item)
            reason = ""
        if query:
            normalized.append({"query": query, "reason": reason})
    return normalized


async def search_bilibili_videos(
    keywords: list[dict] | list[str] | str,
    *,
    per_keyword: int = 2,
    total_limit: int = 5,
) -> dict:
    normalized_keywords = _normalize_keywords(keywords)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": BILI_HOME,
    }
    videos: list[dict] = []
    failures: list[dict] = []
    seen_bvid_pages: set[tuple[str, int]] = set()

    async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
        try:
            await client.get(BILI_HOME)
        except Exception:
            pass

        for keyword in normalized_keywords:
            query = keyword["query"]
            reason = keyword.get("reason", "")
            found: list[dict] = []
            try:
                found = await _search_by_api(client, query, reason, per_keyword)
            except Exception:
                found = []
            if not found:
                try:
                    found = await _search_by_html(client, query, reason, per_keyword)
                except Exception:
                    found = []

            if not found:
                failures.append({
                    "query": query,
                    "reason": "未能从 B 站搜索结果中解析到可直达播放的视频",
                    "search_url": f"{BILI_SEARCH_PAGE}?keyword={quote(query)}",
                })
                continue

            for video in found:
                key = (video.get("bvid", ""), int(video.get("page") or 1))
                if key in seen_bvid_pages:
                    continue
                seen_bvid_pages.add(key)
                videos.append(video)
                if len(videos) >= total_limit:
                    return {"videos": videos, "failures": failures}

    return {"videos": videos[:total_limit], "failures": failures}
