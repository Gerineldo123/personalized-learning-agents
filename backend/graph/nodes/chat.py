from graph.state import AgentGraphState
from agents.chat_agent import ChatAgent
from agents.base import AgentState

_chat_agent = ChatAgent()


async def chat_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    # ChatAgent.process() 只返回 state 不做实际处理，
    # 实际逻辑在 stream() 中，这里需要收集流式输出
    collected = ""
    async for chunk in _chat_agent.stream(agent_state):
        collected += chunk
    response = agent_state.get("response", collected)
    return {
        "response": response,
        "messages": [{"role": "assistant", "content": response}],
    }
