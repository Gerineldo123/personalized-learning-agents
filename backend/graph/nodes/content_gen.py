from graph.state import AgentGraphState
from agents.content_gen_agent import ContentGenAgent
from agents.base import AgentState

_content_gen_agent = ContentGenAgent()


async def content_gen_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await _content_gen_agent.process(agent_state)
    response = result.get("response", "")
    return {
        "response": response,
        "messages": [{"role": "assistant", "content": response}],
    }
