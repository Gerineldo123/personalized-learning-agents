## AI 对话去意图化后的模块联动方案

### 一、现状与问题

移除意图识别后，LangGraph 图退化为单节点：

```
START → chat_node → END
```

四个学习模块各自独立运作，无跨模块联动：

```
AI 对话 ──(独立)── ChatAgent
学习画像 ──(独立)── ProfileView API
错题本   ──(独立)── MistakeView API
学习资源 ──(独立)── ResourcesView API
```

**待解决的问题**：
1. ChatAgent 不知道学生有哪些错题、什么知识点薄弱
2. 学生在错题本中发现弱项后，无法从对话中自动获得针对性辅导
3. 学习资源、错题分析、画像更新三者互不感知，数据孤岛

---

### 二、新架构总览

核心思路：**AI 对话保留纯问答，同时成为各模块的"智能入口"——ChatAgent 读取全部画像数据来个性化回答，并在合适时机主动建议学生进入专项学习。**

```
                    ┌─────────────────────────┐
                    │       AI 对话 (chat)     │
                    │  读取: profile + mistakes│
                    │        + focus + quiz    │
                    │  输出: 回答 + 学习建议    │
                    └───────────┬─────────────┘
                                │ 建议触发
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
     │ 系统学习      │  │ 错题复习      │  │ 学习评估      │
     │ study_subgraph│  │ review_subgraph│ │ eval_subgraph │
     └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
            │                 │                 │
            ▼                 ▼                 ▼
     ┌─────────────────────────────────────────────────┐
     │              共享数据层                          │
     │  StudentProfile · MistakeQuestion · FocusSession│
     │  QuizRecord · LearningResource                  │
     └─────────────────────────────────────────────────┘
```

| 层级 | 说明 |
|---|---|
| AI 对话 | 纯问答 + 画像感知 + 主动建议。ChatAgent 回答时自动读取学生的最新画像、错题弱项、专注记录 |
| 工作流子图 | 独立 API 端点触发（POST /api/study/stream 等）。复用之前的 LangGraph 子图，每个内部按 plan 驱动 |
| 共享数据层 | 所有模块写入同一批数据库表，ChatAgent 和工作流节点都能读取最新状态 |

---

### 三、ChatAgent 增强：画像感知

#### 3.1 修改 ChatAgent 的 System Prompt

当前 ChatAgent 仅读 `profile.major/grade/knowledge_base/weak_points`。扩展为读取完整学习全貌：

```python
# agents/chat_agent.py 中 _profile_text 改动

def _profile_text(self, state: AgentState) -> str:
    p = state.get("profile")
    user_id = state.get("user_id")

    # 错题分析
    from core.database import SessionLocal
    from models.mistake_question import MistakeQuestion
    db = SessionLocal()
    try:
        mistakes = db.query(MistakeQuestion).filter(
            MistakeQuestion.user_id == user_id
        ).order_by(MistakeQuestion.created_at.desc()).limit(10).all()
        mistake_text = "、".join([
            m.question.get("question", "")[:40] if m.question else ""
            for m in mistakes
        ]) if mistakes else "无"
    finally:
        db.close()

    # 专注数据
    from stores.focus import FocusSession  # 或直接读 localStorage 无法在后端读
    # 专注数据已在之前的迭代中写入 focus_sessions 表，可直接查
    try:
        db2 = SessionLocal()
        sessions = db2.query(FocusSession).filter(
            FocusSession.user_id == user_id
        ).order_by(FocusSession.started_at.desc()).limit(20).all()
        total_min = sum(s.duration_min for s in sessions)
        completed = sum(1 for s in sessions if s.completed)
        focus_text = f"累计专注{total_min}分钟，完成率{completed}/{len(sessions)}" if sessions else "无专注记录"
        db2.close()
    except:
        focus_text = "无专注记录"

    return json.dumps({
        "专业": p.major,
        "年级": p.grade,
        "知识基础": p.knowledge_base,
        "薄弱知识点": p.weak_points,
        "学习目标": p.learning_goal,
        "最近错题": mistake_text,
        "专注情况": focus_text,
    }, ensure_ascii=False)
```

#### 3.2 ChatAgent 输出学习建议

Prompt 中增加一条规则：

```
在回答末尾，如果检测到以下情况，附加一个学习建议：
- 学生反复问某类问题（可能需要系统学习） → "建议你系统学习一下【主题】"
- 学生表达了困惑/出错 → "要不要我帮你分析一下错题，找出薄弱点？"
- 学生完成了多轮对话 → "想评估一下当前的学习水平吗？"

建议格式（前端可解析为按钮）：
[建议] 系统学习【{topic}】
[建议] 分析错题
[建议] 学习评估
```

前端解析 `[建议]` 文本，渲染为可点击按钮，点击后调对应的子图 API：

```typescript
// ChatView.vue 中解析
const suggestionMatch = content.match(/\[建议\]\s*(.+)/g)
if (suggestionMatch) {
  suggestions = suggestionMatch.map(s => ({
    text: s.replace('[建议] ', ''),
    action: s.includes('系统学习') ? 'study'
          : s.includes('错题') ? 'review'
          : s.includes('评估') ? 'evaluation'
          : null,
  }))
}
```

---

### 四、工作流子图独立 API

将 LangGraph 子图从主图剥离，变为独立 API 端点：

#### 4.1 路由文件结构

```
backend/api/routes/
├── chat.py          ← 已有（ChatAgent 纯问答）
├── study.py         ← 新建（学习工作流子图 API）
├── review.py        ← 新建（错题复习子图 API）
├── evaluation.py    ← 新建（评估工作流子图 API）
├── mistake.py       ← 已有（错题 CRUD + 分析 + 举一反三）
├── ...
```

#### 4.2 `backend/api/routes/study.py`

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from graph.state import AgentGraphState
from graph.subgraphs.study import study_subgraph
from core.database import SessionLocal
from core.sse import sse_stream
from models.student import StudentProfile
from services.safety_service import check_text_input

router = APIRouter(prefix="/api/study", tags=["系统学习"])


class StudyRequest(BaseModel):
    user_id: str
    topic: str
    history: list[dict] = []


@router.post("/stream")
async def study_stream(req: StudyRequest):
    safe_topic, ok = check_text_input(req.topic)
    if not ok:
        async def deny():
            yield "话题包含不当内容"
        return StreamingResponse(sse_stream(deny()), media_type="text/event-stream")

    db = SessionLocal()
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == req.user_id).first()
    db.close()

    initial_state: AgentGraphState = {
        "user_id": req.user_id,
        "user_message": safe_topic,
        "profile": profile,
        "history": req.history or [],
        "messages": [],
        "response": "",
        "agent_name": "",
        "task_plan": [],
        "agent_feedback": {},
        "completed_tasks": [],
        "all_modules_data": {},
    }

    async def event_stream():
        async for chunk in study_subgraph.astream(initial_state, stream_mode="updates"):
            for node_name, update in chunk.items():
                if "workflow_outputs" in update:
                    outputs = update["workflow_outputs"]
                    latest = outputs[-1] if isinstance(outputs, list) and outputs else {}
                    yield json.dumps({
                        "type": "stage",
                        "stage": latest.get("stage", node_name),
                        "data": latest.get("data", ""),
                    }, ensure_ascii=False)
                if "response" in update and update["response"]:
                    yield update["response"]

    return StreamingResponse(sse_stream(event_stream()), media_type="text/event-stream")
```

同理创建 `review.py` 和 `evaluation.py`（结构相同，替换子图和 request 字段）。

#### 4.3 注册路由

```python
# backend/main.py
from api.routes import study, review, evaluation

app.include_router(study.router)
app.include_router(review.router)
app.include_router(evaluation.router)
```

---

### 五、联动数据流

```
                        ┌──────────────────────────────────┐
                        │          StudentProfile           │
                        │  knowledge_base / weak_points     │
                        │  focus_stamina / focus_peak_hours │
                        └────┬──────────┬──────────┬───────┘
                             │ 读取     │ 写入     │ 读取
                  ┌──────────┘          │          └──────────┐
                  ▼                     ▼                     ▼
           ┌────────────┐     ┌──────────────┐      ┌────────────┐
           │ ChatAgent  │     │profile_update│      │ ChatAgent  │
           │ (每次对话) │     │ (评估后更新) │      │ (下次对话) │
           └────────────┘     └──────────────┘      └────────────┘

                        ┌──────────────────────────────────┐
                        │        MistakeQuestion            │
                        │  question / user_answer / analysis│
                        └────┬──────────┬──────────┬───────┘
                             │ 读取     │ 写入     │ 读取
                  ┌──────────┘          │          └──────────┐
                  ▼                     ▼                     ▼
           ┌────────────┐     ┌──────────────┐      ┌────────────┐
           │ ChatAgent  │     │错题本API     │      │review_subgr│
           │ (感知弱项) │     │(答题后记录)  │      │(分析弱项)  │
           └────────────┘     └──────────────┘      └────────────┘

                        ┌──────────────────────────────────┐
                        │        LearningResource           │
                        │  resource_type / content / title  │
                        └────┬──────────────────────────────┘
                             │ 写入
                             ▼
                    ┌──────────────┐
                    │ study_subgraph│
                    │ (生成资源后)  │
                    └──────────────┘
```

**具体场景**：

| 场景 | 数据流 |
|---|---|
| 学生在 AI 对话中问了很多导数问题 | ChatAgent 感知到 `profile.weak_points: ["导数"]`，回答末尾附 `[建议] 系统学习【导数】`。学生点击 → 前端调 `POST /api/study/stream { topic: "导数" }` → study_subgraph 读取 profile + mistakes，生成针对性内容 |
| 学生在错题本做了一套导数题，答错率高 | `mistake_analysis` 写入 `MistakeQuestion.analysis` → 下次对话时 ChatAgent 读取到 | 
| 学生完成一次系统学习 + 评估 | `evaluation_subgraph` 输出评估 → `profile_update` 更新 `StudentProfile.weak_points` → 下次对话 ChatAgent 自动感知新画像 |
| 学生多天未学习 | ChatAgent 读取 `FocusSession` → 提示"你最近专注时间减少了" |

---

### 六、前端交互

#### 6.1 ChatView 新增建议按钮

ChatAgent 返回的 `[建议]` 文本被解析为内联按钮：

```
┌──────────────────────────────────┐
│ AI: 导数是微积分的基础，你问了   │
│ 好几个相关问题，可能基础不够扎实  │
│                                  │
│ [建议] 系统学习【导数】           │ ← 可点击按钮
│ [建议] 分析做题情况               │ ← 可点击按钮
└──────────────────────────────────┘
```

点击建议 → 前端调对应子图 API，以 SSE 流式展示进度：

```
系统学习中...
  ✓ 分析当前水平
  ✓ 生成学习内容
  → 审核中...
  → 生成练习题...
✓ 完成
```

#### 6.2 前端 API 调用

```typescript
// frontend/src/api/study.ts
import api from './index'

export function studyStream(
  userId: string, topic: string, history: any[],
  onChunk: (chunk: string) => void,
  onStage: (stage: string, data: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
) {
  // SSE 流式调用 POST /api/study/stream
  // 解析 stage 事件 → onStage
  // 解析文本 → onChunk
}
```

---

### 七、文件变更清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/agents/chat_agent.py` | 修改 | `_profile_text()` 读取 mistakes + focus；prompt 增建议规则 |
| `backend/api/routes/study.py` | **新建** | `POST /api/study/stream` |
| `backend/api/routes/review.py` | **新建** | `POST /api/review/stream` |
| `backend/api/routes/evaluation.py` | **新建** | `POST /api/evaluation/stream` |
| `backend/main.py` | 修改 | 注册三个新路由 |
| `frontend/src/api/study.ts` | **新建** | SSE 流式调用 |
| `frontend/src/views/ChatView.vue` | 修改 | 解析 `[建议]` 渲染按钮；点击调子图 API |
| `backend/graph/builder.py` | 保持不变 | （主图仍是 chat_node，子图被独立 API 直接调用） |

---

### 八、效果对比

| 指标 | 之前（全挂图） | 去意图后（各独立） | 本方案 |
|---|---|---|---|
| 一次普通对话 LLM 调用 | 2 次 | 1 次 | 1 次 |
| 一次系统学习 LLM 调用 | 4-5 次 | 不可用 | 4-5 次 |
| ChatAgent 是否知画像 | ✅ | ❌ | ✅ |
| ChatAgent 是否知错题 | ❌ | ❌ | ✅ |
| ChatAgent 是否知专注 | ❌ | ❌ | ✅ |
| 能否从对话触发学习 | ✅（自动） | ❌ | ✅（建议式） |
| 模块间数据感知 | 同一 state | 零 | 同一 DB 表 |
