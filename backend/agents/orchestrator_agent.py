import json

from agents.base import BaseAgent, AgentState
from graph.subgraphs.resource_orchestration import DEFAULT_RESOURCE_TYPES, resource_orchestration_graph


class OrchestratorAgent(BaseAgent):
    name = "orchestrator"
    description = "多智能体协同编排：画像诊断、资源规划、并行生成、知识点绑定"

    async def process(self, state: AgentState) -> AgentState:
        graph_state = {
            "user_id": state.get("user_id"),
            "user_message": state.get("user_message", ""),
            "profile": state.get("profile"),
            "history": state.get("history", []),
            "messages": [],
            "response": "",
            "agent_name": self.name,
            "task_plan": [],
            "agent_feedback": {},
            "completed_tasks": [],
            "all_modules_data": state.get("all_modules_data") or {},
            "course_name": state.get("course_name"),
            "knowledge_points": state.get("knowledge_points") or [],
            "requested_resource_types": state.get("requested_resource_types") or DEFAULT_RESOURCE_TYPES,
            "generated_resources": [],
            "orchestration_failures": [],
            "orchestration_events": [],
            "skill_result_items": [],
            "skill_workflow_outputs": [],
        }
        result = await resource_orchestration_graph.ainvoke(graph_state)

        resources = result.get("generated_resources") or []
        failures = result.get("orchestration_failures") or []
        state["course_name"] = result.get("course_name")
        state["knowledge_points"] = result.get("knowledge_points") or []
        state["profile_analysis"] = result.get("profile_analysis") or {}
        state["generated_resources"] = resources
        state["orchestration_failures"] = failures
        state["workflow_outputs"] = result.get("workflow_outputs") or []
        state["response"] = json.dumps({
            "agent": self.name,
            "orchestration": "LangGraph: profile_diagnosis -> resource_plan -> article_gen -> parallel_resource_gen -> safety_review -> graph_tagging -> path_update -> finalize",
            "course_name": state.get("course_name"),
            "knowledge_points": state.get("knowledge_points") or [],
            "profile_analysis": state.get("profile_analysis") or {},
            "generated_resources": resources,
            "failures": failures,
            "steps_completed": [item.get("resource_type") for item in resources],
        }, ensure_ascii=False)
        return state
