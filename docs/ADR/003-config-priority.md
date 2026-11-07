# ADR-003: 配置三级优先级（数据库 > 环境变量 > 代码默认值）

- **状态**：已采纳
- **日期**：2026-11-07
- **关联**：`PRD.md` FR-7、NFR-15；`ARCHITECTURE.md` §5

## 背景

视觉飞轮的配置来源有三类诉求，彼此冲突：

| 诉求 | 典型配置 | 期望的变更方式 |
|---|---|---|
| **运维/部署** | 数据库连接、密钥、监听端口 | 启动时定，环境变量注入 |
| **业务运行** | 默认权重、conf/iou 阈值、标签映射、val_ratio | **页面改，立即生效，不重启** |
| **代码默认** | 兜底值、内部开关 | 版本控制，随代码演进 |

如果统一放环境变量，业务配置每次改都要重启服务；如果统一放代码，运维无法覆盖；如果统一放数据库，密钥又不安全。

PRD FR-7.1 明确要求：**配置三级优先级 DB > env > 默认**。

## 决策

实现 **三级配置解析器**：

```
读取 key → ① 查数据库 configs 表  → 命中则返回
           ↓ 未命中
           ② 读环境变量 / .env    → 命中则返回
           ↓ 未命中
           ③ 使用代码默认值
```

**写入语义**：
- **页面改配置** → 写 `configs` 表 → 触发 `on_change` 钩子 → 立即生效
- **环境变量** → 只读不写，运维层控制
- **代码默认** → 版本化，只随代码变更

**变更钩子**（`core/events.py` + `services/config_service.py`）：

| 配置项 | 钩子动作 |
|---|---|
| `default_weight_id` | `weight_manager.reload()` 重载权重 |
| `llm_model` / `embedding_model` | `llm_service.reset()` / `rag_service.reset()` |
| `label_map` | 重建中英映射缓存 |
| `conf_threshold` / `iou_threshold` | 无需钩子，下次推理生效 |

**审计**：所有配置变更写入 `audit_logs`（key、old_value、new_value、operator、ts），FR-7.5。

## 后果

### 正面
- **业务配置可热改**（FR-7.2），符合 PRD G4"不重启服务"
- **运维友好**：密钥、端口走 env，不入 DB
- **代码友好**：默认值版本化，新部署环境有兜底
- **可追溯**：变更留审计

### 负面 / 权衡
- 解析逻辑多一层复杂度 → `config_service` 单点实现，所有调用走 `config_service.get(key)`
- "当前值"可能让用户困惑（"为什么页面看到的和 env 不一样"）→ 配置 UI 显示 `source` 字段（db/env/default）
- DB 优先级可能掩盖 env 变更 → 部署文档明确"改 env 后需清理对应 DB 项或保留双源"

## 备选方案与放弃理由

- **只用环境变量**：业务配置改一次要重启，违反 FR-7.2
- **只用数据库**：密钥入 DB，违反 NFR-10 安全要求
- **配置文件（YAML/JSON）**：分发成本高，改一次要同步多机
- **consul / etcd**：0-to-1 阶段过度工程

## 实现约束

1. `config_service.get(key)` 是**唯一读入口**，禁止服务层直接读 `os.environ`
2. 写入必须走 `config_service.set(key, value, operator)`，自动写审计
3. 启动时打印三级配置解析结果（脱敏），便于排查
4. 敏感配置（数据库密码、JWT secret）**禁止写入 DB**，仅 env 来源

## 参考
- pydantic-settings：https://docs.pydantic.dev/latest/concepts/pydantic_settings
- FastAPI 依赖注入模式
