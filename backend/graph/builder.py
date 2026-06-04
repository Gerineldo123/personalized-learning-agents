from langgraph.graph import StateGraph, START, END

from graph.state import AgentGraphState
from graph.nodes.intent import classify_intent
from graph.nodes.chat import chat_node
from graph.nodes.profile import profile_node
from graph.nodes.content_gen import content_gen_node
from graph.nodes.mindmap import mindmap_node
from graph.subgraphs.study import study_subgraph
from graph.subgraphs.review import review_subgraph
from graph.subgraphs.evaluation import evaluation_subgraph

_SIMPLE = {"chat", "profile", "content_gen", "mindmap"}
_WORKFLOWS = {"study", "review", "evaluation"}


def _dispatch(state: AgentGraphState) -> str:
    intent = state.get("agent_name", "chat")
    if intent in _SIMPLE:
        return intent
    if intent in _WORKFLOWS:
        return f"{intent}_subgraph"
    return "chat"


def _build_graph(checkpointer=None):
    b = StateGraph(AgentGraphState)

    b.add_node("intent_classifier", classify_intent)
    b.add_node("chat", chat_node)
    b.add_node("profile", profile_node)
    b.add_node("content_gen", content_gen_node)
    b.add_node("mindmap", mindmap_node)
    b.add_node("study_subgraph", study_subgraph)
    b.add_node("review_subgraph", review_subgraph)
    b.add_node("evaluation_subgraph", evaluation_subgraph)

    b.add_edge(START, "intent_classifier")
    b.add_conditional_edges(
        "intent_classifier",
        _dispatch,
        {
            "chat": "chat",
            "profile": "profile",
            "content_gen": "content_gen",
            "mindmap": "mindmap",
            "study_subgraph": "study_subgraph",
            "review_subgraph": "review_subgraph",
            "evaluation_subgraph": "evaluation_subgraph",
        },
    )
    for n in _SIMPLE:
        b.add_edge(n, END)
    for w in _WORKFLOWS:
        b.add_edge(f"{w}_subgraph", END)

    return b.compile(checkpointer=checkpointer)


def compile_graph(checkpointer=None):
    return _build_graph(checkpointer=checkpointer)
