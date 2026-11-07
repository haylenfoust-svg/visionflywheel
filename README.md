# 视觉飞轮 VisionFlywheel

> 以 YOLO 为核心、人工校正为飞轮动力的**自进化图像识别闭环系统**。
>
> **上传即识别 · 识别即可视化 · 看得不对就改 · 改完即训练 · 切换即生效。**

---

## 🚀 60 秒体验

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m app.seed && python -m uvicorn app.main:app --port 8000

# 前端
cd frontend && npm install && npm run dev
# 打开 http://localhost:5173 · admin / admin123
```

或一条命令：

```bash
docker compose up --build    # 前端 8080 · 后端 8000
```

---

## 📖 目录

- [这是什么](#这是什么)
- [核心能力](#核心能力)
- [架构](#架构)
- [快速开始](#快速开始)
- [API 概览](#api-概览)
- [数据与合规](#数据与合规)
- [部署](#部署)
- [开发指南](#开发指南)

---

## 这是什么

很多视觉方案停在"画完框"这一步。**视觉飞轮**打通了从识别到再训练的完整闭环：

```
① 上传图片/视频
      ↓
② YOLO 推理（权重、阈值全部可配）
      ↓
③ 结果落库 + 可视化（检测框、置信度、中文类别）
      ↓
④ 人工校正：确认 / 改标签 / 标记误检 / 拖拽改框 / 空白处补框
      ↓
⑤ 校正流水审计 + 反馈工单
      ↓
⑥ 一键导出标准 YOLO 训练集（images / labels / data.yaml）
      ↓
⑦ 增量训练生成 best.pt → 放回 weights/ → 页面切换权重 → 回到 ②
```

**适用场景**：工业质检、仓储分拣、果蔬/零件盘点、巡检取证、现场照片数字化。

---

## 核心能力

### 🎯 识别与校正
- ✅ 上传识别（单图 / 批量 / 视频抽帧），YOLO 权重与阈值可配
- ✅ Canvas 标注工作台：五种校正动作 + 拖拽改框/补框 + 撤销
- ✅ 中英标签映射（`dog` → 「狗」），可配置
- ✅ 校正流水**只追加不修改**（审计可追溯）

### 📊 数据与训练
- ✅ 一键导出标准 YOLO 训练集（`data.yaml` + `images/{train,val}` + `labels/{train,val}`）
- ✅ **holdout 评估集冻结**：永不参与训练，用作 mAP 基线
- ✅ **权重热切换**：切换默认权重立即生效，`requires_restart=false`
- ✅ **回归门禁**：新权重上任前 holdout 指标对比，回归即拦截

### 🧠 智能分析
- ✅ 基于真实识别统计的问答（"今天识别了多少 defect？"）
- ✅ 知识库沉淀 + 检索增强
- ✅ 反思自检（答案里的数字都对照统计）
- ✅ RAG 内容安全过滤（PII / 敏感词）

### 🔒 B 端商用
- ✅ JWT + 角色权限（admin / operator / viewer）
- ✅ **细粒度权限**：36 权限码 × 14 分类，`require_permission(...)` 装饰器
- ✅ **org/team 数据隔离**：跨组织可见性隔离
- ✅ **API Key**：机器对机器凭证（生成/吊销/权限范围/调用记录）
- ✅ **2FA TOTP**：可选两步验证
- ✅ **SSO OAuth**：Google / GitHub / SAML（接 client_id/secret 即启用）
- ✅ **密码重置**：邮件 + token
- ✅ **邮件服务**：SMTP 可配置，测试模式写 outbox

### 📈 可观测与质量
- ✅ 结构化 JSON 日志 + 健康检查 + 告警通道（邮件 + Webhook）
- ✅ **模型漂移监控**：置信度/类别/校正率漂移检测 + 报警
- ✅ **漂移→行动闭环**：告警 + 回滚建议 + 可选重训
- ✅ **训练指标**：mAP / precision / recall / loss 曲线
- ✅ **异步推理队列**：进度推送 + 取消

### 🛡 合规
- ✅ PII 处理声明（隐私政策）
- ✅ **数据删除权**：级联清除账号所有数据
- ✅ **审计日志导出**：CSV / JSON
- ✅ RAG 内容安全过滤

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  接入层  api/   FastAPI routers (鉴权 · 校验 · 序列化)  │
├─────────────────────────────────────────────────────────┤
│  业务层  services/  业务核心（不依赖 FastAPI）           │
│    ├─ yolo / fallback detector    ├─ correction_service  │
│    ├─ dataset_exporter            ├─ weight_manager      │
│    ├─ weight_gate (回归门禁)      ├─ train_service       │
│    ├─ inference_queue (异步)      ├─ drift_service       │
│    ├─ drift_action_service        ├─ llm_service (RAG)   │
│    ├─ permission_service          ├─ scope_service       │
│    ├─ compliance_service          ├─ observability       │
│    └─ email / oauth / api_key / metrics / quality        │
├─────────────────────────────────────────────────────────┤
│  数据层  models/ + SQLAlchemy (10+ 表)                  │
├─────────────────────────────────────────────────────────┤
│  横切   core/  config·security·deps·envelope·exceptions  │
└─────────────────────────────────────────────────────────┘
```

**前端**：Vue3 + Element Plus + Pinia + Vite + TypeScript
**检测**：ultralytics YOLO（可选）+ 内置降级检测器（无 GPU 可跑闭环）
**数据库**：SQLite（起步）→ PostgreSQL（后期）

详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## 快速开始

### 环境要求
- Python **3.10+**（推荐 3.12）
- Node.js **18+**（推荐 20/22）
- （可选）CUDA GPU

### 1. 后端

```bash
cd backend
python -m venv ../.venv
source ../.venv/bin/activate      # Windows: ../.venv/Scripts/activate
pip install -r requirements.txt
python -m app.seed                 # 建初始管理员 admin / admin123
python -m uvicorn app.main:app --port 8000 --reload
```

打开 <http://127.0.0.1:8000/docs> 查看自动 OpenAPI。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5173>，用 `admin / admin123` 登录。

> ⚠️ 默认密码仅用于开发，**生产部署前务必改掉**。

### 3. （可选）真 YOLO

```bash
cd backend
pip install -r requirements-ml.txt       # ultralytics + torch (~2 GB)
# 下载 yolov8n.pt 放到 backend/weights/
```

重启后自动识别并切换到 YOLO 推理。

### 4. （可选）Docker

```bash
docker compose up --build
# 前端 http://localhost:8080 · 后端 http://localhost:8000
```

---

## API 概览

| 模块 | 端点 | 权限 |
|---|---|---|
| **认证** | `POST /api/auth/login` · `POST /api/auth/refresh` · `POST /api/auth/logout` | 公开 |
| **2FA** | `POST /api/auth/2fa/setup` · `confirm` · `disable` | 登录用户 |
| **密码重置** | `POST /api/auth/password-reset/request` · `confirm` | 公开 |
| **SSO** | `GET /api/auth/oauth/{google\|github\|saml}/authorize` · `callback` | 公开 |
| **API Key** | `POST /api/api-keys` · `GET /api/api-keys` · `revoke` · `verify` | `system.admin` |
| **识别** | `POST /api/tasks/upload` · `batch` · `video` · `GET /api/tasks` | `task.write/read` |
| **检测** | `GET /api/detections/*` · `stats` | `detection.read` |
| **校正** | `POST /api/corrections` · `batch` · `undo` · `GET /api/corrections/audit` | `detection.correct` |
| **工单** | `POST /api/feedback` · `GET` · `reply` · `status` | `feedback.write/read/manage` |
| **数据集** | `POST /api/dataset/export` · `GET` · `download` · `holdout` | `dataset.read/export` |
| **权重** | `GET /api/weights` · `upload` · `set-default` · `delete` | `weight.read/write/switch/delete` |
| **回归门禁** | `GET /api/weights/{id}/gate` · `POST /api/weights/{id}/switch-gated` | `weight.read/switch` |
| **训练** | `POST /api/train` · `GET` · `cancel` | `train.read/write` |
| **异步任务** | `GET /api/tasks/jobs` · `POST /api/tasks/submit-async` | `task.write` |
| **配置** | `GET /api/config` · `PUT` · `audit` | `config.read/write` |
| **智能分析** | `POST /api/chat` · `knowledge` · `GET /api/knowledge` | `chat.use/knowledge.write` |
| **统计** | `GET /api/stats/overview` · `quality` · `drift` · `drift/action` | `task.read` / `detection.read` |
| **RBAC** | `GET /api/rbac/permissions` · `roles` · `users/{id}/roles` · `orgs` · `teams` | `role.read/write` · `user.role.assign` |
| **审计** | `GET /api/compliance/audit/export` · `preview` | `audit.read` |
| **合规** | `GET /api/compliance/privacy` · `POST /api/compliance/safety/screen` · `DELETE /api/compliance/users/{username}` | 公开 / `user.delete` |

完整契约见 [`docs/API.md`](docs/API.md) 与 <http://127.0.0.1:8000/docs>。

---

## 数据与合规

### 隐私政策
- 上传即隐式同意（PII 处理声明见 `/api/compliance/privacy`）
- 支持**数据删除权**：`DELETE /api/compliance/users/{username}` 级联清除
- **审计日志导出**：CSV / JSON，供外部合规审查

### 数据分级
| 数据 | 分级 | 备份 | 版本化 |
|---|---|---|---|
| 模型权重 `*.pt` | ⭐⭐⭐ | 必须 | `dataset_version` 关联 |
| 校正数据 | ⭐⭐⭐ | 必须 | 只追加不修改 |
| 训练集导出 | ⭐⭐⭐ | 必须 | `dataset_version` |
| 原始上传 | ⭐⭐ | 建议 | `task_id` 关联 |
| 结果可视化 | ⭐ | 不必 | 可重建 |

### 评估集冻结
首次导出随机抽 10% 进入 `holdout/`，**永不参与训练**，用于 mAP 基线。

---

## 部署

### Docker（推荐）
```bash
docker compose up --build
```

### 生产要点
- **强制改密码**：`VF_REQUIRE_PASSWORD_CHANGE=true`
- **HTTPS / 反代**：在 nginx/traefik 终止 TLS
- **密钥管理**：`.env` 不入库；生产用 KMS / Vault
- **备份**：`runtime_data/` 与 `backend/weights/` 定期备份

详见 `.env.example`。

---

## 开发指南

### 常用命令
```bash
# 后端
cd backend && pytest                    # 120+ 测试
python -m ruff check app tests          # lint
python -m ruff format app tests         # 格式化

# 前端
cd frontend && npm run type-check
npm run lint
npm run build
```

### 提交规范
Conventional Commits：`feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:`

### CI
`.github/workflows/ci.yml` 4 job：lint → test + build → e2e smoke

---

## 路线图

### ✅ 已完成（M1–M6 + P1–P3）
- 完整闭环（识别/校正/导出/训练/切换）
- RBAC + org/team 数据隔离
- 真 YOLO 集成（ultralytics）
- 2FA / SSO / API Key
- 回归门禁 + 异步推理 + 漂移闭环
- 合规（PII / 删除权 / 审计导出 / RAG 安全）
- Docker + CI + 观测性

### 🔜 计划中
- 视频识别（抽帧推理）
- 训练曲线 UI（对比对话框画 mAP/loss）
- 多语言 i18n
- 前端 E2E 测试
- 依赖扫描 / SAST

---

## License

待定。

---

## 致谢

- [ultralytics](https://github.com/ultralytics/ultralytics) — YOLO
- [FastAPI](https://fastapi.tiangolo.com) / [Vue](https://vuejs.org) / [Element Plus](https://element-plus.org)
- [LangChain](https://www.langchain.com) / [LangGraph](https://langchain-ai.github.io/langgraph)
