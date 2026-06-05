import json
from fastapi import APIRouter
from pydantic import BaseModel
from services.chat_service import route_to_agent, _load_profile
from schemas.chat import ChatRequest
from core.llm_client import chat_completion

router = APIRouter(prefix="/api/chat", tags=["对话"])


class TermExplainRequest(BaseModel):
    term: str
    user_id: str
    context: str = ""


EXPLAIN_PROMPT = """你是一位个性化学习导师。请根据学生的画像信息，对学生询问的学术术语进行解释。

解释时需要：
1. 用通俗易懂的语言解释该术语的基本定义
2. 如果有相关的定理、公式或知识点，简要列出
3. 根据学生的专业背景和学习阶段，调整解释的深度和侧重点
4. 对于与学生薄弱点相关的概念，额外加以强调
5. 将最关键的核心概念用 **粗体** 标出

学生画像信息：{profile}

请直接给出解释，不要加「解释：」「回答：」等前缀，控制在 200 字以内。"""


MARK_TERMS_PROMPT = """你是一个学术术语识别与解释专家。分析以下文本，完成两件事：

1. 将其中所有学科专业术语用 [[术语]] 包裹
2. 为每个被标记的术语生成一句简短通俗的中文解释（30-80字）

只返回JSON，格式：
{{
  "marked_text": "标记后的完整文本",
  "glossary": {{"术语1": "解释1", "术语2": "解释2"}}
}}

规则：
- 只标记教科书、论文中公认的学术专业术语（有明确定义、定理、公式的概念）
- 不要标记普通日常词汇（如"问题""方法""理解""例子"等）
- 不要标记已经用 [[ ]] 包裹过的术语
- 保持原文其他部分完全不变，包括格式、标点、换行、LaTeX 公式、Markdown 语法
- glossary 中只包含本次标记的术语及其解释
- 解释要通俗易懂、结合上下文语境
- 只返回JSON，不要其他内容

文本：
{text}"""


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    return await route_to_agent(req.user_id, req.message, req.history, req.session_id)


@router.post("/explain-term")
async def explain_term(req: TermExplainRequest):
    profile = _load_profile(req.user_id)
    profile_text = _build_profile_text(profile)

    messages = [
        {"role": "system", "content": EXPLAIN_PROMPT.format(profile=profile_text)},
        {"role": "user", "content": f"请解释术语：{req.term}\n\n上下文：{req.context}" if req.context else f"请解释术语：{req.term}"},
    ]

    resp = await chat_completion(messages, temperature=0.5)
    return {"term": req.term, "explanation": resp.choices[0].message.content}


class MarkTermsRequest(BaseModel):
    text: str


@router.post("/mark-terms")
async def mark_terms(req: MarkTermsRequest):
    if not req.text.strip():
        return {"marked_text": req.text, "glossary": {}}

    messages = [
        {"role": "system", "content": MARK_TERMS_PROMPT.format(text=req.text)},
    ]

    resp = await chat_completion(messages, temperature=0.3)
    raw = resp.choices[0].message.content.strip()

    try:
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
        result = json.loads(raw)
        return {
            "marked_text": result.get("marked_text", req.text),
            "glossary": result.get("glossary", {}),
        }
    except Exception:
        return {"marked_text": req.text, "glossary": {}}


def _build_profile_text(profile) -> str:
    if not profile:
        return "暂无学生画像，请用通用的学术语言进行解释。"
    import json
    return json.dumps({
        "专业": profile.major,
        "年级": profile.grade,
        "教育阶段": profile.education_level,
        "学科": profile.discipline,
        "知识基础": profile.knowledge_base,
        "薄弱点": profile.weak_points,
        "学习目标": profile.learning_goal,
    }, ensure_ascii=False)
