import type { AgentStep } from '../types/agent'

const demoStepsRaw = [
  {
    stepType: 'thinking' as const,
    title: '分析任务需求',
    delay: 0,
    updates: [
      { delay: 300, status: 'running' as const, data: { content: '正在分析任务：斐波那契数列跨学科分析...\n' } },
      { delay: 600, status: 'running' as const, data: { content: '正在分析任务：斐波那契数列跨学科分析...\n\n识别到以下子任务：\n1. 斐波那契数列数学原理\n2. 自然界中的斐波那契模式\n3. 黄金比例与美学\n4. 编程实现与可视化\n' } },
      { delay: 1000, status: 'running' as const, data: { content: '正在分析任务：斐波那契数列跨学科分析...\n\n识别到以下子任务：\n1. 斐波那契数列数学原理\n2. 自然界中的斐波那契模式\n3. 黄金比例与美学\n4. 编程实现与可视化\n\n开始搜索相关资料...\n' } },
      { delay: 1200, status: 'completed' as const, data: { content: '正在分析任务：斐波那契数列跨学科分析...\n\n识别到以下子任务：\n1. 斐波那契数列数学原理\n2. 自然界中的斐波那契模式\n3. 黄金比例与美学\n4. 编程实现与可视化\n\n搜索策略已确定，调用 Tavily API...' } },
    ],
  },
  {
    stepType: 'search' as const,
    title: 'Tavily Search: Fibonacci sequence nature applications',
    delay: 1400,
    updates: [
      { delay: 100, status: 'running' as const, data: { query: 'Fibonacci sequence nature golden ratio applications', results: [], answer: '' } },
      { delay: 800, status: 'completed' as const, data: {
        query: 'Fibonacci sequence nature golden ratio applications',
        answer: 'The Fibonacci sequence appears extensively in nature, from the arrangement of leaves (phyllotaxis) to the spiral patterns of galaxies. The golden ratio (approximately 1.618) emerges from the ratio of consecutive Fibonacci numbers. In mathematics, it has connections to the Binet formula and matrix exponentiation.',
        results: [
          {
            title: 'Fibonacci Numbers and the Golden Ratio - Math is Fun',
            url: 'https://www.mathsisfun.com/numbers/fibonacci-sequence.html',
            snippet: 'The Fibonacci Sequence is the series of numbers: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34... The next number is found by adding up the two numbers before it. When we take any two successive Fibonacci Numbers, their ratio is very close to the Golden Ratio φ which is approximately 1.618034...',
          },
          {
            title: 'The Fibonacci Sequence in Nature - ScienceDirect',
            url: 'https://www.sciencedirect.com/topics/mathematics/fibonacci-sequence',
            snippet: 'The Fibonacci sequence appears in biological settings, such as branching in trees, arrangement of leaves on a stem, the fruitlets of a pineapple, the flowering of artichoke, and the arrangement of a pine cone. The patterns often optimize exposure to sunlight and other environmental factors.',
          },
          {
            title: 'Fibonacci Sequence: Definition, Formula, List and Examples',
            url: 'https://www.geeksforgeeks.org/fibonacci-sequence/',
            snippet: 'The Fibonacci formula is F(n) = F(n-1) + F(n-2). Applications include computer algorithms like Fibonacci search, financial market analysis using Fibonacci retracement levels, and the design of aesthetically pleasing compositions in architecture and art.',
          },
          {
            title: 'Magical Fibonacci Numbers and the Golden Ratio - YouTube',
            url: 'https://www.youtube.com/watch?v=SjSHVDfXHQ4',
            snippet: 'A fascinating exploration of how Fibonacci numbers connect mathematics, nature, and art. Learn about the rabbit problem that started it all, and how the sequence appears in sunflowers, pinecones, and even the Parthenon.',
          },
          {
            title: 'Applications of Fibonacci Numbers in Computer Science',
            url: 'https://arxiv.org/abs/example-fibonacci-cs',
            snippet: 'Fibonacci numbers have numerous applications in computer science including: Fibonacci heaps for priority queues, Fibonacci search technique for optimization, dynamic programming examples, and analysis of recursive algorithms. The computation of large Fibonacci numbers is a classic problem for testing algorithmic efficiency.',
          },
        ],
      }},
    ],
  },
  {
    stepType: 'memory' as const,
    title: '更新知识库',
    delay: 2400,
    updates: [
      { delay: 200, status: 'running' as const, data: { action: 'read' as const, key: 'fibonacci_context', value: '从长期记忆中检索已有的斐波那契相关知识...' } },
      { delay: 500, status: 'completed' as const, data: { action: 'write' as const, key: 'fibonacci_analysis_2026', value: '斐波那契数列跨学科分析：数学原理(递推公式)、自然界应用(叶序、松果)、黄金比例(φ≈1.618)、算法优化(矩阵快速幂)、可视化(黄金螺旋)' } },
    ],
  },
  {
    stepType: 'code' as const,
    title: '计算斐波那契数列 (JavaScript)',
    delay: 3000,
    updates: [
      { delay: 200, status: 'running' as const, data: {
        language: 'javascript' as const,
        code: 'function fibonacci(n) {\n  if (n <= 1) return n\n  let a = 0, b = 1\n  for (let i = 2; i <= n; i++) {\n    [a, b] = [b, a + b]\n  }\n  return b\n}\n\nconsole.log(`F(10) = ${fibonacci(10)}`)\nconsole.log(`F(20) = ${fibonacci(20)}`)\nconsole.log(`F(30) = ${fibonacci(30)}`)\n\nconst phi = (1 + Math.sqrt(5)) / 2\nconsole.log(`黄金比例 φ = ${phi.toFixed(6)}`)\n\nconst ratio = fibonacci(30) / fibonacci(29)\nconsole.log(`F(30)/F(29) = ${ratio.toFixed(6)} ≈ φ`)\n',
        output: '',
        status: 'running' as const,
      }},
      { delay: 1000, status: 'completed' as const, data: {
        language: 'javascript' as const,
        code: 'function fibonacci(n) {\n  if (n <= 1) return n\n  let a = 0, b = 1\n  for (let i = 2; i <= n; i++) {\n    [a, b] = [b, a + b]\n  }\n  return b\n}\n\nconsole.log(`F(10) = ${fibonacci(10)}`)\nconsole.log(`F(20) = ${fibonacci(20)}`)\nconsole.log(`F(30) = ${fibonacci(30)}`)\n\nconst phi = (1 + Math.sqrt(5)) / 2\nconsole.log(`黄金比例 φ = ${phi.toFixed(6)}`)\n\nconst ratio = fibonacci(30) / fibonacci(29)\nconsole.log(`F(30)/F(29) = ${ratio.toFixed(6)} ≈ φ`)\n',
        output: 'F(10) = 55\nF(20) = 6765\nF(30) = 832040\n\n黄金比例 φ = 1.618034\nF(30)/F(29) = 1.618034 ≈ φ\n\n结论：随着 n 增大，相邻斐波那契数的比值趋近于黄金比例 φ ≈ 1.618034',
        status: 'completed' as const,
      }},
    ],
  },
  {
    stepType: 'scrape' as const,
    title: '提取论文资料',
    delay: 4100,
    updates: [
      { delay: 500, status: 'completed' as const, data: {
        url: 'https://en.wikipedia.org/wiki/Fibonacci_sequence',
        content: 'The Fibonacci sequence is named after Italian mathematician Leonardo of Pisa (Fibonacci). The sequence first appeared in Indian mathematics in connection with Sanskrit prosody. In the West, the sequence was studied by Fibonacci in his 1202 book Liber Abaci, where he considered the growth of an idealized rabbit population. Applications include computer algorithms (Fibonacci search technique, Fibonacci heap), financial markets (Fibonacci retracement), and natural phenomena (phyllotaxis, arrangement of sunflower seeds, spiral galaxies). The sequence is closely related to the golden ratio φ = (1+√5)/2 ≈ 1.618, as the ratio of consecutive Fibonacci numbers converges to φ. The Binet formula provides a closed-form expression: F(n) = (φ^n - ψ^n) / √5 where ψ = (1-√5)/2.',
      }},
    ],
  },
  {
    stepType: 'result' as const,
    title: '任务执行报告',
    delay: 4700,
    updates: [
      { delay: 100, status: 'running' as const, data: { content: '' } },
      { delay: 600, status: 'completed' as const, data: { content: `## 斐波那契数列跨学科分析报告

### 一、数学原理

斐波那契数列由 **递推公式** 定义：

$$F(n) = F(n-1) + F(n-2), \\quad F(0)=0, F(1)=1$$

前 10 项：0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55...

**Binet 公式**（封闭形式）：

$$F(n) = \\frac{\\varphi^n - \\psi^n}{\\sqrt{5}}$$

其中 $\\varphi = \\frac{1+\\sqrt{5}}{2} \\approx 1.618034$（黄金比例），$\\psi = \\frac{1-\\sqrt{5}}{2} \\approx -0.618034$

### 二、自然界应用

| 领域 | 现象 | 斐波那契数 |
|------|------|------------|
| 植物学 | 向日葵种子排列 | 34, 55, 89 |
| 植物学 | 松果鳞片螺旋 | 8, 13 |
| 植物学 | 叶序（phyllotaxis） | 1/2, 1/3, 2/5, 3/8... |
| 动物学 | 蜜蜂家谱 | 1, 1, 2, 3, 5, 8... |

### 三、黄金比例

> 黄金比例 $\\varphi$ 被称为"神圣比例"，在文艺复兴时期的艺术和建筑中被广泛使用。

相邻斐波那契数的比值趋近于 $\\varphi$：
- $F(10)/F(9) \\approx 1.617647$
- $F(20)/F(19) \\approx 1.618026$
- $F(30)/F(29) \\approx 1.618034$

### 四、算法与计算

\`\`\`javascript
function fibonacci(n) {
  if (n <= 1) return n
  let a = 0, b = 1
  for (let i = 2; i <= n; i++) {
    [a, b] = [b, a + b]
  }
  return b
}
\`\`\`

- **时间复杂度**：O(n)
- **空间复杂度**：O(1)
- 可使用**矩阵快速幂**优化至 O(log n)

### 五、结论

斐波那契数列是数学与自然之间的桥梁，从植物生长模式到金融市场分析，从算法设计到艺术美学，展现了数学的普遍性和优雅性。跨学科视角下，斐波那契数列不仅是数学家的研究对象，更是连接科学与人文的重要纽带。

| 步骤 | 状态 | 关键发现 |
|------|------|----------|
| 需求分析 | ✅ | 识别4个子任务 |
| 资料搜索 | ✅ | Tavily 返回5条结果 |
| 记忆更新 | ✅ | 知识已持久化存储 |
| 代码计算 | ✅ | F(30)=832040, φ≈1.618034 |
| 论文提取 | ✅ | Wikipedia 摘要已提取 |
| 报告汇总 | ✅ | 跨学科分析完成 |
` } },
    ],
  },
]

export function runDemo(
  taskId: number,
  onStep: (step: AgentStep) => void,
  onDone: () => void,
) {
  const stepIdPrefix = `demo_${Date.now()}_`
  let stepIndex = 0
  let subTimer: ReturnType<typeof setTimeout>[] = []

  function processNext() {
    if (stepIndex >= demoStepsRaw.length) {
      onDone()
      return
    }

    const raw = demoStepsRaw[stepIndex]
    const stepId = `${stepIdPrefix}${stepIndex}`

    const step: AgentStep = {
      stepId,
      stepType: raw.stepType,
      status: 'pending',
      title: raw.title,
      data: raw.updates[0]?.data || {},
      expanded: false,
      timestamp: Date.now(),
    }

    raw.updates.forEach((update, ui) => {
      subTimer.push(
        setTimeout(() => {
          const updated: AgentStep = {
            ...step,
            status: update.status,
            data: update.data as AgentStep['data'],
            expanded: update.status === 'running',
            timestamp: Date.now(),
          }
          onStep(updated)
        }, raw.delay + update.delay),
      )
    })

    stepIndex++
    setTimeout(processNext, raw.delay + raw.updates[raw.updates.length - 1].delay + 200)
  }

  processNext()

  onDone()
  return () => subTimer.forEach(clearTimeout)
}
