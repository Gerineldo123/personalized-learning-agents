import os
import re

from core.llm_client import chat_completion


SENSITIVE_KEYWORDS = [
    "违法", "赌博", "色情", "诈骗", "暴力",
    "毒品", "枪支", "恐怖", "洗钱",
]

SAFE_CONTEXT_TERMS = [
    "暴力枚举", "暴力搜索", "暴力递归", "暴力解法", "暴力匹配", "穷举",
]

SAFETY_CHECK_PROMPT = """判断以下学习内容是否安全合规。只回复"安全"或"不安全"。
不安全标准：涉及违法、色情、暴力伤害、诈骗、毒品、枪支、恐怖主义等内容。
内容：{content}"""

UNSAFE_FALLBACK = "[系统提示] 该内容未通过安全审核，已被过滤。"

HALLUCINATION_DISCLAIMER = (
    "可信生成要求：严格围绕学生问题、课程知识点和系统已有资料作答；"
    "不确定的信息必须明确标注“不确定/需进一步查证”；"
    "不得编造教材出处、实验数据、论文、链接或学生画像；"
    "涉及知识点时尽量点明对应课程节点与知识点标签。"
)


class SafetyService:
    def __init__(self, enable_llm_check: bool = False):
        self.enable_llm_check = enable_llm_check
        self.keyword_pattern = re.compile(
            "|".join(re.escape(x) for x in SENSITIVE_KEYWORDS), re.IGNORECASE
        )

    def _keyword_hit(self, content: str) -> str | None:
        text = content or ""
        normalized = text.lower()
        for term in SAFE_CONTEXT_TERMS:
            normalized = normalized.replace(term.lower(), "")
        match = self.keyword_pattern.search(normalized)
        return match.group(0) if match else None

    async def check(self, content: str) -> bool:
        if not (content or "").strip():
            return True
        if self._keyword_hit(content):
            return False
        if not self.enable_llm_check:
            return True
        try:
            resp = await chat_completion([
                {"role": "user", "content": SAFETY_CHECK_PROMPT.format(content=content[:3000])}
            ], temperature=0)
            verdict = (resp.choices[0].message.content or "").strip()
            return "不安全" not in verdict
        except Exception:
            return True

    async def check_and_sanitize(self, content: str) -> tuple[str, bool]:
        if await self.check(content):
            return content, True
        return UNSAFE_FALLBACK, False


_safety = SafetyService(enable_llm_check=os.getenv("ENABLE_LLM_SAFETY", "").lower() in {"1", "true", "yes"})


async def check_text(content: str) -> tuple[str, bool]:
    return await _safety.check_and_sanitize(content)


def check_text_input(content: str) -> tuple[str, bool]:
    if not (content or "").strip():
        return "", True
    if _safety._keyword_hit(content):
        return UNSAFE_FALLBACK, False
    return content, True


def hallu_rules() -> str:
    return HALLUCINATION_DISCLAIMER
