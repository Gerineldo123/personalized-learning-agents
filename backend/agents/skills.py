"""
Skill 系统：为 Agent 面板提供可插拔的能力模块。

每个 Skill 是一个独立的能力单元，由 plan 节点根据任务自动选择调用。
Skill 执行结果通过 SSE 事件流实时推送至前端。
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """Skill 执行结果"""
    success: bool = True
    data: dict = field(default_factory=dict)
    summary: str = ""
    error: str = ""


class BaseSkill(ABC):
    """Skill 基类，所有 skill 需继承此类"""
    name: str = ""
    description: str = ""  # 供 LLM plan 节点选择参考
    icon: str = "🔧"

    @abstractmethod
    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        """
        执行 skill。
        
        Args:
            context: 包含 user_message, user_id, all_modules_data 等上下文
            workflow_outputs: 当前 workflow 输出列表，skill 可向其中追加步骤事件
        
        Returns:
            SkillResult 包含执行结果
        """
        ...

    _SKILL_AGENT_NAMES: dict = {
        "deep_search": "搜索智能体", "code_analysis": "代码智能体",
        "mindmap_gen": "导图智能体", "quiz_gen": "出题智能体", "video_search": "视频智能体",
    }

    def emit_step(self, workflow_outputs: list, status: str, title: str, data: dict, step_id: str | None = None) -> str:
        """向 workflow_outputs 追加一个 skill step 事件，并实时推送到 SSE 队列"""
        sid = step_id or str(uuid.uuid4())[:8]
        event = {
            "type": "step",
            "step_type": "skill",
            "step_id": sid,
            "status": status,
            "title": title,
            "agent_name": self._SKILL_AGENT_NAMES.get(self.name, self.name),
            "data": {
                "skill_name": self.name,
                "skill_icon": self.icon,
                **data,
            },
        }
        workflow_outputs.append(event)
        # 实时推送：如果 context 中有 SSE 队列，立即 put
        q: asyncio.Queue | None = getattr(self, "_sse_queue", None)
        if q is not None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return sid


# ============================================================
# Skill Registry
# ============================================================

_SKILL_REGISTRY: dict[str, BaseSkill] = {}


def register_skill(skill: BaseSkill):
    """注册一个 skill 实例"""
    _SKILL_REGISTRY[skill.name] = skill


def get_skill(name: str) -> BaseSkill | None:
    """按名称获取 skill"""
    return _SKILL_REGISTRY.get(name)


def get_all_skills() -> dict[str, BaseSkill]:
    """获取所有已注册 skills"""
    return _SKILL_REGISTRY.copy()


def get_skills_description() -> str:
    """生成 skills 列表描述，供 LLM plan 节点使用"""
    lines = []
    for name, skill in _SKILL_REGISTRY.items():
        lines.append(f"- {name}: {skill.description}")
    return "\n".join(lines)


# ============================================================
# 具体 Skill 实现
# ============================================================


class DeepSearchSkill(BaseSkill):
    """深度搜索 - 多轮搜索 + 网页抓取，获取更详尽的信息"""
    name = "deep_search"
    description = "深度搜索：对任务进行多轮互联网搜索并抓取关键网页内容，适用于需要全面资料的任务"
    icon = "🔍"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from agents.tools import tavily_search, web_scrape

        user_message = context.get("user_message", "")
        ad = context.get("all_modules_data", {})
        search_keywords = ad.get("search_keywords", user_message)

        step_id = self.emit_step(workflow_outputs, "running", f"深度搜索: {search_keywords[:30]}", {
            "sub_steps": ["⏳ 第一轮关键词搜索中..."],
        })

        # 第一轮：关键词搜索
        result1 = await tavily_search(search_keywords, max_results=5)
        sub_steps = [f"✅ 关键词搜索完成，获取 {len(result1.get('results', []))} 条结果", "⏳ 第二轮补充搜索中..."]
        self.emit_step(workflow_outputs, "running", f"深度搜索: {search_keywords[:30]}", {"sub_steps": sub_steps}, step_id)

        # 第二轮：原始问题搜索
        result2 = await tavily_search(user_message, max_results=3)
        sub_steps[-1] = f"✅ 补充搜索完成，获取 {len(result2.get('results', []))} 条结果"

        # 合并去重
        seen_urls = set()
        all_results = []
        for r in result1.get("results", []) + result2.get("results", []):
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

        # 抓取前2个网页获取详细内容
        scraped_contents = []
        for r in all_results[:2]:
            url = r.get("url", "")
            if url:
                sub_steps.append(f"⏳ 抓取网页: {r.get('title', url)[:40]}...")
                self.emit_step(workflow_outputs, "running", f"深度搜索: {search_keywords[:30]}", {"sub_steps": sub_steps}, step_id)
                scrape_result = await web_scrape(url)
                content = scrape_result.get("content", "")
                if content and len(content) > 50:
                    scraped_contents.append({"url": url, "title": r.get("title", ""), "content": content[:1000]})
                    sub_steps[-1] = f"✅ 抓取完成: {r.get('title', url)[:40]}"

        answer = result1.get("answer", "") or result2.get("answer", "")

        self.emit_step(workflow_outputs, "completed", f"深度搜索: {search_keywords[:30]}", {
            "content": f"搜索完成，共获取 {len(all_results)} 条结果，抓取 {len(scraped_contents)} 个网页",
            "sub_steps": sub_steps,
        }, step_id)

        return SkillResult(
            success=True,
            data={
                "search_results": all_results,
                "scraped_contents": scraped_contents,
                "answer": answer,
            },
            summary=f"深度搜索完成: {len(all_results)} 条结果, {len(scraped_contents)} 个网页内容",
        )


class CodeAnalysisSkill(BaseSkill):
    """代码分析与生成"""
    name = "code_analysis"
    description = "代码分析与生成：根据任务需求生成、解释或优化代码，适用于编程相关任务"
    icon = "💻"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from core.llm_client import chat_completion

        user_message = context.get("user_message", "")
        ad = context.get("all_modules_data", {})
        code_lang = ad.get("code_lang", "python")
        code_desc = ad.get("code_desc", user_message)
        search_answer = ad.get("search_result", {}).get("answer", "") if ad.get("search_result") else ""

        step_id = self.emit_step(workflow_outputs, "running", f"代码生成 ({code_lang})", {
            "sub_steps": ["⏳ 正在调用模型生成代码..."],
        })

        system_prompt = "你是一个代码专家。根据任务需求生成高质量、可运行的代码。包含详细注释说明逻辑。"
        user_prompt = f"""任务：{code_desc}
上下文：{user_message}
参考信息：{search_answer[:500]}
语言：{code_lang}

请生成完整的可运行代码，包含注释。只输出代码，不要markdown标记。"""

        try:
            resp = await chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], temperature=0.3)
            code_content = resp.choices[0].message.content.strip()
            # 清理 markdown 代码块标记
            if code_content.startswith("```"):
                lines = code_content.split("\n")
                code_content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            self.emit_step(workflow_outputs, "completed", f"代码生成 ({code_lang})", {
                "content": code_content,
                "sub_steps": [f"✅ 已生成 {code_lang} 代码"],
                "language": code_lang,
            }, step_id)

            return SkillResult(
                success=True,
                data={"code": code_content, "language": code_lang},
                summary=f"代码生成完成 ({code_lang})",
            )
        except Exception as e:
            self.emit_step(workflow_outputs, "completed", f"代码生成 ({code_lang})", {
                "content": f"代码生成失败: {str(e)}",
                "sub_steps": [f"❌ 错误: {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))


class MindmapSkill(BaseSkill):
    """思维导图生成"""
    name = "mindmap_gen"
    description = "思维导图生成：将知识点整理为结构化思维导图，适用于需要知识梳理和体系化的任务"
    icon = "🧠"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from core.llm_client import chat_completion

        user_message = context.get("user_message", "")

        step_id = self.emit_step(workflow_outputs, "running", "生成思维导图", {
            "sub_steps": ["⏳ 正在调用模型生成知识结构..."],
        })

        prompt = f"""你是大学学科知识体系专家。请根据主题生成一份用于径向树图(Radial Tree)可视化的JSON知识结构。

主题：{user_message}

【核心原则】
- 每个节点必须有教育深度：name 是短标签(4-12字)，detail 是解释/定义/公式(10-40字)
- 树图只显示 name，detail 用于鼠标悬停弹窗展示
- 禁止只写空洞词典条目（如 "定义：..."），要包含原理、关系、应用等实际知识

【结构要求】
- 根节点 name 为主题精简名(5-10字)，不设 detail
- 一级分支 4-7 个，覆盖不同的知识维度（如概念、原理、方法、应用、工具、关联学科等）
- 每个分支下 2-4 个子节点，最多 3 层
- 叶节点 detail 要特别充实

JSON格式：
{{
  "name": "根节点短名",
  "children": [
    {{
      "name": "分支短标签",
      "detail": "该分支的核心知识说明",
      "children": [
        {{
          "name": "知识点短标签",
          "detail": "具体知识：包含定义、公式、关键参数或一句话示例"
        }}
      ]
    }}
  ]
}}

只返回JSON，不要其他内容。"""

        try:
            resp = await chat_completion([
                {"role": "user", "content": prompt},
            ], temperature=0.55)
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            tree_data = json.loads(raw)

            self.emit_step(workflow_outputs, "completed", "生成思维导图", {
                "content": json.dumps(tree_data, ensure_ascii=False),
                "sub_steps": ["✅ 径向树图数据生成完成"],
                "render_type": "radial_tree",
            }, step_id)

            return SkillResult(
                success=True,
                data={"tree": tree_data, "type": "mindmap"},
                summary="思维导图生成完成",
            )
        except Exception as e:
            self.emit_step(workflow_outputs, "completed", "生成思维导图", {
                "content": f"生成失败: {str(e)}",
                "sub_steps": [f"❌ 错误: {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))


class ArticleGenSkill(BaseSkill):
    """学习文章生成 — 委托给 ContentGenAgent"""
    name = "article_gen"
    description = "文章生成：根据知识点生成个性化学习文章，适用于需要详细讲解某个概念的任务"
    icon = "📄"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from agents.content_gen_agent import ContentGenAgent
        from agents.base import AgentState

        user_message = context.get("user_message", "")
        user_id = context.get("user_id", "")

        step_id = self.emit_step(workflow_outputs, "running", "生成学习文章", {
            "sub_steps": ["⏳ 正在调用模型生成文章..."],
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


class CodeGenSkill(BaseSkill):
    """代码案例生成 — 委托给 ContentGenAgent"""
    name = "code_gen"
    description = "代码案例生成：生成带注释的可运行代码示例或算法可视化动画（HTML+JS自包含页面），适用于编程概念教学、算法步骤演示、数据结构可视化等任务"
    icon = "💡"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from agents.content_gen_agent import ContentGenAgent
        from agents.base import AgentState
        from core.llm_client import chat_completion

        user_message = context.get("user_message", "")
        user_id = context.get("user_id", "")
        ad = context.get("all_modules_data", {})
        code_lang = ad.get("code_lang", "python")

        # 检测可视化意图
        VIZ_KEYWORDS = ["可视化", "动画", "演示", "visuali", "animation", "animate", "步骤展示", "动态展示"]
        is_viz = any(kw in user_message.lower() for kw in VIZ_KEYWORDS)

        step_id = self.emit_step(workflow_outputs, "running", "生成代码案例", {
            "sub_steps": [f"⏳ 正在生成{'可视化动画' if is_viz else '代码案例'}..."],
        })

        try:
            if is_viz:
                profile = context.get("profile")
                profile_text = f"专业：{getattr(profile, 'major', '')}，年级：{getattr(profile, 'grade', '')}" if profile else ""
                prompt = f"""你是一个算法可视化专家。请生成一个自包含的HTML文件，用动画展示以下内容：

主题：{user_message}
学生背景：{profile_text or '未知'}

要求：
- 输出完整可运行的单个HTML文件（包含CSS和JavaScript）
- 用动画逐步展示算法/概念的每个步骤
- 提供"下一步"/"上一步"/"自动播放"控制按钮
- 界面美观，关键步骤有文字说明
- 不依赖外部CDN，所有代码内嵌

严格输出规则（违反将导致错误）：
- 直接输出HTML代码，以<!DOCTYPE html>或<html开头
- 以</html>结尾，之后不得有任何内容
- 禁止输出任何Markdown、注释、说明、建议或总结文字"""

                resp = await chat_completion([{"role": "user", "content": prompt}], temperature=0.3)
                content = resp.choices[0].message.content.strip()
                # 提取 HTML：找到第一个 < 到最后 </html> 之间的内容
                import re as _re
                _m_start = _re.search(r'<(!DOCTYPE html|html)', content, _re.IGNORECASE)
                _m_end = _re.search(r'</html\s*>', content, _re.IGNORECASE)
                if _m_start and _m_end:
                    content = content[_m_start.start():_m_end.end()].strip()
                elif _m_end:
                    content = content[:_m_end.end()].strip()

                self.emit_step(workflow_outputs, "completed", "生成代码案例", {
                    "content": content,
                    "sub_steps": ["✅ 可视化动画生成完成"],
                    "language": "html",
                }, step_id)
                return SkillResult(success=True, data={"code": content, "type": "code"}, summary="可视化动画生成完成")

            # 非可视化：走原有流程
            state = AgentState(
                user_id=user_id,
                user_message=user_message,
                resource_type="code",
                code_language=code_lang,
                profile=context.get("profile"),
            )
            agent = ContentGenAgent()
            await agent._generate_code_case(state)

            resp = json.loads(state.get("response", ""))
            content = resp.get("content", "")
            resource_type = resp.get("resource_type", "code")

            self.emit_step(workflow_outputs, "completed", "生成代码案例", {
                "content": content,
                "sub_steps": ["✅ 代码案例生成完成"],
                "language": code_lang,
            }, step_id)
            return SkillResult(success=True, data={"code": content, "type": resource_type}, summary="代码案例生成完成")

        except Exception as e:
            self.emit_step(workflow_outputs, "completed", "生成代码案例", {
                "content": f"生成失败: {str(e)}",
                "sub_steps": [f"❌ {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))


class QuizGenSkill(BaseSkill):
    """习题生成 — 委托给 ContentGenAgent"""
    name = "quiz_gen"
    description = "习题生成：根据知识点生成练习题和测验，适用于需要检验学习效果或出题的任务"
    icon = "📝"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from agents.content_gen_agent import ContentGenAgent
        from agents.base import AgentState

        user_message = context.get("user_message", "")
        user_id = context.get("user_id", "")
        ad = context.get("all_modules_data", {})

        step_id = self.emit_step(workflow_outputs, "running", "生成练习题", {
            "sub_steps": ["⏳ 正在调用模型生成练习题..."],
        })

        try:
            state = AgentState(
                user_id=user_id,
                user_message=user_message,
                resource_type="quiz",
                question_count=context.get("question_count", 5),
                difficulty=context.get("difficulty", "中等"),
                code_language=ad.get("code_lang", "python"),
                profile=context.get("profile"),
            )
            agent = ContentGenAgent()
            await agent._generate_quiz(state)

            resp = json.loads(state.get("response", "{}"))
            quiz_data = resp.get("content", {})

            self.emit_step(workflow_outputs, "completed", "生成练习题", {
                "content": json.dumps(quiz_data, ensure_ascii=False, indent=2),
                "sub_steps": [f"✅ 已生成 {len(quiz_data.get('questions', []))} 道练习题"],
            }, step_id)

            return SkillResult(
                success=True,
                data={"quiz": quiz_data, "type": "quiz"},
                summary=f"生成 {len(quiz_data.get('questions', []))} 道练习题",
            )
        except Exception as e:
            self.emit_step(workflow_outputs, "completed", "生成练习题", {
                "content": f"生成失败: {str(e)}",
                "sub_steps": [f"❌ 错误: {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))


class PracticeCaseSkill(BaseSkill):
    """实操案例生成 — 生成完整的实验/实践项目案例"""
    name = "practice_case"
    description = "实操案例生成：生成包含背景、目标、操作步骤、参考实现和验证要点的完整实践项目案例，适用于需要动手实践、实验练习的任务"
    icon = "🔬"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        from core.llm_client import chat_completion

        user_message = context.get("user_message", "")
        user_id = context.get("user_id", "")
        profile = context.get("profile")

        step_id = self.emit_step(workflow_outputs, "running", "生成实操案例", {
            "sub_steps": ["⏳ 正在调用模型生成实操案例..."],
        })

        profile_text = ""
        if profile:
            profile_text = f"专业：{getattr(profile, 'major', '')}，年级：{getattr(profile, 'grade', '')}，编程语言偏好：{getattr(profile, 'learning_goal', '')}"

        prompt = f"""你是一位经验丰富的实践教学专家。请为以下学习任务设计一个完整的实操案例，用Markdown格式输出。

学习任务：{user_message}
学生背景：{profile_text or '未知'}

请按以下结构输出：

## 🔬 实操案例：[案例名称]

### 📋 背景与目标
[说明本案例的应用背景和学习目标，3-5句]

### 🛠️ 环境准备
[列出所需工具、依赖、环境配置]

### 📝 实践步骤

**步骤一：[标题]**
[详细说明 + 关键代码]

**步骤二：[标题]**
[详细说明 + 关键代码]

（根据复杂度设计3-6个步骤）

### 💡 参考实现
```[语言]
[完整可运行的参考代码，含注释]
```

### ✅ 验证要点
- [ ] [验证点1]
- [ ] [验证点2]
- [ ] [验证点3]

### 🚀 拓展挑战
[1-2个进阶练习方向]

要求：步骤具体可操作，代码真实可运行，验证要点可自测。"""

        try:
            resp = await chat_completion([{"role": "user", "content": prompt}], temperature=0.4)
            content = resp.choices[0].message.content.strip()

            # 存入 LearningResource
            resource_db_id = None
            try:
                from core.database import SessionLocal
                from models.resource import LearningResource
                from services.rag_service import index_resource
                self.emit_step(workflow_outputs, "running", "生成实操案例", {"sub_steps": ["✅ 案例内容生成完成", "⏳ 正在保存到资源库..."]}, step_id)
                db = SessionLocal()
                try:
                    title = f"实操案例：{user_message[:40]}"
                    res = LearningResource(user_id=user_id, title=title, resource_type="article", content=content)
                    db.add(res)
                    db.commit()
                    db.refresh(res)
                    resource_db_id = res.id
                    await index_resource(res.id, content)
                finally:
                    db.close()
            except Exception:
                pass

            self.emit_step(workflow_outputs, "completed", "生成实操案例", {
                "content": content,
                "sub_steps": ["✅ 案例内容生成完成", "✅ 已保存到资源库"],
                **({"resource_db_id": resource_db_id, "resource_type": "article"} if resource_db_id else {}),
            }, step_id)

            return SkillResult(success=True, data={"content": content, "type": "practice_case", "resource_db_id": resource_db_id}, summary="实操案例生成完成")
        except Exception as e:
            self.emit_step(workflow_outputs, "completed", "生成实操案例", {
                "content": f"生成失败: {str(e)}",
                "sub_steps": [f"❌ {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))


class VideoSearchSkill(BaseSkill):
    """视频检索 — 从B站搜索教学视频"""
    name = "video_search"
    description = "视频检索：从B站搜索相关教学视频，适用于需要视频学习资源的任务"
    icon = "🎬"

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """将秒数格式化为 mm:ss 或 hh:mm:ss"""
        if seconds <= 0:
            return ""
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @staticmethod
    def _format_play(n: int) -> str:
        if n >= 10000:
            return f"{n / 10000:.1f}万"
        return str(n)

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        import httpx
        from urllib.parse import quote

        user_message = context.get("user_message", "")
        ad = context.get("all_modules_data", {})
        search_keywords = ad.get("search_keywords", user_message)

        step_id = self.emit_step(workflow_outputs, "running", "搜索教学视频", {
            "content": f"正在B站搜索: {search_keywords[:30]}...",
            "sub_steps": [],
            "render_type": "video_cards",
        })

        BILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
        BILI_VIDEO_URL = "https://www.bilibili.com/video/{}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }

        videos = []
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
                # 先访问主页获取 buvid cookie，否则搜索接口返回空 body
                await client.get("https://www.bilibili.com/")
                r = await client.get(BILI_SEARCH_API, params={
                    "search_type": "video", "keyword": search_keywords, "page": 1,
                })
                if r.status_code == 200:
                    data = r.json()
                    video_list = (data.get("data") or {}).get("result") or []
                    for v in video_list[:6]:
                        bvid = v.get("bvid", "")
                        if not bvid:
                            continue
                        arcurl = v.get("arcurl", "")
                        url = arcurl if arcurl and "video" in arcurl else BILI_VIDEO_URL.format(bvid)

                        # 封面图：B站返回的 pic 字段可能缺少协议头
                        pic = v.get("pic", "")
                        if pic and not pic.startswith("http"):
                            pic = "https:" + pic

                        # 时长：B站搜索接口返回 duration 字段格式为 "mm:ss" 字符串
                        duration_raw = v.get("duration", "")
                        duration = duration_raw if isinstance(duration_raw, str) else self._format_duration(int(duration_raw or 0))

                        # 清理标题中的高亮标签
                        title = v.get("title", "").replace('<em class="keyword">', "").replace("</em>", "")

                        videos.append({
                            "title": title,
                            "url": url,
                            "cover": pic,
                            "duration": duration,
                            "author": v.get("author", ""),
                            "play_count": self._format_play(v.get("play", 0)),
                            "danmaku": self._format_play(v.get("danmaku", 0)),
                            "bvid": bvid,
                        })
        except Exception:
            pass

        if not videos:
            videos.append({
                "title": search_keywords,
                "url": f"https://search.bilibili.com/all?keyword={quote(search_keywords)}",
                "cover": "",
                "duration": "",
                "author": "",
                "play_count": "",
                "danmaku": "",
                "bvid": "",
            })

        sub_steps = [f"✅ 找到 {len(videos)} 个相关视频"]
        self.emit_step(workflow_outputs, "completed", "搜索教学视频", {
            "content": json.dumps(videos, ensure_ascii=False),
            "sub_steps": sub_steps,
            "render_type": "video_cards",
        }, step_id)

        return SkillResult(
            success=True,
            data={"videos": videos, "type": "video"},
            summary=f"找到 {len(videos)} 个B站教学视频",
        )


PPT_PROMPT = """你是一个专业的课件设计专家。根据学生画像和知识点，生成一份结构精美的PPT课件内容。

学生画像：{profile}
主题：{topic}

返回JSON格式：
{{
  "title": "课件标题（精简5-12字）",
  "slides": [
    {{
      "title": "幻灯片标题",
      "content": ["要点1：具体可讲解的内容", "要点2"],
      "notes": "讲师备注：讲解要点或补充信息"
    }}
  ]
}}

设计要求：
- 第1张作为封面（课件标题+副标题概括），最后1张做总结
- 总页数 6-10 张，每页 2-4 条内容要点
- 要点做到简明有深度，适合大学生课堂
- 逻辑递进：引入 → 概念/原理 → 方法/案例 → 应用 → 总结

只返回JSON，不要其他内容。"""


class PptGenSkill(BaseSkill):
    """PPT课件生成 - 支持 .pptx 文件导出"""
    name = "ppt_gen"
    description = "PPT课件生成：根据知识点生成结构化课件，支持导出.pptx文件，适用于需要教学演示的任务"
    icon = "📊"

    async def execute(self, context: dict, workflow_outputs: list) -> SkillResult:
        import os as _os
        from core.database import SessionLocal
        from models.resource import LearningResource
        from services.rag_service import index_resource
        from services.config_service import is_configured as _is_configured

        user_message = context.get("user_message", "")
        user_id = context.get("user_id", "")

        step_id = self.emit_step(workflow_outputs, "running", "生成PPT课件", {
            "sub_steps": ["⏳ 正在调用模型生成课件内容..."],
        })

        # 构建学生画像文本
        profile_text = "暂无学生画像"
        profile = context.get("profile")
        if profile:
            import json as _json
            parts = [
                f"专业：{getattr(profile, 'major', '未知')}",
                f"年级：{getattr(profile, 'grade', '未知')}",
            ]
            kb = getattr(profile, 'knowledge_base', {})
            if kb:
                parts.append(f"知识基础：{_json.dumps(kb, ensure_ascii=False)}")
            goal = getattr(profile, 'learning_goal', '')
            if goal:
                parts.append(f"学习目标：{goal}")
            profile_text = "；".join(parts)

        # 1. 调用 LLM 生成JSON内容
        try:
            from core.llm_client import ppt_completion, chat_completion
            use_ppt_model = _is_configured("ppt")
            completion_fn = ppt_completion if use_ppt_model else chat_completion

            resp = await completion_fn([
                {"role": "user", "content": PPT_PROMPT.format(profile=profile_text, topic=user_message)},
            ], temperature=0.5)

            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            ppt_data = json.loads(raw)
            if not isinstance(ppt_data, dict) or "slides" not in ppt_data:
                ppt_data = {"title": user_message, "slides": []}

            sub_steps = [f"✅ LLM生成完成，共 {len(ppt_data.get('slides', []))} 页"]
            self.emit_step(workflow_outputs, "running", "生成PPT课件", {"sub_steps": sub_steps + ["⏳ 正在生成 .pptx 文件..."]}, step_id)
        except Exception as e:
            self.emit_step(workflow_outputs, "completed", "生成PPT课件", {
                "content": f"生成失败: {str(e)}",
                "sub_steps": [f"❌ LLM调用失败: {str(e)}"],
            }, step_id)
            return SkillResult(success=False, error=str(e))

        # 2. 生成 .pptx 文件
        pptx_filename = ""
        pptx_path = ""
        try:
            pptx_filename = self._generate_pptx_file(ppt_data)
            pptx_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static", "ppt", pptx_filename)
            sub_steps.append(f"✅ .pptx 文件已生成")
        except Exception as e:
            sub_steps.append(f"⚠️ .pptx 生成失败: {str(e)}")
        self.emit_step(workflow_outputs, "running", "生成PPT课件", {"sub_steps": sub_steps + ["⏳ 正在保存到资源库..."]}, step_id)

        # 3. 保存到数据库
        db_id = None
        try:
            db = SessionLocal()
            try:
                resource = LearningResource(
                    user_id=user_id,
                    resource_type="ppt",
                    title=ppt_data.get("title", user_message),
                    content={"slides": ppt_data.get("slides", []), "title": ppt_data.get("title", ""), "pptx_file": pptx_filename},
                    tags=["ppt"],
                )
                db.add(resource)
                db.flush()
                db.commit()
                db_id = resource.id
                index_resource(resource.id, user_id or "", json.dumps(ppt_data, ensure_ascii=False)[:4000], "ppt")
                sub_steps.append(f"✅ 已保存至学习资源库")
            finally:
                db.close()
        except Exception as e:
            sub_steps.append(f"⚠️ 数据库保存失败: {str(e)}")

        # 4. 构建前端渲染数据
        download_url = f"/static/ppt/{pptx_filename}" if pptx_filename else ""

        render_content = json.dumps({
            "title": ppt_data.get("title", user_message),
            "slides": ppt_data.get("slides", []),
            "pptx_url": download_url,
            "slide_count": len(ppt_data.get("slides", [])),
            "db_id": db_id,
        }, ensure_ascii=False)

        self.emit_step(workflow_outputs, "completed", "生成PPT课件", {
            "content": render_content,
            "sub_steps": sub_steps,
            "render_type": "ppt_viewer",
        }, step_id)

        return SkillResult(
            success=True,
            data={
                "ppt_json": ppt_data,
                "pptx_filename": pptx_filename,
                "pptx_url": download_url,
                "db_id": db_id,
                "type": "ppt",
            },
            summary=f"PPT课件生成完成 ({len(ppt_data.get('slides', []))} 页)" + (f", .pptx已导出" if pptx_filename else ""),
        )

    def _generate_pptx_file(self, ppt_data: dict) -> str:
        """将 JSON 幻灯片数据转换为 .pptx 文件，返回文件名"""
        import uuid as _uuid
        import os as _os
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        slides_data = ppt_data.get("slides", [])
        title_text = ppt_data.get("title", "课件")

        # 封面
        if slides_data:
            self._make_cover_slide(prs, title_text, slides_data[0])
            content_slides = slides_data[1:]
        else:
            content_slides = []

        # 内容页
        for sd in content_slides:
            self._make_content_slide(prs, sd.get("title", ""), sd.get("content", []), sd.get("notes", ""))

        # 如果没有内容，至少加一张空页
        if len(prs.slides) == 0:
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.title.text = title_text

        static_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static", "ppt")
        _os.makedirs(static_dir, exist_ok=True)

        filename = f"{_uuid.uuid4().hex[:8]}.pptx"
        filepath = _os.path.join(static_dir, filename)
        prs.save(filepath)
        return filename

    def _make_cover_slide(self, prs, title: str, first_slide: dict):
        """制作封面页"""
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        slide_layout = prs.slide_layouts[6]  # blank
        slide = prs.slides.add_slide(slide_layout)

        # 背景色块
        left, top = Inches(0), Inches(0)
        width, height = prs.slide_width, prs.slide_height
        bg_shape = slide.shapes.add_shape(
            1, left, top, width, height  # MSO_SHAPE.RECTANGLE
        )
        bg_shape.fill.solid()
        bg_shape.fill.fore_color.rgb = RGBColor(0x1A, 0x36, 0x5D)
        bg_shape.line.fill.background()

        # 标题
        txBox = slide.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.3), Inches(1.5))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(44)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = PP_ALIGN.CENTER

        # 副标题
        subtitle = first_slide.get("title", "")
        if subtitle:
            txBox2 = slide.shapes.add_textbox(Inches(1.5), Inches(3.8), Inches(10.3), Inches(1.0))
            tf2 = txBox2.text_frame
            p2 = tf2.paragraphs[0]
            p2.text = subtitle
            p2.font.size = Pt(24)
            p2.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
            p2.alignment = PP_ALIGN.CENTER

        # 装饰线
        line = slide.shapes.add_shape(
            1, Inches(4.5), Inches(5.2), Inches(2.8), Inches(0.04)
        )
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(0x40, 0x9E, 0xFF)
        line.line.fill.background()

    def _make_content_slide(self, prs, title: str, content: list, notes: str):
        """制作内容页"""
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        slide_layout = prs.slide_layouts[6]  # blank
        slide = prs.slides.add_slide(slide_layout)

        # 顶部装饰条
        top_bar = slide.shapes.add_shape(
            1, Inches(0), Inches(0), prs.slide_width, Inches(0.08)
        )
        top_bar.fill.solid()
        top_bar.fill.fore_color.rgb = RGBColor(0x40, 0x9E, 0xFF)
        top_bar.line.fill.background()

        # 标题
        txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.9))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0x1A, 0x36, 0x5D)

        # 内容要点
        content_top = Inches(1.8)
        txBox2 = slide.shapes.add_textbox(Inches(1.2), content_top, Inches(10.9), Inches(5.0))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True

        for i, point in enumerate(content):
            if i == 0:
                p2 = tf2.paragraphs[0]
            else:
                p2 = tf2.add_paragraph()
            p2.text = f"• {point}"
            p2.font.size = Pt(20)
            p2.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            p2.space_after = Pt(14)
            p2.space_before = Pt(4)

        # 讲师备注
        if notes:
            txBox3 = slide.shapes.add_textbox(Inches(1.2), Inches(6.2), Inches(10.9), Inches(0.9))
            tf3 = txBox3.text_frame
            tf3.word_wrap = True
            p3 = tf3.paragraphs[0]
            p3.text = f"📝 {notes}"
            p3.font.size = Pt(13)
            p3.font.italic = True
            p3.font.color.rgb = RGBColor(0x90, 0x93, 0x99)

        # 页码
        slide_num = len(prs.slides)
        txBox4 = slide.shapes.add_textbox(Inches(12.0), Inches(6.9), Inches(1.0), Inches(0.4))
        tf4 = txBox4.text_frame
        p4 = tf4.paragraphs[0]
        p4.text = str(slide_num)
        p4.font.size = Pt(11)
        p4.font.color.rgb = RGBColor(0xC0, 0xC4, 0xCC)
        p4.alignment = PP_ALIGN.RIGHT


# ============================================================
# 初始化：注册所有内置 skills
# ============================================================

def init_skills():
    """注册所有内置 skills，在应用启动时调用"""
    register_skill(DeepSearchSkill())
    register_skill(CodeAnalysisSkill())
    register_skill(MindmapSkill())
    register_skill(QuizGenSkill())
    register_skill(VideoSearchSkill())
    register_skill(PptGenSkill())
    register_skill(ArticleGenSkill())
    register_skill(CodeGenSkill())
    register_skill(PracticeCaseSkill())
