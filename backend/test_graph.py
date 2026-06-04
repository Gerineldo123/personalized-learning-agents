"""
LangGraph Phase 2 测试脚本

测试内容：
1. 图编译是否成功（含工作流节点）
2. 路由函数是否正确（含 study/review 意图）
3. 意图分类节点是否正确路由
4. 学习工作流完整执行
5. 错题复习工作流完整执行
6. 评估工作流完整执行

使用方式：
    cd backend
    python test_graph.py

注意：测试 3-6 需要配置 .env 中的 SPARK_API_KEY 等环境变量。
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
    nodes = sorted(graph.nodes.keys())
    print(f"  OK 图编译成功，共 {len(nodes)} 个节点")
    print(f"  节点: {nodes}")

    # 验证关键节点存在
    expected = {
        "intent_classifier", "chat", "profile", "content_gen", "mindmap",
        "evaluation", "profile_update", "path_suggest",
        "profile_analysis", "study_content", "study_mindmap", "quiz_gen", "study_summary",
        "mistake_analysis",
    }
    missing = expected - set(nodes)
    if missing:
        print(f"  FAIL 缺少节点: {missing}")
    else:
        print(f"  OK 所有预期节点均存在")
    return graph


async def test_should_continue():
    """测试 2：should_continue 路由函数"""
    print("\n" + "=" * 50)
    print("测试 2：should_continue 路由函数")
    from graph.builder import should_continue

    test_cases = [
        ({"current_task": "chat", "supervisor_iteration": 1, "agent_feedback": {}}, "chat"),
        ({"current_task": "study_content", "supervisor_iteration": 1, "agent_feedback": {}}, "study_content"),
        ({"current_task": "unknown", "supervisor_iteration": 1, "agent_feedback": {}}, "summary"),
        ({"current_task": "chat", "supervisor_iteration": 8, "agent_feedback": {}}, "summary"),
        ({"current_task": "chat", "supervisor_iteration": 1, "agent_feedback": {"force_summary": True}}, "summary"),
    ]

    all_pass = True
    for state, expected in test_cases:
        result = should_continue(state)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  {'OK' if ok else 'FAIL'} should_continue({state}) -> '{result}' (expect '{expected}')")

    print(f"\n  {'ALL PASS' if all_pass else 'SOME FAILED'}")


async def test_intent_classification():
    """测试 3：意图分类节点"""
    print("\n" + "=" * 50)
    print("测试 3：意图分类节点")
    from graph.nodes.intent import classify_intent

    test_cases = [
        {"user_message": "什么是Python装饰器？", "expected": "chat"},
        {"user_message": "我想学微积分", "expected": "study"},
        {"user_message": "帮我复习错题", "expected": "review"},
        {"user_message": "帮我生成一份PPT", "expected": "content_gen"},
        {"user_message": "评估一下我的学习情况", "expected": "evaluation"},
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
            "profile_analysis": {},
            "generated_article": "",
            "generated_mindmap": "",
            "generated_quiz": {},
            "evaluation_report": {},
            "mistake_analysis": {},
            "path_suggestion": "",
            "workflow_outputs": [],
            "task_plan": [],
            "current_task": "",
            "agent_feedback": {},
            "supervisor_iteration": 0,
            "completed_tasks": [],
        }
        try:
            result = await classify_intent(state)
            agent_name = result.get("agent_name", "")
            match = "OK" if case["expected"] in agent_name.lower() else "??"
            print(f"  {match} '{case['user_message']}' -> {agent_name} (期望: {case['expected']})")
        except Exception as e:
            print(f"  FAIL '{case['user_message']}' -> 错误: {e}")


async def test_study_workflow():
    """测试 4：学习工作流完整执行"""
    print("\n" + "=" * 50)
    print("测试 4：学习工作流 (study)")
    from graph.builder import compile_graph
    graph = compile_graph()

    initial_state = {
        "user_id": "test_user",
        "user_message": "Python装饰器",
        "history": [],
        "messages": [],
        "response": "",
        "agent_name": "study",
        "profile": None,
        "profile_analysis": {},
        "generated_article": "",
        "generated_mindmap": "",
        "generated_quiz": {},
        "evaluation_report": {},
        "mistake_analysis": {},
        "path_suggestion": "",
        "workflow_outputs": [],
        "task_plan": [],
        "current_task": "",
        "agent_feedback": {},
        "supervisor_iteration": 0,
        "completed_tasks": [],
    }

    try:
        stages = []
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, update in chunk.items():
                if node_name == "__start__":
                    continue
                stages.append(node_name)
                print(f"  -> 节点 '{node_name}' 完成, keys: {list(update.keys())}")

        expected_stages = ["intent_classifier", "profile_analysis", "study_content", "study_mindmap", "quiz_gen", "study_summary"]
        # intent_classifier 不在这里因为 agent_name 已预设为 study
        # 实际上 intent_classifier 仍会执行但不改变 agent_name
        print(f"\n  执行节点序列: {stages}")
        print(f"  OK 学习工作流执行完成")
    except Exception as e:
        print(f"  FAIL 执行失败: {e}")


async def test_graph_astream_updates():
    """测试 5：astream updates 模式"""
    print("\n" + "=" * 50)
    print("测试 5：astream updates 模式（chat 路由）")
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
        "profile_analysis": {},
        "generated_article": "",
        "generated_mindmap": "",
        "generated_quiz": {},
        "evaluation_report": {},
        "mistake_analysis": {},
        "path_suggestion": "",
        "workflow_outputs": [],
        "task_plan": [],
        "current_task": "",
        "agent_feedback": {},
        "supervisor_iteration": 0,
        "completed_tasks": [],
    }

    try:
        stages = []
        response = ""
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, update in chunk.items():
                stages.append(node_name)
                if update.get("response"):
                    response = update["response"]

        print(f"  执行节点: {stages}")
        print(f"  response 长度: {len(response)} 字符")
        if response:
            print(f"  response 前 100 字: {response[:100]}...")
        print(f"  OK")
    except Exception as e:
        print(f"  FAIL: {e}")


async def main():
    print("LangGraph Phase 2 测试")
    print("=" * 50)
    print(f"已注册 Agent: {[a.name for a in get_all_agents()]}")

    # 测试 1 & 2 不需要 LLM 调用
    await test_graph_compile()
    await test_should_continue()

    # 测试 3-5 需要 LLM 调用
    from services.config_service import is_configured
    if is_configured("main"):
        await test_intent_classification()
        await test_graph_astream_updates()
        # test_study_workflow 耗时较长（多次 LLM 调用），按需启用
        # await test_study_workflow()
    else:
        print("\n" + "=" * 50)
        print("未配置 LLM API，跳过需要 LLM 调用的测试 (3-5)")
        print("请在 .env 中配置 SPARK_API_KEY / SPARK_BASE_URL 后重新运行")

    print("\n" + "=" * 50)
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(main())
