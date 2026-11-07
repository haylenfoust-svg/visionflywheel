# ADR-002: 降级检测器（torch 不可用时闭环仍可跑）

- **状态**：已采纳
- **日期**：2026-11-07
- **关联**：`PRD.md` FR-9.1-9.2、G5、NFR-16、R-01；`ARCHITECTURE.md` §2、§8

## 背景

部署环境常面临三类约束：

1. **无 GPU**：客户机房无显卡，CPU 推理慢但可接受
2. **torch 装不上**：Python 版本冲突、内网 PyPI 不全、驱动问题
3. **快速演示需求**：售前/教学场景需要"先看到效果"

如果 torch 不可用就整个系统跑不起来，会卡死两类用户：

- **学习者**：想先跑通流程，再补环境
- **客户 IT**：环境受限，需先验证业务闭环

PRD G5 / NFR-16 明确要求：**无 GPU 环境可跑，闭环依旧完整**。

## 决策

引入 **可插拔检测器协议**，实现两套：

| 实现 | 何时启用 | 说明 |
|---|---|---|
| `yolo_detector` | torch + ultralytics 可用 | 真实 YOLO 推理，默认 |
| `fallback_detector` | torch 加载失败或配置强制启用 | 内置规则检测器（颜色/轮廓/固定区域） |

**协议统一**（`services/` 内的抽象）：

```python
class Detector(Protocol):
    def detect(self, image_path: str, conf: float, iou: float) -> list[Detection]: ...
    def reload(self, weight_path: str | None) -> None: ...
    @property
    def is_fallback(self) -> bool: ...
```

**行为要求**：

1. 推理结果返回**同一数据结构**（含 `class_id / class_name / confidence / bbox`），业务层零感知
2. 启动时探测 torch，失败自动降级 + 页面明确提示（FR-9.2）
3. 配置项 `enable_fallback_detector`（默认 true）可强制关闭降级（生产可拒绝降级）
4. 降级检测器输出的 class 用统一枚举（如 `object / defect`），仍可走中英映射与完整闭环

**降级检测器实现思路**（M2 起提供）：

- 基于 OpenCV：自适应阈值 → 轮廓 → 最小外接矩形
- 返回类别统一为 `object`（可配置）
- 置信度 = 轮廓面积 / 图像面积的启发式值（0~1）

## 后果

### 正面
- 学习曲线平缓：**先跑通闭环，再补环境**，符合 G1 / NFR-16
- 教学/演示场景零门槛
- 协议抽象使未来换检测器（RT-DETR、SAM）成本极低
- 即便生产环境误配置，闭环不中断（仅精度下降 + 告警）

### 负面 / 权衡
- fallback 精度远低于 YOLO，可能给用户错误预期 → 由页面**强提示**缓解
- 多一套代码要维护 → 用协议统一接口，测试同跑两套
- 用户可能误以为"系统跑通了就够了" → README 显式声明"fallback 仅用于流程验证"

## 备选方案与放弃理由

- **无降级，硬依赖 torch**：简单，但违反 G5 / NFR-16
- **降级为"返回空检测"**：太弱，闭环形同虚设
- **降级为云端 API（如百度/腾讯）**：违反私有化部署定位，且引入网络依赖
- **用 ONNX Runtime 替代 torch**：可行但仍是重依赖，安装失败问题未解决

## 强制约束（防滥用）

- 降级状态必须在响应元信息中标记 `detector_mode: "fallback"`
- 累计使用 fallback 推理 > N 次（默认 100）→ 告警日志
- 训练能力在 fallback 模式下**禁用**（FR-6.1 仅在真实 YOLO 可用时启用）

## 参考
- OpenCV 轮廓检测：`cv2.findContours`
- ultralytics 装机疑难：https://github.com/ultralytics/ultralytics/issues
