# 第三方依赖与 AI 工具说明

> 本说明用于软件杯提交材料与系统内展示。协议与版本需在最终提交前由团队再次人工复核；本文不是法律意见。

## 前端开源依赖

| 名称 | 来源 | 协议 | 项目用途 |
| --- | --- | --- | --- |
| Vue | https://github.com/vuejs/core | MIT | 前端应用框架 |
| Vue Router | https://github.com/vuejs/router | MIT | 前端路由 |
| Pinia | https://github.com/vuejs/pinia | MIT | 前端状态管理 |
| Vite | https://github.com/vitejs/vite | MIT | 前端构建工具 |
| Element Plus | https://github.com/element-plus/element-plus | MIT | UI 组件库 |
| Axios | https://github.com/axios/axios | MIT | HTTP 请求 |
| ECharts | https://github.com/apache/echarts | Apache-2.0 | 图表与可视化 |
| KaTeX | https://github.com/KaTeX/KaTeX | MIT | 数学公式渲染 |
| markdown-it | https://github.com/markdown-it/markdown-it | MIT | Markdown 渲染 |
| markmap | https://github.com/markmap/markmap | MIT | 思维导图展示 |

## 后端开源依赖

| 名称 | 来源 | 协议 | 项目用途 |
| --- | --- | --- | --- |
| FastAPI | https://github.com/fastapi/fastapi | MIT | 后端 Web API 框架 |
| Starlette | https://github.com/encode/starlette | BSD-3-Clause | ASGI 基础框架 |
| Uvicorn | https://github.com/encode/uvicorn | BSD-3-Clause | ASGI 服务 |
| SQLAlchemy | https://github.com/sqlalchemy/sqlalchemy | MIT | ORM 与数据库访问 |
| Pydantic | https://github.com/pydantic/pydantic | MIT | 数据校验 |
| ChromaDB | https://github.com/chroma-core/chroma | Apache-2.0 | 向量检索与 RAG 存储 |
| LangGraph | https://github.com/langchain-ai/langgraph | MIT | 多智能体图式编排 |
| OpenAI Python SDK | https://github.com/openai/openai-python | Apache-2.0 | 大模型 API 调用 |
| sentence-transformers | https://github.com/UKPLab/sentence-transformers | Apache-2.0 | 文本向量化 |
| python-pptx | https://github.com/scanny/python-pptx | MIT | PPTX 文件处理 |
| Pillow | https://github.com/python-pillow/Pillow | HPND | 图片处理与 PPT 低保真预览 |
| Playwright | https://github.com/microsoft/playwright-python | Apache-2.0 | 网页抓取与自动化辅助 |

## AI 工具与外部服务

| 名称 | 来源 | 协议/服务条款 | 项目用途 |
| --- | --- | --- | --- |
| OpenAI 兼容大模型 API | 由用户在系统中配置 | 以实际服务商条款为准 | 对话、资源生成、画像分析、学习路径规划 |
| Docmee / veasion AiPPT | https://github.com/veasion/aippt | 以仓库协议与 Docmee 服务条款为准 | 分步生成 PPT 课件 |
| Tavily Search API | https://tavily.com | 以 Tavily 服务条款为准 | 联网搜索辅助 |
| Bilibili 视频链接 | https://www.bilibili.com | 以 Bilibili 服务条款为准 | 教学视频推荐与跳转 |

## 使用说明

- 若提交材料引用本项目功能截图，应同时保留本说明或等价的第三方依赖说明。
- 若新增依赖、模型服务或外部 API，应同步补充名称、来源、协议和用途。
- 若实际部署中替换了模型供应商，应在提交材料中写明最终使用的供应商及条款来源。
