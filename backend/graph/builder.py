from langgraph.graph import StateGraph, START, END

from graph.state import AgentGraphState
from graph.nodes.chat import chat_node


def _build_graph(checkpointer=None):
    b = StateGraph(AgentGraphState)
    b.add_node("chat", chat_node)
    b.add_edge(START, "chat")
    b.add_edge("chat", END)
    return b.compile(checkpointer=checkpointer)


def compile_graph(checkpointer=None):
    return _build_graph(checkpointer=checkpointer)
