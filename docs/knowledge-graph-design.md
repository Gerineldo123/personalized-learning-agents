# 知识图谱模块设计方案

> 学习画像 → 知识图谱（按培养方案）

## 一、整体架构

```
培养方案 (Curriculum)
    └── 课程节点 (Course Node)       ← 图谱第一层（本文档重点）
            └── 知识点图谱 (KP Graph)  ← 点击课程后展开/跳转
```

两级联动：宏观（培养方案维度）+ 微观（课程内知识点维度）。

---

## 二、培养方案数据来源

系统面向学习者，无管理员角色，培养方案数据采用 **A+B 混合方案**：

### 方案 A：内置默认培养方案

预置主流专业的培养方案为静态 JSON 文件（与现有 `knowledge_graph_cs.json` 同目录）：

```
/static/curriculum_cs.json        # 计算机科学与技术
/static/curriculum_se.json        # 软件工程
/static/curriculum_math.json      # 数学
/static/curriculum_ai.json        # 人工智能
```

文件格式：

```json
[
  {
    "course_name": "离散数学",
    "semester": 2,
    "category": "必修",
    "prerequisites": ["高等数学"]
  },
  {
    "course_name": "数据结构",
    "semester": 3,
    "category": "必修",
    "prerequisites": ["离散数学", "程序设计基础"]
  }
]
```

学生在问卷建档时选择**专业 + 年级**，系统加载对应文件作为初始培养方案。

### 方案 B：AI 解析上传的培养方案

学生可将学校培养方案文本/PDF 内容粘贴到输入框，调用 LLM 提取结构化数据：

```
POST /api/curriculum/parse
Body: { "text": "<粘贴的培养方案原文>" }
```

LLM Prompt 核心指令：提取课程列表，识别每门课的学期、类别和先修关系，输出与内置格式相同的 JSON。解析结果经学生确认后保存，**覆盖**内置默认方案。

> 亮点：AI 解析能力体现系统智能化，同时兼容任意学校的课程体系。

---

## 三、数据模型

### 3.1 后端新增表

```python
# backend/models/curriculum.py

class Curriculum(Base):
    """学生个人培养方案（A=内置加载，B=AI解析后存储）"""
    user_id: int
    course_name: str
    semester: int       # 建议学期 1~8，决定分层布局纵坐标
    category: str       # "必修" | "选修" | "通识"
    prerequisites: JSON # ["离散数学", "高等数学"]  → 驱动图谱连线
    source: str         # "preset" | "ai_parsed"


class UserCourseStatus(Base):
    """学生课程学习状态（与现有 CoursePath 联动更新）"""
    user_id: int
    course_name: str
    status: str         # "completed" | "learning" | "planned" | "not_started"
```

`prerequisites` 字段直接驱动图谱有向边，无需手工维护边列表。

### 3.2 接口

```
GET /api/curriculum/graph?user_id={id}
POST /api/curriculum/parse       # 方案B：AI解析培养方案文本
```

`GET` 响应示例：

```json
{
  "nodes": [
    {"id": "离散数学",     "semester": 2, "category": "必修", "status": "completed"},
    {"id": "数据结构",     "semester": 3, "category": "必修", "status": "learning"},
    {"id": "人工智能导论", "semester": 5, "category": "选修", "status": "not_started"}
  ],
  "links": [
    {"source": "离散数学",  "target": "数据结构"},
    {"source": "数据结构",  "target": "人工智能导论"}
  ]
}
```

---

## 四、图谱层级交互

### 4.1 第一层：课程图谱（培养方案视角）

**节点状态与视觉编码**

| 状态 | 颜色 | 说明 |
|------|------|------|
| `completed`   | 绿色实心 `#52c41a` | 已完成 |
| `learning`    | 蓝色脉冲 `#1890ff` + ripple 动画 | 正在学习 |
| `planned`     | 蓝色空心 `#69b1ff` | 已列入计划 |
| `not_started` | 灰色 `#d9d9d9` | 培养方案中但未开始 |

**边的含义**

有向边 `A → B` 表示 A 是 B 的前置课程，方向揭示学习顺序依赖链。

**布局策略**

- 主推：**分层布局**，X 轴 = 学期，Y 轴 = 课程类别，语义清晰
- 备选：ECharts `force` 力导向，自动聚类相关课程

### 4.2 第二层：知识点图谱（课程内视角）

点击课程节点后，**弹出侧边面板或切换子视图**，展示该课程内部知识点图谱：

- 复用现有 `KnowledgeGraph.vue`（ECharts graph + force 布局）
- 节点颜色逻辑沿用现有掌握度着色（绿/橙/红/灰）
- 新增：知识点节点标注"推荐学习顺序"编号

---

## 五、前端核心实现

### 5.1 组件结构

```
ProfileView.vue
  └── CurriculumGraph.vue      ← 新增：第一层课程图谱
          └── KnowledgeGraph.vue  ← 已有：第二层知识点图谱（复用）
```

### 5.2 ECharts 关键配置

```js
// 节点颜色映射
const statusColor = {
  completed:   '#52c41a',
  learning:    '#1890ff',
  planned:     '#69b1ff',
  not_started: '#d9d9d9'
}

// learning 状态节点加涟漪动画（视觉突出"当前进行时"）
nodes = nodes.map(n => n.status === 'learning'
  ? { ...n, symbol: 'circle', itemStyle: { color: statusColor.learning },
      emphasis: { scale: true } }
  : n
)

// 点击节点展开知识点图谱
chart.on('click', ({ data }) => {
  if (data.status !== 'not_started') {
    emit('open-course-detail', data.id)
  }
})
```

---

## 六、与现有系统的联动

| 触发事件 | 联动动作 |
|----------|----------|
| `CoursePath.status` 变为 `completed` | `UserCourseStatus` 同步更新为 `completed` |
| 新建 `CoursePath`（active） | `UserCourseStatus` 更新为 `learning` |
| AI Agent 推荐下一门课 | 对应节点高亮为"推荐"状态 |
| 点击课程节点 | 切换到该课程知识点图谱（复用现有组件） |

---

## 六、亮点总结（答辩用）

1. **两级联动**：培养方案课程图谱 → 课程内知识点图谱，宏观+微观双视角
2. **学习进度可视化**：节点颜色/动画直观反映已完成/进行中/待学三种状态，个人学习轨迹一图呈现
3. **先修关系建模**：有向边揭示知识依赖链，学习顺序一目了然
4. **个性化**：同一培养方案下，每个学生的点亮路径不同，图谱即个人学习画像
5. **AI Agent 联动**：图谱"推荐下一步节点"可直接触发 LangGraph Agent 生成对应课程的学习路径

---

## 七、实施优先级

| 优先级 | 内容 | 工作量 |
|--------|------|--------|
| P0 核心 | `Curriculum` 数据模型 + `/curriculum/graph` 接口 + `CurriculumGraph.vue` 组件 | 中 |
| P1 亮点 | 点击课程节点展开知识点图谱（复用现有 `KnowledgeGraph.vue`） | 小 |
| P2 加分 | `learning` 节点脉冲动画 + AI 推荐节点高亮 + 分层学期布局 | 小 |

现有基础：ECharts 已引入、`KnowledgeGraph.vue` 已有力导向图实现、`CoursePath` 课程状态已存在。P0 主要工作量在后端数据模型和接口，前端改造量较小。
