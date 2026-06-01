from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class AgentGraphState(TypedDict):
    user_id: str
    user_message: str
    profile: Any
    history: list[dict]
    messages: Annotated[list, add_messages]
    response: str
    agent_name: str
