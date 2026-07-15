import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from agents.content_gen_agent import _completion_text  # noqa: E402


class ContentGenerationStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_text_forwards_each_stream_token(self):
        async def chunks():
            for text in ["第一段", "第二段", "第三段"]:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
                )

        received = []
        with patch(
            "agents.content_gen_agent.chat_completion",
            new=AsyncMock(return_value=chunks()),
        ):
            content = await _completion_text(
                [{"role": "user", "content": "测试"}],
                temperature=0.5,
                on_token=received.append,
            )

        self.assertEqual(content, "第一段第二段第三段")
        self.assertEqual(received, ["第一段", "第二段", "第三段"])


if __name__ == "__main__":
    unittest.main()
