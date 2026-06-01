from langgraph.graph import StateGraph, START, END

from graph.state import AgentGraphState
from graph.nodes.intent import classify_intent
from graph.nodes.chat import chat_node
from graph.nodes.profile import profile_node
from graph.nodes.content_gen import content_gen_node
from graph.nodes.mindmap import mindmap_node
from graph.nodes.evaluation import evaluation_node

VALID_AGENTS = {"chat", "profile", "content_gen", "mindmap", "evaluation"}


def route_by_agent(state: AgentGraphState) -> str:
    """根据 intent_classifier 写入的 agent_name 进行条件路由"""
    agent_name = state.get("agent_name", "").lower()
    if agent_name in VALID_AGENTS:
        return agent_name

    # 模糊匹配
    for name in VALID_AGENTS:
        if name in agent_name or agent_name in name:
            return name

    return "chat"


def compile_graph():
    """构建并编译 StateGraph"""
    builder = StateGraph(AgentGraphState)

    # 注册节点
    builder.add_node("intent_classifier", classify_intent)
    builder.add_node("chat", chat_node)
    builder.add_node("profile", profile_node)
    builder.add_node("content_gen", content_gen_node)
    builder.add_node("mindmap", mindmap_node)
    builder.add_node("evaluation", evaluation_node)

    # 入口边：START → intent_classifier
    builder.add_edge(START, "intent_classifier")

    # 条件边：intent_classifier → 各 Agent 节点
    builder.add_conditional_edges(
        "intent_classifier",
        route_by_agent,
        {
            "chat": "chat",
            "profile": "profile",
            "content_gen": "content_gen",
            "mindmap": "mindmap",
            "evaluation": "evaluation",
        },
    )

    # 所有 Agent 节点执行完即结束
    for name in VALID_AGENTS:
        builder.add_edge(name, END)

    return builder.compile()
