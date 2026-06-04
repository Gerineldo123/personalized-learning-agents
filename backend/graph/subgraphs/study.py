from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from graph.state import AgentGraphState
from graph.nodes.profile_analysis import profile_analysis_node
from graph.nodes.study_content import study_content_node
from graph.nodes.content_review import content_review_node
from graph.nodes.study_mindmap import study_mindmap_node
from graph.nodes.quiz_gen import quiz_gen_node
from graph.nodes.study_summary import study_summary_node

_PLAN = ["profile_analysis", "study_content", "content_review"]
_ALL = set(_PLAN) | {"study_mindmap", "quiz_gen", "study_summary"}


def _router(state: AgentGraphState) -> str:
    done = {t["agent"] for t in (state.get("completed_tasks") or [])}
    for step in _PLAN:
        if step not in done:
            return step
    return "study_summary"


def _after_review(state: AgentGraphState):
    fb = state.get("agent_feedback", {})
    if fb.get("needs_regeneration"):
        return "study_content"
    if state.get("profile_analysis", {}).get("current_level") == "高级":
        return "quiz_gen"
    return [Send("study_mindmap", state), Send("quiz_gen", state)]


_b = StateGraph(AgentGraphState)
_b.add_node("profile_analysis", profile_analysis_node)
_b.add_node("study_content", study_content_node)
_b.add_node("content_review", content_review_node)
_b.add_node("study_mindmap", study_mindmap_node)
_b.add_node("quiz_gen", quiz_gen_node)
_b.add_node("study_summary", study_summary_node)

_b.set_entry_point("profile_analysis")
for step in _PLAN:
    if step != "content_review":
        _b.add_conditional_edges(step, _router, {n: n for n in _ALL})

_b.add_conditional_edges(
    "content_review", _after_review,
    ["study_content", "study_mindmap", "quiz_gen"],
)
_b.add_edge("study_mindmap", "study_summary")
_b.add_edge("quiz_gen", "study_summary")
_b.add_edge("study_summary", END)

study_subgraph = _b.compile()
