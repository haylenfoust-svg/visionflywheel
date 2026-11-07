# API 契约 — VisionFlywheel

> **文档目的**：前后端并行开发的**唯一事实来源**（Single Source of Truth）。
> **约定**：任何接口变更必须先改本文档并走 PR 评审，再改代码。
> **运行时文档**：FastAPI 自动 OpenAPI 在 `/docs`，本文档是设计期契约。
> **对应 PRD**：`PRD.md` §6 功能需求

---

## 0. 通用约定

### 0.1 协议与前缀

| 项 | 值 |
|---|---|
| 协议 | HTTP/1.1 + JSON（除文件上传/下载） |
| 前缀 | `/api` |
| 编码 | UTF-8 |
| 时间格式 | ISO 8601 UTC，如 `2026-11-07T10:30:00Z` |
| ID 类型 | 整数自增主键 `id`；业务唯一键用字符串 |

### 0.2 认证

- 方案：**JWT Bearer Token**
- 请求头：`Authorization: Bearer <token>`
- 登录接口无需 token
- token 过期返回 `401`，角色不符返回 `403`

### 0.3 统一响应信封

**成功响应**（HTTP 200 / 201）：
```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

**错误响应**（HTTP 4xx / 5xx）：
```json
{
  "code": 40001,
  "message": "validation error: conf must be between 0 and 1",
  "data": null,
  "request_id": "uuid-v4"
}
```

**错误码分段**：

| 范围 | 含义 |
|---|---|
| 0 | 成功 |
| 40000-40099 | 请求错误（参数、格式） |
| 40100-40199 | 认证错误 |
| 40300-40399 | 权限错误 |
| 40400-40499 | 资源不存在 |
| 40900-40999 | 冲突（重复、状态机错误） |
| 42200-42299 | 业务校验失败 |
| 50000-50099 | 服务器内部错误 |
| 50300-50399 | 服务不可用（含降级提示） |

### 0.4 分页

请求：`?page=1&page_size=20&sort_by=created_at&sort_order=desc`

响应 `data`：
```json
{
  "items": [...],
  "total": 123,
  "page": 1,
  "page_size": 20,
  "pages": 7
}
```

### 0.5 通用 DTO

**Detection**：
```json
{
  "id": 101,
  "task_id": 5,
  "image_path": "uploads/5/img_001.jpg",
  "result_path": "results/5/img_001.jpg",
  "class_id": 0,
  "class_name": "dog",
  "class_name_zh": "狗",
  "confidence": 0.87,
  "bbox": {"x1": 120.5, "y1": 80.0, "x2": 320.0, "y2": 260.0},
  "status": "pending",
  "source": "model",
  "created_at": "2026-11-07T10:30:00Z"
}
```

`status`: `pending` | `corrected` | `rejected`
`source`: `model` | `manual`
`bbox` 坐标：像素坐标系，原点左上

---

## 1. 认证 `/api/auth`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 公开 | 用户名密码登录 |
| POST | `/api/auth/logout` | 任意登录 | 退出（客户端丢弃 token） |
| GET | `/api/auth/me` | 任意登录 | 当前用户信息 |
| POST | `/api/auth/refresh` | 任意登录 | 刷新 token |
| GET | `/api/auth/users` | admin | 用户列表 |
| POST | `/api/auth/users` | admin | 创建用户 |
| PUT | `/api/auth/users/{id}` | admin | 更新用户（含禁用） |
| DELETE | `/api/auth/users/{id}` | admin | 删除用户 |

### POST `/api/auth/login`
**Request**：
```json
{"username": "zhang", "password": "****"}
```
**Response 200**：
```json
{
  "code": 0,
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {"id": 1, "username": "zhang", "role": "admin"}
  }
}
```
**错误**：`40101 用户名或密码错误`

---

## 2. 任务与识别 `/api/tasks`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/tasks/upload` | user | 单图上传识别（同步） |
| POST | `/api/tasks/batch` | user | 批量上传（异步，返回 task_ids） |
| POST | `/api/tasks/video` | user | 视频上传（异步抽帧识别） |
| GET | `/api/tasks` | user | 任务列表（分页、筛选） |
| GET | `/api/tasks/{id}` | user | 任务详情 |
| GET | `/api/tasks/{id}/detections` | user | 任务检测列表 |
| GET | `/api/tasks/{id}/progress` | user | 异步任务进度 |
| DELETE | `/api/tasks/{id}` | admin | 删除任务及相关产物 |

### POST `/api/tasks/upload`
**Request**：`multipart/form-data`
- `file`：图片文件
- `conf_threshold`：float，可选，默认读配置
- `iou_threshold`：float，可选
- `imgsz`：int，可选，默认 640

**Response 200**：
```json
{
  "code": 0,
  "data": {
    "task_id": 5,
    "status": "done",
    "image_url": "/api/files/uploads/5/img_001.jpg",
    "result_url": "/api/files/results/5/img_001.jpg",
    "detector_mode": "yolo",
    "inference_ms": 230,
    "detections": [Detection, ...]
  }
}
```
**降级时**：`detector_mode: "fallback"` + 响应头 `X-VisionFlywheel-Detector: fallback`（FR-9.2）

---

## 3. 检测结果 `/api/detections`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/detections/{id}` | user | 检测详情 |
| GET | `/api/detections/pending` | user | 未校正样本（用于工作台） |
| GET | `/api/detections/stats` | user | 统计（按类别、状态、时间） |

### GET `/api/detections/stats`
**Response**：
```json
{
  "code": 0,
  "data": {
    "total": 1245,
    "by_status": {"pending": 120, "corrected": 1100, "rejected": 25},
    "by_class": [
      {"class_name": "dog", "class_name_zh": "狗", "count": 600},
      {"class_name": "cat", "class_name_zh": "猫", "count": 645}
    ],
    "today": {"detected": 88, "corrected": 40},
    "avg_confidence": 0.82
  }
}
```
> 该接口供 FR-8 智能分析读取，作为量化问答的事实来源。

---

## 4. 校正 `/api/corrections`（飞轮核心）

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/corrections` | user | 提交一条校正 |
| POST | `/api/corrections/batch` | user | 批量提交（一次工作台会话） |
| POST | `/api/corrections/undo` | user | 撤销最近一次校正 |
| GET | `/api/corrections/audit` | admin | 审计流水（只读） |

### POST `/api/corrections`
**Request**：
```json
{
  "detection_id": 101,
  "action": "relabel",
  "new_class_name": "dog",
  "new_bbox": {"x1": 118.0, "y1": 78.0, "x2": 322.0, "y2": 262.0},
  "comment": "看起来更像狗"
}
```
`action` 枚举：
- `confirm`：确认正确（无需其他字段）
- `relabel`：改标签（必带 `new_class_name`）
- `false_positive`：标记误检（无需其他字段）
- `adjust`：改框（必带 `new_bbox`）
- `add`：补框（`detection_id` 置 null，必带 `image_id` + `new_bbox` + `new_class_name`）

**Response 200**：
```json
{
  "code": 0,
  "data": {
    "correction_id": 888,
    "detection_id": 101,
    "action": "relabel",
    "old_value": "cat",
    "new_value": "dog",
    "created_at": "2026-11-07T10:35:00Z"
  }
}
```

**约束（FR-3.7）**：审计流水**只追加**。任何 `PUT/PATCH/DELETE /api/corrections/{id}` 一律 `403`。

---

## 5. 反馈工单 `/api/feedback`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/feedback` | user | 提交工单 |
| GET | `/api/feedback` | user | 我的工单 / admin 全部 |
| PUT | `/api/feedback/{id}/reply` | admin | 回复 |
| PUT | `/api/feedback/{id}/status` | admin | 流转状态 |

---

## 6. 数据集 `/api/dataset`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/dataset/pending` | admin | 未导出样本数与预览 |
| POST | `/api/dataset/export` | admin | 触发导出 |
| GET | `/api/dataset` | admin | 导出历史 |
| GET | `/api/dataset/{id}` | admin | 导出详情（含 data.yaml 预览） |
| GET | `/api/dataset/{id}/download` | admin | 下载 zip |
| GET | `/api/dataset/holdout` | admin | 评估集列表（冻结） |

### POST `/api/dataset/export`
**Request**：
```json
{
  "name": "factory_v2",
  "val_ratio": 0.2,
  "include_rejected": false,
  "seed": 42
}
```
**Response 202**（异步）：
```json
{
  "code": 0,
  "data": {
    "dataset_version": "20261107-103000-a1b2c3",
    "status": "exporting",
    "total_samples": 240,
    "estimated_seconds": 12
  }
}
```

**产物结构**（FR-5.2）：
```
runtime_data/datasets/{dataset_version}/
├── data.yaml
├── images/
│   ├── train/
│   └── val/
└── labels/
    ├── train/
    └── val/
```

---

## 7. 权重 `/api/weights`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/weights` | user | 权重列表 |
| POST | `/api/weights/upload` | admin | 上传 `.pt` |
| PUT | `/api/weights/{id}/default` | admin | **热切换**默认权重 |
| DELETE | `/api/weights/{id}` | admin | 删除权重 |
| GET | `/api/weights/{id}` | user | 权重详情 |

### PUT `/api/weights/{id}/default`
**Response 200**：
```json
{
  "code": 0,
  "data": {
    "weight_id": 2,
    "filename": "best_20261107.pt",
    "is_default": true,
    "reloaded_in_ms": 820,
    "requires_restart": false
  }
}
```
**约束**：`requires_restart` 必须为 `false`（FR-6.5 / G4）。

---

## 8. 训练 `/api/train`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/train` | admin | 触发训练 |
| GET | `/api/train` | admin | 训练任务列表 |
| GET | `/api/train/{id}` | admin | 训练详情（含日志、进度） |
| POST | `/api/train/{id}/cancel` | admin | 取消训练 |
| GET | `/api/train/{id}/metrics` | admin | 训练指标（mAP、loss） |

### POST `/api/train`
**Request**：
```json
{
  "dataset_version": "20261107-103000-a1b2c3",
  "base_weight": "yolov8n.pt",
  "epochs": 100,
  "imgsz": 640,
  "batch": 16,
  "name": "run_v1"
}
```
**Response 202**：训练任务 ID + 预估时长

**约束**：
- 训练仅在 `detector_mode == "yolo"` 时启用（ADR-002）
- 训练完成自动注册 `weights`，记录 `dataset_version`

---

## 9. 配置 `/api/config`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/config` | user | 读配置（含 `source` 字段） |
| PUT | `/api/config/{key}` | admin | 改配置（写 DB + 审计 + 钩子） |
| GET | `/api/config/audit` | admin | 配置变更审计 |

### GET `/api/config`
**Response**：
```json
{
  "code": 0,
  "data": {
    "conf_threshold": {"value": 0.5, "source": "db", "default": 0.5},
    "iou_threshold": {"value": 0.45, "source": "env", "default": 0.45},
    "default_weight_id": {"value": 2, "source": "db", "default": null},
    "label_map": {"value": {"dog": "狗", "cat": "猫"}, "source": "db", "default": {}},
    "val_ratio": {"value": 0.2, "source": "default", "default": 0.2},
    "enable_fallback_detector": {"value": true, "source": "default", "default": true}
  }
}
```

---

## 10. 智能分析 `/api/chat`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/chat` | user | 提问（流式或非流式） |
| GET | `/api/chat/sessions` | user | 会话列表 |
| GET | `/api/chat/sessions/{id}/messages` | user | 会话消息 |
| POST | `/api/chat/knowledge` | user | 保存问答到知识库 |
| GET | `/api/knowledge` | user | 知识库列表 |
| DELETE | `/api/knowledge/{id}` | admin | 删除知识条目 |

### POST `/api/chat`
**Request**：
```json
{
  "session_id": 1,
  "question": "今天识别了多少 defect？"
}
```
**Response 200**：
```json
{
  "code": 0,
  "data": {
    "message_id": 55,
    "answer": "今天共识别 88 个目标，其中 32 个被标记为误检（false_positive）…",
    "sources": ["stats:today", "knowledge:12"],
    "is_hallucination_checked": true
  }
}
```
**约束（FR-8.3）**：`answer` 必须标注数据来源；无依据时明确"我不知道"，不得编造。

---

## 11. 文件 `/api/files`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/files/{kind}/{path}` | user | 静态文件（uploads / results） |

**约束**：禁止访问 `weights/` 下的任何文件（NFR-11）。

---

## 12. 系统 `/api/system`

| Method | Path | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/system/health` | 公开 | 健康检查 |
| GET | `/api/system/info` | user | 系统信息（版本、detector_mode、权重） |

### GET `/api/system/health`
```json
{
  "code": 0,
  "data": {
    "status": "healthy",
    "detector_mode": "yolo",
    "db": "ok",
    "version": "0.1.0"
  }
}
```

---

## 13. 错误码字典

| code | HTTP | message |
|---|---|---|
| 0 | 200 | ok |
| 40001 | 400 | 参数校验失败 |
| 40002 | 400 | 文件类型不支持 |
| 40003 | 400 | 文件过大 |
| 40101 | 401 | 用户名或密码错误 |
| 40102 | 401 | token 过期 |
| 40103 | 401 | token 无效 |
| 40301 | 403 | 权限不足 |
| 40302 | 403 | 审计记录禁止修改 |
| 40303 | 403 | fallback 模式禁止训练 |
| 40401 | 404 | 资源不存在 |
| 40901 | 409 | 状态冲突（如任务未完成） |
| 42201 | 422 | 校正动作字段缺失 |
| 50001 | 500 | 服务器内部错误 |
| 50301 | 503 | 检测器降级中 |

---

## 14. 接口变更流程

1. 先改本文档，提交 PR（标题含 `[API]`）
2. 评审通过后合并文档
3. 再实现代码，PR 关联文档 PR 编号
4. FastAPI `/docs` 自动 OpenAPI 必须与本文档一致
5. 破坏性变更必须升 `api_version` 并写 `CHANGELOG.md`

---

## 附录 A：TypeScript 类型定义（前端 `src/types/index.ts`）

```typescript
export interface Detection {
  id: number;
  task_id: number;
  image_path: string;
  result_path: string;
  class_id: number;
  class_name: string;
  class_name_zh: string;
  confidence: number;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  status: 'pending' | 'corrected' | 'rejected';
  source: 'model' | 'manual';
  created_at: string;
}

export type CorrectionAction = 'confirm' | 'relabel' | 'false_positive' | 'adjust' | 'add';

export interface CorrectionPayload {
  detection_id: number | null;
  action: CorrectionAction;
  image_id?: number;
  new_class_name?: string;
  new_bbox?: { x1: number; y1: number; x2: number; y2: number };
  comment?: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  request_id?: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
```
