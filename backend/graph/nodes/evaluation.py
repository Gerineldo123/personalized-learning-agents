from graph.state import AgentGraphState
from agents.evaluation_agent import EvaluationAgent
from agents.base import AgentState

_evaluation_agent = EvaluationAgent()


async def evaluation_node(state: AgentGraphState) -> dict:
    agent_state = AgentState(
        user_id=state["user_id"],
        user_message=state["user_message"],
        profile=state.get("profile"),
        history=state.get("history", []),
    )
    result = await _evaluation_agent.process(agent_state)
    response = result.get("response", "")
    return {
        "response": response,
        "messages": [{"role": "assistant", "content": response}],
    }
