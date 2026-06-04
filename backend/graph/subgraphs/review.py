from langgraph.graph import StateGraph, END

from graph.state import AgentGraphState
from graph.nodes.mistake_analysis import mistake_analysis_node
from graph.nodes.study_content import study_content_node
from graph.nodes.content_review import content_review_node
from graph.nodes.quiz_gen import quiz_gen_node
from graph.nodes.study_summary import study_summary_node

_PLAN = ["mistake_analysis", "study_content", "content_review"]
_ALL = set(_PLAN) | {"quiz_gen", "study_summary"}


def _router(state: AgentGraphState) -> str:
    done = {t["agent"] for t in (state.get("completed_tasks") or [])}
    for step in _PLAN:
        if step not in done:
            return step
    return "study_summary"


def _after_review(state: AgentGraphState) -> str:
    if state.get("agent_feedback", {}).get("needs_regeneration"):
        return "study_content"
    return "quiz_gen"


_b = StateGraph(AgentGraphState)
_b.add_node("mistake_analysis", mistake_analysis_node)
_b.add_node("study_content", study_content_node)
_b.add_node("content_review", content_review_node)
_b.add_node("quiz_gen", quiz_gen_node)
_b.add_node("study_summary", study_summary_node)

_b.set_entry_point("mistake_analysis")
for step in ["mistake_analysis", "study_content"]:
    _b.add_conditional_edges(step, _router, {n: n for n in _ALL})

_b.add_conditional_edges(
    "content_review", _after_review, ["study_content", "quiz_gen"]
)
_b.add_edge("quiz_gen", "study_summary")
_b.add_edge("study_summary", END)

review_subgraph = _b.compile()
