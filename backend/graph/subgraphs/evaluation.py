from langgraph.graph import StateGraph, END

from graph.state import AgentGraphState
from graph.nodes.evaluation import evaluation_node
from graph.nodes.profile_update import profile_update_node
from graph.nodes.path_suggest import path_suggest_node
from graph.nodes.study_summary import study_summary_node

_PLAN = ["evaluation", "profile_update", "path_suggest"]
_ALL = set(_PLAN) | {"study_summary"}


def _router(state: AgentGraphState) -> str:
    done = {t["agent"] for t in (state.get("completed_tasks") or [])}
    for step in _PLAN:
        if step not in done:
            return step
    return "study_summary"


_b = StateGraph(AgentGraphState)
_b.add_node("evaluation", evaluation_node)
_b.add_node("profile_update", profile_update_node)
_b.add_node("path_suggest", path_suggest_node)
_b.add_node("study_summary", study_summary_node)

_b.set_entry_point("evaluation")
for step in _PLAN:
    _b.add_conditional_edges(step, _router, {n: n for n in _ALL})

_b.add_edge("study_summary", END)

evaluation_subgraph = _b.compile()
