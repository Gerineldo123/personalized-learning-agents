# ContentGenAgent → Skills 渐进式迁移方案

## 背景

`ContentGenAgent` 当前通过内部方法分支实现四种资源生成，与 `BaseSkill` 系统并行存在，导致：
- Agent 面板无法直接调用文章/代码生成能力
- `quiz_gen` 在两套系统中重复实现
- 能力碎片化，LLM plan 节点无法感知所有可用工具

**目标**：以最小改动代价，让 Agent 面板获得 ContentGenAgent 的全部能力，同时不破坏 Workflow 子图和 Resource API 的现有逻辑。

---

## 设计原则

- **渐进迁移**，不全量重写
- ContentGenAgent 保留不动，Skill 内部**委托**给它
- Workflow 子图节点 **零改动**
- 每步可独立测试、独立回滚

---

## 改动步骤

### Step 1：新增 `ArticleGenSkill`

**文件**：`backend/agents/skills.py`

仿照 `PptGenSkill` 的委托模式，新增 `ArticleGenSkill`，内部调用 `ContentGenAgent._generate_article()`。

```python
class ArticleGenSkill(BaseSkill):
    name = "article_gen"
    description = "文章生成：根据知识点生成个性化学习文章，适用于需要详细讲解某个概念的任务"
    icon = "📄"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from agents.content_gen_agent import ContentGenAgent
        from agents.base import AgentState

        user_message = context.get("user_message", "")
        user_id = context.get("user_id", "")

        step_id = self.emit_step(workflow_outputs, "running", "生成学习文章", {
            "content": f"正在为「{user_message[:30]}」生成文章...",
            "sub_steps": [],
        })

        try:
            state = AgentState(
                user_id=user_id,
                user_message=user_message,
                resource_type="article",
                profile=context.get("profile"),
            )
            agent = ContentGenAgent()
            await agent._generate_article(state)

            import json
            resp = json.loads(state.get("response", "{}"))
            content = resp.get("content", "")

            self.emit_step(workflow_outputs, "completed", "生成学习文章", {
                "content": content,
                "sub_steps": ["✅ 文章生成完成"],
            }, step_id)

            return SkillResult(success=True, data={"article": content, "type": "article"}, summary="文章生成完成")
        except Exception as e:
            self.emit_step(workflow_outputs, "completed", "生成学习文章", {
                "content": f"生成失败: {str(e)}",
                "sub_steps": [f"❌ {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))
```

在 `init_skills()` 中注册：

```python
register_skill(ArticleGenSkill())
```

**风险**：低。ContentGenAgent 不改动，Workflow 不受影响。

---

### Step 2：新增 `CodeGenSkill`

同 Step 1，委托给 `ContentGenAgent._generate_code_case()`。

```python
class CodeGenSkill(BaseSkill):
    name = "code_gen"
    description = "代码案例生成：生成带注释的可运行代码示例，适用于编程概念教学"
    icon = "💡"
    # 内部委托给 ContentGenAgent._generate_code_case()
```

**风险**：低。

---

### Step 3：合并 `quiz_gen` 实现

当前 `QuizGenSkill`（`skills.py`）与 `ContentGenAgent._generate_quiz()` 逻辑重复。

**方案**：
1. 将 `QuizGenSkill.execute()` 改为委托给 `ContentGenAgent._generate_quiz(state)`
2. 接受 `context` 中的 `difficulty` 和 `question_count` 参数，传入 AgentState

```python
# QuizGenSkill.execute() 改为：
state = AgentState(
    user_id=user_id,
    user_message=user_message,
    resource_type="quiz",
    question_count=context.get("question_count", 5),
    difficulty=context.get("difficulty", "中等"),
    profile=context.get("profile"),
)
agent = ContentGenAgent()
await agent._generate_quiz(state)
```

**注意**：先保留原 QuizGenSkill 的 prompt 逻辑作为 fallback，确认委托正常后再删除重复代码。

**风险**：中。需测试 Agent 面板中 quiz 生成的格式是否与前端 `SkillStep.vue` 的 JSON 解析兼容。

---

### Step 4：将 `profile` 对象传入 Skill context

当前 Skills 的 `context` 字典不含学生画像（ORM 对象），导致委托后的 ContentGenAgent 拿不到 `profile`。

**方案**：在 `agent_execute.py` 的 `skills_node` 中，从 state 取出 `profile` 注入 context：

```python
# skills_node 中补充：
context = {
    "user_message": user_message,
    "user_id": user_id,
    "all_modules_data": ad,
    "profile": state.get("profile"),          # ← 新增
}
```

**影响范围**：`agent_execute.py` 1 处改动，Skills 接口不变（`context.get("profile")` 已经可以容错 None）。

**风险**：低。profile 为 None 时 ContentGenAgent 回退到"暂无学生画像"提示，不会崩溃。

---

### Step 5：更新 `agent_panel.py` 状态构建，加载 profile

当前 `/api/agent/execute/stream` 不加载 StudentProfile，导致 Step 4 的 profile 始终为 None。

**文件**：`backend/api/routes/agent_panel.py`

```python
# _make_state() 中补充从 DB 加载 profile：
from core.database import SessionLocal
from models.student import StudentProfile

def _make_state(req: AgentExecuteRequest) -> AgentGraphState:
    profile = None
    try:
        db = SessionLocal()
        profile = db.query(StudentProfile).filter(
            StudentProfile.user_id == req.user_id
        ).first()
        db.close()
    except Exception:
        pass

    return AgentGraphState(
        user_id=req.user_id,
        user_message=req.task_description,
        profile=profile,                          # ← 新增
        # ... 其余字段不变
    )
```

**风险**：低。profile 不存在时为 None，各 Skill 均有容错。

---

### Step 6（可选）：Resource API 路由支持 Skill 调用

当前 `/api/resources/generate` 直接调用 `ContentGenAgent`。若希望未来 Resource 模块也享受 Skill 系统的可扩展性，可在路由层增加一个分发逻辑：

```python
SKILL_TYPE_MAP = {
    "article": "article_gen",
    "quiz": "quiz_gen",
    "code": "code_gen",
    "ppt": "ppt_gen",
    "mindmap": "mindmap_gen",
}

async def gen_one(rtype: str):
    skill_name = SKILL_TYPE_MAP.get(rtype)
    skill = get_skill(skill_name) if skill_name else None
    if skill:
        await skill.execute(context, [])   # workflow_outputs 不用于此路由
    else:
        # fallback: 原有 ContentGenAgent 逻辑
        ...
```

**风险**：中高。SSE 事件格式与 Resource API 的响应格式不同，需验证前端 ResourcesView 的刷新逻辑。建议最后实施，或单独作为一个 PR。

---

## 步骤优先级与实施顺序

```
Step 4（profile 注入 context）
    ↓
Step 5（agent_panel 加载 profile）
    ↓
Step 1（ArticleGenSkill）
    ↓
Step 2（CodeGenSkill）
    ↓
Step 3（合并 quiz_gen）
    ↓
Step 6（可选：Resource API 接入）
```

Step 4 和 5 是前提依赖，需首先完成。Step 1、2 相互独立，可并行。Step 3 需在 Step 1/2 稳定后再合并，降低回滚代价。

---

## 改动文件清单

| 文件 | 改动类型 | 预计行数 |
|------|---------|---------|
| `backend/agents/skills.py` | 新增 ArticleGenSkill、CodeGenSkill；改造 QuizGenSkill | +80 行 |
| `backend/graph/subgraphs/agent_execute.py` | skills_node 中注入 profile | +3 行 |
| `backend/api/routes/agent_panel.py` | _make_state() 加载 profile | +12 行 |
| `backend/api/routes/resource.py` | （可选）接入 Skill 分发 | +20 行 |

**Workflow 子图、ContentGenAgent、前端代码：零改动。**

---

## 验证方法

每步完成后，在 Agent 面板输入以下测试 prompt，验证 plan 节点是否选择对应 skill：

| Prompt | 期望 selected_skills |
|--------|---------------------|
| "帮我写一篇关于递归算法的学习文章" | `["deep_search", "article_gen"]` |
| "给我出5道关于二叉树的练习题" | `["quiz_gen"]` |
| "用Python写一个快速排序的示例代码" | `["code_gen"]` 或 `["code_analysis"]` |
| "给我生成一个操作系统的思维导图" | `["mindmap_gen"]` |
