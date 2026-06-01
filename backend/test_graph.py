"""
LangGraph Phase 1 测试脚本

测试内容：
1. 图编译是否成功
2. 意图分类节点是否正确路由
3. 各 Agent 节点是否正常执行
4. astream 模式是否正确输出

使用方式：
    cd backend
    python test_graph.py

注意：需要配置 .env 中的 SPARK_API_KEY 等环境变量才能实际调用 LLM。
"""
import sys
import asyncio

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from agents.registry import register, get_all_agents
from agents.profile_agent import ProfileAgent
from agents.content_gen_agent import ContentGenAgent
from agents.mindmap_agent import MindMapAgent
from agents.evaluation_agent import EvaluationAgent
from agents.chat_agent import ChatAgent

# 注册 Agent（模拟 main.py 的启动流程）
register(ProfileAgent())
register(ContentGenAgent())
register(MindMapAgent())
register(EvaluationAgent())
register(ChatAgent())


async def test_graph_compile():
    """测试 1：图编译"""
    print("=" * 50)
    print("测试 1：图编译")
    from graph.builder import compile_graph
    graph = compile_graph()
    assert graph is not None
    print(f"  ✓ 图编译成功: {type(graph).__name__}")
    print(f"  ✓ 节点列表: {list(graph.nodes.keys())}")
    return graph


async def test_intent_classification():
    """测试 2：意图分类节点"""
    print("\n" + "=" * 50)
    print("测试 2：意图分类节点")
    from graph.nodes.intent import classify_intent

    test_cases = [
        {"user_message": "什么是Python装饰器？", "expected": "chat"},
        {"user_message": "帮我生成一份关于微积分的学习资料", "expected": "content_gen"},
        {"user_message": "生成一个Python知识体系的思维导图", "expected": "mindmap"},
        {"user_message": "评估一下我的学习情况", "expected": "evaluation"},
        {"user_message": "我是大二计算机专业的学生", "expected": "profile"},
    ]

    for case in test_cases:
        state = {
            "user_id": "test",
            "user_message": case["user_message"],
            "history": [],
            "messages": [],
            "response": "",
            "agent_name": "",
            "profile": None,
        }
        try:
            result = await classify_intent(state)
            agent_name = result.get("agent_name", "")
            match = "✓" if case["expected"] in agent_name.lower() else "✗"
            print(f"  {match} '{case['user_message'][:20]}...' → {agent_name} (期望: {case['expected']})")
        except Exception as e:
            print(f"  ✗ '{case['user_message'][:20]}...' → 错误: {e}")


async def test_graph_invoke():
    """测试 3：完整图执行"""
    print("\n" + "=" * 50)
    print("测试 3：完整图执行 (ainvoke)")
    from graph.builder import compile_graph
    graph = compile_graph()

    initial_state = {
        "user_id": "test_user",
        "user_message": "什么是Python装饰器？",
        "history": [],
        "messages": [],
        "response": "",
        "agent_name": "",
        "profile": None,
    }

    try:
        result = await graph.ainvoke(initial_state)
        print(f"  ✓ agent_name: {result.get('agent_name', '')}")
        response = result.get("response", "")
        print(f"  ✓ response 长度: {len(response)} 字符")
        print(f"  ✓ response 前 100 字: {response[:100]}...")
    except Exception as e:
        print(f"  ✗ 执行失败: {e}")


async def test_graph_astream():
    """测试 4：流式图执行"""
    print("\n" + "=" * 50)
    print("测试 4：流式图执行 (astream updates)")
    from graph.builder import compile_graph
    graph = compile_graph()

    initial_state = {
        "user_id": "test_user",
        "user_message": "什么是Python装饰器？",
        "history": [],
        "messages": [],
        "response": "",
        "agent_name": "",
        "profile": None,
    }

    try:
        chunks = []
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, update in chunk.items():
                print(f"  → 节点 '{node_name}' 输出 keys: {list(update.keys())}")
                if update.get("response"):
                    chunks.append(update["response"])
        print(f"  ✓ 共收到 {len(chunks)} 个 response chunk")
        if chunks:
            print(f"  ✓ 最终 response 前 100 字: {chunks[-1][:100]}...")
    except Exception as e:
        print(f"  ✗ 流式执行失败: {e}")


async def test_route_by_agent():
    """测试 5：路由函数"""
    print("\n" + "=" * 50)
    print("测试 5：route_by_agent 路由函数")
    from graph.builder import route_by_agent

    test_cases = [
        ({"agent_name": "chat"}, "chat"),
        ({"agent_name": "profile"}, "profile"),
        ({"agent_name": "content_gen"}, "content_gen"),
        ({"agent_name": "mindmap"}, "mindmap"),
        ({"agent_name": "evaluation"}, "evaluation"),
        ({"agent_name": "unknown"}, "chat"),
        ({"agent_name": ""}, "chat"),
        ({"agent_name": "content_generation"}, "content_gen"),
    ]

    for state, expected in test_cases:
        result = route_by_agent(state)
        match = "✓" if result == expected else "✗"
        print(f"  {match} agent_name='{state['agent_name']}' → {result} (期望: {expected})")


async def main():
    print("LangGraph Phase 1 测试")
    print("=" * 50)
    print(f"已注册 Agent: {[a.name for a in get_all_agents()]}")

    # 测试 1 & 5 不需要 LLM 调用
    await test_graph_compile()
    await test_route_by_agent()

    # 测试 2, 3, 4 需要 LLM 调用
    from services.config_service import is_configured
    if is_configured("main"):
        await test_intent_classification()
        await test_graph_invoke()
        await test_graph_astream()
    else:
        print("\n⚠ 未配置 LLM API，跳过需要 LLM 调用的测试 (2, 3, 4)")
        print("  请在 .env 中配置 SPARK_API_KEY / SPARK_BASE_URL 后重新运行")

    print("\n" + "=" * 50)
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
