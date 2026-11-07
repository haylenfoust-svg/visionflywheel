# ADR-001: 技术栈选择（FastAPI + Vue3 + ultralytics YOLO + LangGraph）

- **状态**：已采纳
- **日期**：2026-11-07
- **关联**：`PRD.md` §2、§3；`ARCHITECTURE.md` §1

## 背景

视觉飞轮需要一条从识别到训练的完整闭环，涉及五类能力：

1. **目标检测**：快速、可增量训练、生态成熟
2. **Web 后端**：能挂模型、能做异步任务、能给前端稳定 API
3. **Web 前端**：复杂 Canvas 标注交互、表格、表单
4. **智能问答**：基于识别统计的对话式分析
5. **检索增强**：知识库沉淀与复用

候选方案对比：

| 能力 | 候选 A | 候选 B | 候选 C |
|---|---|---|---|
| 目标检测 | ultralytics YOLO | MMDetection | DETR / RT-DETR |
| 后端 | FastAPI | Django REST | Flask |
| 前端 | Vue3 + Element Plus | React + AntD | 原生 + jQuery |
| 智能体 | LangChain + LangGraph | LlamaIndex | 自研链式调用 |
| 检索 | Chroma / FAISS / 哈希兜底 | Pinecone | Elasticsearch + 向量插件 |

## 决策

| 能力 | 选型 | 关键理由 |
|---|---|---|
| 目标检测 | **ultralytics YOLO** | 一行 CLI 训练/推理；导出标准 `data.yaml`；从 v5→v8→11→26 API 兼容；社区资料最多 |
| 后端 | **FastAPI + SQLAlchemy + JWT** | 原生 OpenAPI 文档、异步 IO、Pydantic 校验、依赖注入天然契合分层架构 |
| 前端 | **Vue3 + Element Plus + Vite + Pinia** | 组合式 API 利于复杂标注交互；Element Plus 表格/表单成熟；中文文档全 |
| 智能体 | **LangChain + LangGraph** | LangGraph 支持反思节点、状态机、可中断流；契合 PRD FR-8 反思约束幻觉需求 |
| 检索 | **哈希向量兜底 + 可插 Chroma/FAISS** | 0-to-1 阶段避免重依赖；接口抽象后可替换 |
| 数据库 | **SQLite（起步）→ PostgreSQL（后期）** | 单实例私有化部署，SQLite 起步足够；SQLAlchemy 抽象使迁移成本低 |
| 部署 | **Docker Compose** | 一条命令起前后端，符合 NFR-15 |

## 后果

### 正面
- ultralytics 训练导出标准，符合 FR-5.2 "导出即可训"
- FastAPI 自动生成 OpenAPI，契约先行成本低
- LangGraph 的反思节点直接对应 NFR-9 / R-09 幻觉约束
- 单仓 + Compose，新用户 5 分钟跑通（项目 DoD）

### 负面 / 权衡
- ultralytics 是重依赖，CPU 环境慢 → 由 ADR-002 降级策略兜底
- SQLite 并发写弱（R-06）→ WAL 模式 + 事务粒度控制，必要时迁 PG
- LangChain 版本迭代快，API 不稳 → 锁版本 + 抽象 `llm_service` 接口
- Element Plus 定制性弱于原生 → 关键交互（Canvas 标注）自研组件

## 备选方案与放弃理由

- **MMDetection**：精度上限更高，但训练/部署复杂度陡峭，与"5 分钟跑通"目标冲突
- **Django REST**：内置 admin 省事，但同步框架不适合模型推理任务，Pydantic 生态不如 FastAPI
- **React + AntD**：能力相当，但团队/文档中文生态 Vue 更顺，组合式 API 对 Canvas 交互更直接
- **LlamaIndex**：RAG 强，但反思节点/状态机弱于 LangGraph

## 参考
- ultralytics 文档：https://docs.ultralytics.com
- FastAPI 文档：https://fastapi.tiangolo.com
- LangGraph 文档：https://langchain-ai.github.io/langgraph
