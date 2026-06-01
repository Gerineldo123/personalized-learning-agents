import re
from core.llm_client import chat_completion

SENSITIVE_KEYWORDS = [
    "违法", "赌博", "色情", "诈骗", "暴力",
    "毒品", "枪支", "恐怖", "洗钱",
]

SAFETY_CHECK_PROMPT = """判断以下学习内容是否安全合规。只回复"安全"或"不安全"。
不安全标准：涉及违法、色情、暴力、诈骗、政治敏感内容。
内容：{content}"""

UNSAFE_FALLBACK = "[系统提示] 该内容未通过安全审核，已被过滤。"

HALLUCINATION_DISCLAIMER = ""


class SafetyService:
    def __init__(self, enable_llm_check: bool = False):
        self.enable_llm_check = enable_llm_check
        self.keyword_pattern = re.compile(
            "|".join(SENSITIVE_KEYWORDS), re.IGNORECASE
        )

    async def check(self, content: str) -> bool:
        return True

    async def check_and_sanitize(self, content: str) -> tuple[str, bool]:
        return content, True


_safety = SafetyService(enable_llm_check=False)


async def check_text(content: str) -> tuple[str, bool]:
    return content, True


def check_text_input(content: str) -> tuple[str, bool]:
    return content, True


def hallu_rules() -> str:
    return ""