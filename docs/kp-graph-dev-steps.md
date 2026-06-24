# 知识图谱两级联动 — 开发步骤文档

> 目标：点击课程节点后，在课程图谱下方原地展开该课程的知识点图谱，叠加画像掌握度数据着色，不跳转页面。

---

## 一、整体改动范围

```
backend/static/kp/           ← 新增：每门课的知识点图谱 JSON
frontend/src/components/profile/CurriculumGraph.vue  ← 修改：点击行为 + 传递 knowledgeBase
frontend/src/views/ProfileView.vue                   ← 修改：传递 knowledgeBase 给 CurriculumGraph
```

---

## 二、Step 1：预制知识点图谱 JSON 数据

### 2.1 目录结构

在 `backend/static/` 下新建 `kp/` 目录，每门课一个 JSON 文件：

```
backend/static/kp/
  高等数学.json
  线性代数.json
  概率论与数理统计.json
  离散数学.json
  程序设计基础.json
  面向对象程序设计.json
  数据结构.json
  算法设计与分析.json
  数据库系统.json
  操作系统.json
  计算机网络.json
  软件工程.json
  机器学习.json
  深度学习.json
  计算机视觉.json
  自然语言处理.json
```

### 2.2 JSON 格式规范

```json
{
  "nodes": [
    {"id": "极限", "category": 0},
    {"id": "导数", "category": 0},
    {"id": "积分", "category": 1},
    {"id": "多元函数", "category": 1},
    {"id": "级数", "category": 2}
  ],
  "links": [
    {"source": "极限", "target": "导数"},
    {"source": "导数", "target": "积分"},
    {"source": "积分", "target": "多元函数"},
    {"source": "多元函数", "target": "级数"}
  ],
  "categories": [
    {"name": "基础"},
    {"name": "核心"},
    {"name": "进阶"}
  ]
}
```

字段说明：
- `nodes[].id`：知识点名称，**必须与画像 `knowledge_base` 中的 key 对应**（用于掌握度着色）
- `links`：知识点之间的学习先后依赖关系
- `categories`：分组名称，用于图例显示

### 2.3 各课程知识点参考

以下列出每门课的核心知识点，可直接据此生成 JSON：

**高等数学**
节点：极限、连续、导数、微分、不定积分、定积分、多元函数微分、重积分、曲线积分、级数
依赖链：极限→连续→导数→微分→不定积分→定积分→多元函数微分→重积分→曲线积分→级数

**线性代数**
节点：行列式、矩阵运算、线性方程组、向量空间、特征值与特征向量、二次型、矩阵分解
依赖链：行列式→矩阵运算→线性方程组→向量空间→特征值与特征向量→二次型→矩阵分解

**离散数学**
节点：命题逻辑、谓词逻辑、集合论、关系、函数、图论基础、树、组合数学
依赖链：命题逻辑→谓词逻辑→集合论→关系→函数→图论基础→树→组合数学

**数据结构**
节点：数组与链表、栈与队列、树与二叉树、堆、图、排序算法、查找算法、哈希表
依赖链：数组与链表→栈与队列→树与二叉树→堆→图→排序算法→查找算法→哈希表

**算法设计与分析**
节点：复杂度分析、分治、动态规划、贪心、回溯、图算法、NP问题
依赖链：复杂度分析→分治→动态规划→贪心→回溯→图算法→NP问题

**机器学习**
节点：线性回归、逻辑回归、决策树、支持向量机、集成方法、聚类、降维、模型评估
依赖链：线性回归→逻辑回归→决策树→支持向量机→集成方法；线性回归→聚类→降维；决策树→模型评估

**深度学习**
节点：神经网络基础、反向传播、卷积神经网络、循环神经网络、注意力机制、Transformer、生成模型、训练技巧
依赖链：神经网络基础→反向传播→卷积神经网络→循环神经网络→注意力机制→Transformer→生成模型；反向传播→训练技巧

> 其余课程同理，按"基础→核心→进阶"方向建立依赖链。

---

## 三、Step 2：后端新增知识点图谱接口

在 `backend/api/routes/curriculum.py` 新增一个接口，按课程名返回对应 JSON 文件：

```python
@router.get("/kp/{course_name}")
def get_course_kp(course_name: str):
    """返回单门课程的知识点图谱 JSON"""
    path = os.path.join(_STATIC_DIR, "kp", f"{course_name}.json")
    if not os.path.exists(path):
        return {"nodes": [], "links": [], "categories": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

接口路径：`GET /api/curriculum/kp/{course_name}`

---

## 四、Step 3：ProfileView 传递 knowledgeBase

`ProfileView.vue` 已有 `knowledgeGraphData` 计算属性（`profile.knowledge_base`），将其传给 `CurriculumGraph`：

```html
<!-- ProfileView.vue 第 619 行附近 -->
<CurriculumGraph
  :userId="userStore.userId"
  :major="profile.major"
  :knowledgeBase="knowledgeGraphData"
  @node-click="(id) => router.push({ path: '/resources', query: { search: id } })"
/>
```

同时更新 `CurriculumGraph.vue` 的 Props 定义，接收 `knowledgeBase`：

```ts
const props = defineProps<{
  userId: string
  major?: string
  knowledgeBase?: Record<string, number>  // 新增
}>()
```

---

## 五、Step 4：修改 CurriculumGraph 点击行为

### 5.1 移除 router.push，改为展开知识点面板

```ts
chart.on('click', async (p: any) => {
  if (p.dataType !== 'node') return
  const courseName = p.data.id

  // 切换：点同一节点则收起
  if (selectedCourse.value === courseName) {
    selectedCourse.value = null
    return
  }

  selectedCourse.value = courseName

  // 加载该课程的知识点图谱
  try {
    const res = await api.get(`/curriculum/kp/${encodeURIComponent(courseName)}`)
    courseKpData.value = res.data
  } catch {
    courseKpData.value = { nodes: [], links: [], categories: [] }
  }
})
```

新增状态变量：
```ts
const courseKpData = ref<{ nodes: any[]; links: any[]; categories: any[] } | null>(null)
```

### 5.2 知识点图谱渲染：复用 KnowledgeGraph 组件

将 `knowledgeBase` 按课程知识点过滤后传入 `KnowledgeGraph`：

```ts
const filteredKb = computed(() => {
  if (!courseKpData.value || !props.knowledgeBase) return {}
  const nodeIds = new Set(courseKpData.value.nodes.map((n: any) => n.id))
  return Object.fromEntries(
    Object.entries(props.knowledgeBase).filter(([k]) => nodeIds.has(k))
  )
})
```

模板中 KnowledgeGraph 改为静态传入图谱数据：

```html
<div v-if="selectedCourse && courseKpData" class="kp-section">
  <div class="kp-header">
    <span class="kp-title">{{ selectedCourse }} · 知识点图谱</span>
    <el-button size="small" text @click="selectedCourse = null">收起</el-button>
  </div>
  <KnowledgeGraph
    :knowledgeBase="filteredKb"
    :graphData="courseKpData"
  />
</div>
```

---

## 六、Step 5：KnowledgeGraph 支持外部传入图谱数据

`KnowledgeGraph.vue` 目前只能通过 `discipline` 字段加载预置 JSON，需新增一个可选 prop `graphData` 让外部直接传入：

```ts
const props = defineProps<{
  knowledgeBase: Record<string, number>
  discipline?: string
  graphData?: { nodes: any[]; links: any[]; categories: any[] } | null  // 新增
}>()
```

在 `loadGraph` 中优先使用外部传入数据：

```ts
async function loadGraph() {
  if (props.graphData) {
    graphData = props.graphData   // 直接使用，不再 fetch
  } else {
    // 原有 discipline → fetch JSON 逻辑保持不变
    const file = resolveGraphFile(props.discipline)
    if (file && !graphData) {
      try {
        const r = await fetch(file)
        graphData = await r.json()
      } catch { graphData = null }
    }
  }
  // ...后续渲染逻辑不变
}
```

同时 `watch` 新增监听 `graphData` 变化：

```ts
watch(() => props.graphData, () => {
  graphData = null  // 清空缓存，触发重渲染
  loadGraph()
})
```

---

## 七、实施顺序

```
Step 1  预制知识点 JSON 文件（数据工作，可并行）
Step 2  后端新增 /kp/{course_name} 接口（10分钟）
Step 3  ProfileView 传递 knowledgeBase（5分钟）
Step 4  CurriculumGraph 修改点击行为（20分钟）
Step 5  KnowledgeGraph 支持外部 graphData（15分钟）
```

Step 1 数据量最大，建议先完成 5-8 门核心课（高等数学、数据结构、算法、机器学习、深度学习），足够演示效果，其余课程后补。

---

## 八、最终交互效果

```
画像页 → 知识图谱区域
  └── 课程图谱（按培养方案，节点颜色=学习状态）
        ↓ 点击任意课程节点
  └── 课程内知识点图谱（力导向图，节点颜色=掌握度）
        绿色：掌握度≥80%
        橙色：掌握度50-80%
        红色：掌握度<50%
        灰色：未评估
        紫色：推荐下一步学习（前置已掌握，自身未掌握）
```

答辩演示路径：登录 → 画像页 → 看到整体知识图谱（点亮/未点亮） → 点击"机器学习" → 展开内部知识点 → AI自动标注"推荐下一步"。
