# 视觉飞轮 VisionFlywheel

> 以 YOLO 为核心、人工校正为飞轮动力的**自进化图像识别闭环系统**。
>
> **上传即识别 · 识别即可视化 · 看得不对就在图上改 · 改完的数据自动变训练集 · 训练回流后模型更强。**

---

## 这是什么

很多视觉方案都停在"画完框"这一步。**视觉飞轮**打通了从识别到再训练的完整闭环：

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

模型不是一次训练定终身，而是**随着每一次校正持续变强**。适用于工业质检、仓储分拣、果蔬/零件盘点、巡检取证等场景。

---

## 状态

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M1** | 骨架：FastAPI + JWT + Vue3 登录、权限、配置中心 | ✅ 完成 |
| **M2** | 识别主链：上传 → YOLO 推理 → 落库 → 可视化 | ✅ 完成 |
| **M3** | 校正闭环：Canvas 五种校正动作 + 审计流水 | ✅ 完成 |
| **M4** | 导出与回流：YOLO 训练集 + 增量训练 + 权重热切换 | ✅ 完成 |
| **M5** | 智能分析：LangGraph + RAG 问答、Dashboard、Admin、批量、Docker | ✅ 完成 |
| **M6** | 真 YOLO 集成、视频识别、生产加固 | 🔄 部分 |

---

## 5 分钟跑通

### 环境要求

- Python **3.10+**（推荐 3.12）
- Node.js **18+**（推荐 20/22）
- （可选）CUDA GPU — 无 GPU 时用 CPU，M2 起支持降级检测器

### 1. 后端

```bash
cd backend
python -m venv ../.venv                  # 在仓库根建 venv
../.venv/Scripts/activate                # Windows
# source ../.venv/bin/activate           # macOS / Linux

pip install -r requirements.txt
python -m app.seed                        # 建初始管理员 admin / admin123
python -m uvicorn app.main:app --port 8000 --reload
```

打开 <http://127.0.0.1:8000/docs> 可以看到自动 OpenAPI 文档。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5173>，用 `admin / admin123` 登录。

> ⚠️ `admin123` 是开发默认密码，**生产部署前务必改掉**。

### 3. （可选）装真 YOLO

默认用内置降级检测器（OpenCV 规则）——**无需 GPU 也能跑完整闭环**。想用真 YOLO：

```bash
cd backend
pip install -r requirements-ml.txt       # 拉 ultralytics + torch（约 2 GB）
# 下载预训练权重 yolov8n.pt 放到 backend/weights/
```

重启后自动识别并切换到 YOLO 推理（页面顶部会显示 "YOLO" 而不是 "降级检测器"）。

### 4. （可选）Docker 一键起

```bash
docker compose up --build
```

- 前端：<http://localhost:8080>
- 后端 API：<http://localhost:8000/docs>

需要真 YOLO 时：`WITH_ML=1 docker compose build backend`。

---

## 项目结构

```
VisionFlywheel/
├── docs/                    设计文档（与代码同版本演进）
│   ├── PRD.md               产品需求：MVP 边界、用户故事、FR/NFR、风险
│   ├── DESIGN.md            产品设计：核心闭环、技术栈、数据模型
│   ├── ARCHITECTURE.md      技术架构：分层、目录、请求生命周期
│   ├── API.md               接口契约：40+ 接口、错误码、TS 类型
│   └── ADR/                 架构决策记录
│       ├── 001-tech-stack.md
│       ├── 002-fallback-detector.md
│       └── 003-config-priority.md
├── backend/                 FastAPI + SQLAlchemy + JWT + SQLite
│   ├── app/
│   │   ├── core/            config · database · security · deps · envelope · exceptions
│   │   ├── models/          User · ConfigEntry · AuditLog
│   │   ├── schemas/         Pydantic DTO
│   │   ├── api/             auth · system · (M2 起 detect / correct / dataset / weights)
│   │   ├── services/        业务核心（M2 起 yolo / correction / dataset_exporter）
│   │   └── utils/           files · imaging · video
│   ├── tests/               单元与集成测试
│   └── weights/             *.pt 模型权重（不入 git）
├── frontend/                Vue3 + Element Plus + Pinia + Vite + TS
│   └── src/
│       ├── views/           Login · Dashboard · (M2 起 Detect · Annotate · Dataset)
│       ├── components/      ImageAnnotator（M3 核心）等
│       ├── stores/          auth · task · config
│       └── api/             axios 封装
├── scripts/                 e2e_smoke.py 等辅助脚本
└── runtime_data/            运行时产物（上传、结果、训练集、SQLite，不入 git）
```

---

## 技术栈

| 层 | 选型 |
|---|---|
| 目标检测 | [ultralytics YOLO](https://docs.ultralytics.com)（v8n / v26n） |
| 后端 | FastAPI + SQLAlchemy + JWT + Pydantic |
| 前端 | Vue3 + Element Plus + Pinia + Vite + TypeScript |
| 智能体 | LangChain + LangGraph（M5） |
| 检索增强 | RAG + 向量库（离线哈希兜底）（M5） |
| 部署 | Docker Compose（M6） |

---

## 开发

### 常用命令

```bash
# 后端
cd backend
pytest                                   # 跑测试（23 个）
python -m ruff check app tests           # lint
python -m ruff format app tests          # 格式化

# 前端
cd frontend
npm run type-check                       # vue-tsc 类型检查
npm run lint                             # eslint
npm run build                            # 生产构建
```

### 端到端冒烟

```bash
# 先起后端（见上文），然后：
python scripts/e2e_smoke.py http://127.0.0.1:8000
```

7 项检查：health · login · me · config 读写 · audit · 权限矩阵。

### 提交规范

[Conventional Commits](https://www.conventionalcommits.org)：

```
feat: 新功能        feat(correction): 支持拖拽补框
fix: 修 bug         fix(dataset): 修正 val 划分比例
docs: 文档          docs: 补 ARCHITECTURE 时序图
refactor: 重构      test: 测试       chore: 工程化
```

---

## 核心能力

### 已支持

- ✅ **完整闭环**：上传识别 → 可视化 → 五种校正 → 导出 YOLO 训练集 → 训练 → 权重热切换
- ✅ **可插拔检测器**：YOLO（ultralytics）+ 内置降级检测器（ADR-002），无 GPU 也能跑闭环
- ✅ **Canvas 标注**：拖拽移动 / 四角缩放 / 空白补框 / 五种校正动作 / undo
- ✅ **审计流水**：只追加不修改，撤销也留痕
- ✅ **YOLO 标准导出**：`data.yaml` + `images/{train,val}` + `labels/{train,val}`，标签归一化
- ✅ **holdout 评估集冻结**：永不参与训练，权重记录 `holdout_map` 基线
- ✅ **权重热切换**：切换默认权重即刻生效，`requires_restart=false`
- ✅ **中英标签映射**：`dog` → 「狗」，可配置
- ✅ **配置三级优先级**：DB > env > 默认，页面改即生效
- ✅ **批量上传**：多图拖拽 + 进度条
- ✅ **智能分析**：基于真实识别统计的问答 + 知识库沉淀 + 反思自检
- ✅ **Dashboard**：6 统计卡 + 4 趋势/分布图 + 状态分布 + 最近活动
- ✅ **Admin 面板**：用户管理 / 系统配置 / 审计日志 / 反馈工单
- ✅ **Docker Compose**：一键起前后端
- ✅ **JWT + 角色权限**：user / admin 两层
- ✅ **稳定错误码**：统一响应信封，40+ API

### 计划中

- ⏳ 视频抽帧识别
- ⏳ LangGraph 真 LLM 通路（当前有可选降级到模板回答）
- ⏳ Webhook / IM 通知
- ⏳ 数据漂移检测

---

## 环境变量

复制 `.env.example` 为 `.env`，按需填写：

| 变量 | 默认 | 说明 |
|---|---|---|
| `VF_SECRET_KEY` | dev 占位 | **必须改成随机长字符串**（生产） |
| `VF_DATABASE_URL` | `sqlite:///./runtime_data/app.db` | 数据库连接 |
| `VF_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT 过期分钟 |
| `VF_HOST` / `VF_PORT` | `127.0.0.1` / `8000` | 后端监听 |
| `VF_CORS_ORIGINS` | `http://localhost:5173` | 允许的跨域来源 |

业务阈值（`conf` / `iou` / 默认权重 / 标签映射等）登录后在**控制台 → 配置**页面改，无需重启。

---

## 文档

| 文档 | 用途 |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | 需求与边界：用户故事、FR/NFR、风险、DoD |
| [`docs/DESIGN.md`](docs/DESIGN.md) | 产品设计：核心闭环、技术栈、数据模型 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 技术架构：分层、目录、请求生命周期、测试落点 |
| [`docs/API.md`](docs/API.md) | 接口契约：前后端并行开发的唯一事实来源 |
| [`docs/ADR/`](docs/ADR/) | 关键决策：技术栈选型、降级策略、配置优先级 |

接口运行时文档：<http://127.0.0.1:8000/docs>（Swagger）。

---

## License

待定。
