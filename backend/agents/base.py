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

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        ...

    async def stream(self, state: AgentState) -> AsyncGenerator[str, None]:
        result = await self.process(state)
        yield result.get("response", "")
