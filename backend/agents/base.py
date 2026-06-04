import json
from abc import ABC, abstractmethod
from typing import AsyncGenerator
from models.student import StudentProfile


class AgentState(dict):
    user_id: str
    user_message: str
    profile: StudentProfile | None
    history: list

    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class BaseAgent(ABC):
    name: str = ""
    description: str = ""
    tools: list[str] = []

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        ...

    async def stream(self, state: AgentState) -> AsyncGenerator[str, None]:
        result = await self.process(state)
        yield result.get("response", "")

    async def use_tool(self, tool_name: str, **kwargs):
        from agents.tools import TOOL_MAP
        handler = TOOL_MAP.get(tool_name)
        if not handler:
            return {"error": f"Tool not found: {tool_name}"}
        try:
            result = handler(**kwargs)
            if hasattr(result, "__await__"):
                result = await result
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_loop(self, messages: list, state: AgentState) -> str:
        """JSON-driven tool-calling loop (no LangChain required)."""
        from core.llm_client import chat_completion
        from agents.tools import TOOL_MAP, TOOL_DESC

        available = [n for n in (self.tools or []) if n in TOOL_MAP]
        if not available:
            resp = await chat_completion(messages, temperature=0.7)
            return resp.choices[0].message.content

        tool_system = (
            f"你可以调用以下工具获取信息：\n{TOOL_DESC}\n\n"
            "需要调用工具时返回 JSON：{\"tool_call\": \"工具名\", \"arguments\": {\"param\": \"value\"}}\n"
            "不需要工具时直接回答。"
        )
        msgs = [{"role": "system", "content": tool_system}] + messages

        for _ in range(5):
            resp = await chat_completion(msgs, temperature=0.3)
            content = resp.choices[0].message.content.strip()
            try:
                if content.startswith("{"):
                    call = json.loads(content)
                    tool_name = call.get("tool_call", "")
                    if tool_name in available:
                        result = await self.use_tool(tool_name, **call.get("arguments", {}))
                        msgs.append({"role": "assistant", "content": content})
                        msgs.append({"role": "user", "content": f"工具结果：{json.dumps(result, ensure_ascii=False)}"})
                        continue
            except (json.JSONDecodeError, KeyError):
                pass
            return content

        return "无法在有限次数内完成任务"
