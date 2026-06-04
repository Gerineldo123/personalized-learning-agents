import json
from graph.state import AgentGraphState
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.mistake_question import MistakeQuestion

MISTAKE_PROMPT = """你是一个学习诊断专家。分析以下错题记录，找出薄弱知识点。

错题记录：
{mistakes}

返回JSON：
{{
  "weak_topics": ["薄弱知识点1", "薄弱知识点2"],
  "error_patterns": ["常见错误模式"],
  "priority_topic": "最需要复习的知识点",
  "review_suggestion": "复习建议"
}}
只返回JSON。"""


async def mistake_analysis_node(state: AgentGraphState) -> dict:
    db = SessionLocal()
    try:
        mistakes = db.query(MistakeQuestion).filter(
            MistakeQuestion.user_id == state["user_id"]
        ).order_by(MistakeQuestion.created_at.desc()).limit(20).all()

        if not mistakes:
            return {
                "mistake_analysis": {"weak_topics": [], "priority_topic": ""},
                "response": json.dumps({"message": "暂无错题记录"}, ensure_ascii=False),
            }

        mistake_text = "\n".join([
            f"- 题目: {json.dumps(m.question, ensure_ascii=False)[:100]}, "
            f"用户答案: {m.user_answer}, 正确答案: {m.correct_answer}"
            for m in mistakes
        ])

        resp = await chat_completion([
            {"role": "user", "content": MISTAKE_PROMPT.format(mistakes=mistake_text)}
        ], temperature=0.3)

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        try:
            analysis = json.loads(raw)
        except json.JSONDecodeError:
            analysis = {
                "weak_topics": [],
                "error_patterns": [],
                "priority_topic": state["user_message"],
                "review_suggestion": "",
            }

        completed = list(state.get("completed_tasks") or [])
        completed.append({"agent": "mistake_analysis", "result_summary": f"薄弱点:{analysis.get('weak_topics', [])}"})

        return {
            "mistake_analysis": analysis,
            "user_message": analysis.get("priority_topic") or state["user_message"],
            "agent_feedback": {
                "weaknesses_found": analysis.get("weak_topics", []),
                "task_completed": True,
            },
            "workflow_outputs": [{"stage": "mistake_analysis", "data": analysis}],
            "completed_tasks": completed,
        }
    finally:
        db.close()
