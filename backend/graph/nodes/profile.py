from graph.state import AgentGraphState
from agents.profile_agent import ProfileAgent
from agents.base import AgentState

_profile_agent = ProfileAgent()


async def profile_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await _profile_agent.process(agent_state)
    response = result.get("response", "")
    return {
        "response": response,
        "profile": result.get("profile"),
        "messages": [{"role": "assistant", "content": response}],
    }
