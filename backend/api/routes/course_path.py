import json
import asyncio
from fastapi import APIRouter
from core.database import SessionLocal
from core.llm_client import chat_completion
from models.course_path import CoursePath
from models.student import StudentProfile
from models.resource import LearningResource
from agents.base import AgentState
from agents.content_gen_agent import ContentGenAgent

router = APIRouter(prefix="/api/path/course", tags=["课程学习路径"])

COURSE_PATH_PROMPT = """你是一个学习路径规划专家。根据学生在某门课程上的薄弱点，规划一条分步补救学习路径，只返回JSON。

课程名称：{course_name}
薄弱知识点：{knowledge_points}
困难类型：{difficulty_types}
影响范围：{impacts}
学习目标：{goal}
推荐策略：{strategies}
学科基础：{knowledge_base}
能力评分：{ability_scores}

返回JSON格式：
{{
  "steps": [
    {{
      "order": 1,
      "title": "步骤标题（简洁，10字以内）",
      "description": "本步骤要做什么、为什么这样做（50字以内）",
      "duration_estimate": "预计耗时（如30分钟、1小时）",
      "resource_queries": ["可用于搜索系统资源库的关键词"],
      "checkpoint": "验收标准：做完这一步应能回答什么问题或完成什么任务"
    }}
  ]
}}

设计规则：
- 步骤数5-8步，从最基础的缺口补起，逐步深入
- 每个步骤聚焦一个具体的知识缺口，不要泛泛而谈
- 结合推荐策略设计步骤内容（如真题强化→配真题训练步骤；概念精讲→配概念梳理步骤）
- resource_queries 提供1-3个可用于检索学习资源的关键词
- checkpoint 必须是可验证的，不要「理解原理」这种模糊表述
- {hallu}
只返回JSON，不要其他内容。"""


@router.get("/list")
def list_course_paths(user_id: str):
    db = SessionLocal()
    try:
        paths = db.query(CoursePath).filter(
            CoursePath.user_id == user_id,
            CoursePath.status.in_(["active", "completed"]),
        ).order_by(CoursePath.updated_at.desc()).all()
        return {"items": [
            {"id": p.id, "course_name": p.course_name, "steps": p.steps,
             "total_steps": p.total_steps, "done_steps": p.done_steps,
             "progress": p.progress, "status": p.status,
             "created_at": p.created_at.isoformat() if p.created_at else None}
            for p in paths
        ]}
    finally:
        db.close()


@router.get("")
def get_course_path(user_id: str, course_name: str):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).filter(
            CoursePath.user_id == user_id,
            CoursePath.course_name == course_name,
            CoursePath.status == "active",
        ).first()
        if not path:
            return {"found": False, "user_id": user_id, "course_name": course_name}
        return {
            "found": True,
            "id": path.id,
            "course_name": path.course_name,
            "steps": path.steps,
            "total_steps": path.total_steps,
            "done_steps": path.done_steps,
            "progress": path.progress,
            "status": path.status,
            "created_at": path.created_at.isoformat() if path.created_at else None,
        }
    finally:
        db.close()


@router.patch("/{path_id}/step/{step_order}")
def update_step_status(path_id: int, step_order: int, done: bool = True):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).filter(CoursePath.id == path_id).first()
        if not path:
            return {"ok": False, "message": "路径不存在"}
        steps = list(path.steps or [])
        for s in steps:
            if s.get("order") == step_order:
                s["status"] = "done" if done else "pending"
                if done and not s.get("completed_at"):
                    from datetime import datetime, timezone
                    s["completed_at"] = datetime.now(timezone.utc).isoformat()
                elif not done:
                    s.pop("completed_at", None)
                break
        path.steps = steps
        path.done_steps = sum(1 for s in steps if s.get("status") == "done")
        path.total_steps = len(steps)
        path.progress = round(path.done_steps / max(path.total_steps, 1), 4)
        if path.progress >= 1.0:
            path.status = "completed"
        db.commit()
        db.refresh(path)

        # 步骤完成时异步更新画像 + 直接更新知识点掌握度
        if done:
            step_title = next((s.get("title", "") for s in steps if s.get("order") == step_order), "")

            # 方案二+三：步骤标题匹配知识点，滑动平均更新掌握度
            from services.kp_service import match_kp, update_knowledge_base, set_course_kp_scores
            matched = match_kp(step_title)
            if matched:
                update_knowledge_base(db, path.user_id, {kp: 0.8 for kp in matched})

            # 方案三：课程整体完成时，该课所有知识点设为 0.85
            if path.status == "completed":
                set_course_kp_scores(db, path.user_id, path.course_name, 0.85)

            import asyncio as _asyncio
            from agents.profile_agent import ProfileAgent
            from agents.base import AgentState as _AgentState
            _asyncio.create_task(ProfileAgent().process(
                _AgentState(user_id=path.user_id, user_message=f"完成学习路径步骤「{step_title}」（{path.course_name}），更新知识掌握画像"),
                trigger="path_step",
            ))
        return {
            "ok": True,
            "id": path.id,
            "step_order": step_order,
            "done": done,
            "progress": path.progress,
            "done_steps": path.done_steps,
            "total_steps": path.total_steps,
            "status": path.status,
        }
    finally:
        db.close()


@router.post("/generate")
async def generate_course_path(
    user_id: str,
    course_name: str,
    knowledge_points: str = "",
    difficulty_types: str = "",
    impacts: str = "",
    goal: str = "",
    strategies: str = "",
):
    db = SessionLocal()
    try:
        profile = db.query(StudentProfile).filter(
            StudentProfile.user_id == user_id
        ).first()
        kb = json.dumps(profile.knowledge_base or {}, ensure_ascii=False) if profile else "{}"
        as_json = json.dumps(profile.ability_scores or {}, ensure_ascii=False) if profile else "{}"

        existing = db.query(CoursePath).filter(
            CoursePath.user_id == user_id,
            CoursePath.course_name == course_name,
            CoursePath.status == "active",
        ).first()
        if existing:
            existing.status = "archived"
            db.commit()

        resp = await chat_completion([
            {"role": "user", "content": COURSE_PATH_PROMPT.format(
                course_name=course_name,
                knowledge_points=knowledge_points,
                difficulty_types=difficulty_types or "未指定",
                impacts=impacts or "未指定",
                goal=goal or "扎实基础",
                strategies=strategies or "概念精讲、循序渐进",
                knowledge_base=kb,
                ability_scores=as_json,
                hallu="严格基于学生已有的薄弱信息，不要编造知识点",
            )}
        ], temperature=0.4)

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        data = json.loads(raw)
        steps = data.get("steps", [])
        for s in steps:
            s.setdefault("status", "pending")
            s.setdefault("completed_at", None)

        path = CoursePath(
            user_id=user_id,
            course_name=course_name,
            steps=steps,
            total_steps=len(steps),
            done_steps=0,
            progress=0.0,
            status="active",
        )
        db.add(path)
        db.commit()
        db.refresh(path)

        return {
            "ok": True,
            "id": path.id,
            "course_name": path.course_name,
            "steps": path.steps,
            "total_steps": path.total_steps,
            "done_steps": path.done_steps,
            "progress": path.progress,
        }
    finally:
        db.close()


@router.post("/{path_id}/generate-resources")
async def generate_path_resources(path_id: int, user_id: str):
    db = SessionLocal()
    try:
        path = db.query(CoursePath).filter(CoursePath.id == path_id).first()
        if not path:
            return {"ok": False, "message": "路径不存在"}

        steps = list(path.steps or [])

        async def gen_for_step(step: dict):
            existing_ids = list(step.get("resource_ids", []) or [])
            if existing_ids:
                return

            title = step.get("title", "")
            desc = step.get("description", "")
            topic = f"{path.course_name} - {title}：{desc}" if desc else f"{path.course_name} - {title}"

            article = AgentState(user_id=user_id, user_message=topic, resource_type="article", course_name=path.course_name)
            quiz = AgentState(user_id=user_id, user_message=topic, resource_type="quiz", course_name=path.course_name)
            agent = ContentGenAgent()
            await asyncio.gather(agent.process(article), agent.process(quiz))

            new_ids: list[int] = []
            resource_info: list[dict] = []
            for st in [article, quiz]:
                rid = st.get("resource_db_id")
                rtype = st.get("resource_type", "")
                if rid:
                    res = db.query(LearningResource).get(rid)
                    if res:
                        new_ids.append(rid)
                        resource_info.append({"id": rid, "title": res.title, "type": rtype})

            step["resource_ids"] = new_ids
            step["resources"] = resource_info

        await asyncio.gather(*[gen_for_step(s) for s in steps])

        path.steps = steps
        db.commit()
        db.refresh(path)

        return {
            "ok": True,
            "id": path.id,
            "steps": path.steps,
            "total_steps": path.total_steps,
            "done_steps": path.done_steps,
            "progress": path.progress,
        }
    finally:
        db.close()
