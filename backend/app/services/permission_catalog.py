"""Fine-grained permission catalog (B端-2).

Permission codes are namespaced as `category.action`. Every protected
endpoint declares one required code via `@require_permission(...)`.

The catalog is seeded into the `permissions` table at startup so the admin
UI can enumerate and assign them to roles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    name: str
    category: str
    description: str = ""


# ---------------- catalog ----------------
PERMISSION_CATALOG: list[PermissionDef] = [
    # 用户
    PermissionDef("user.read", "查看用户", "user", "查看用户列表与详情"),
    PermissionDef("user.write", "创建/编辑用户", "user", "创建用户、改基础信息"),
    PermissionDef("user.delete", "删除用户", "user", "删除或禁用用户"),
    PermissionDef("user.role.assign", "分配角色", "user", "给用户授予角色"),
    # 角色与权限
    PermissionDef("role.read", "查看角色", "role", "查看角色与权限矩阵"),
    PermissionDef("role.write", "管理角色", "role", "创建/编辑角色、修改权限勾选"),
    PermissionDef("role.delete", "删除角色", "role", "删除非系统角色"),
    # 组织 / 团队
    PermissionDef("org.read", "查看组织", "org", "查看组织树"),
    PermissionDef("org.write", "管理组织", "org", "创建/编辑/删除组织"),
    PermissionDef("team.read", "查看团队", "team", "查看团队与成员"),
    PermissionDef("team.write", "管理团队", "team", "创建/编辑团队、管理成员"),
    # 识别任务
    PermissionDef("task.read", "查看任务", "task", "查看识别任务与结果"),
    PermissionDef("task.write", "创建任务", "task", "上传识别、批量识别"),
    PermissionDef("task.delete", "删除任务", "task", "删除任务与产物"),
    # 检测
    PermissionDef("detection.read", "查看检测", "detection", "查看检测结果与统计"),
    PermissionDef("detection.correct", "校正检测", "detection", "五种校正动作、撤销"),
    # 反馈
    PermissionDef("feedback.read", "查看工单", "feedback", "查看工单"),
    PermissionDef("feedback.write", "提交工单", "feedback", "提交反馈"),
    PermissionDef("feedback.manage", "处理工单", "feedback", "回复/解决/驳回工单"),
    # 数据集
    PermissionDef("dataset.read", "查看数据集", "dataset", "查看导出历史、holdout"),
    PermissionDef("dataset.export", "导出数据集", "dataset", "触发 YOLO 训练集导出"),
    PermissionDef("dataset.delete", "删除数据集", "dataset", "删除导出版本"),
    # 权重
    PermissionDef("weight.read", "查看权重", "weight", "查看权重列表"),
    PermissionDef("weight.write", "上传权重", "weight", "上传/注册权重"),
    PermissionDef("weight.switch", "切换默认权重", "weight", "热切换默认权重"),
    PermissionDef("weight.delete", "删除权重", "weight", "删除权重文件"),
    # 训练
    PermissionDef("train.read", "查看训练", "train", "查看训练任务与指标"),
    PermissionDef("train.write", "发起训练", "train", "创建/取消训练任务"),
    # 配置
    PermissionDef("config.read", "查看配置", "config", "查看系统配置"),
    PermissionDef("config.write", "修改配置", "config", "修改系统配置"),
    # 审计
    PermissionDef("audit.read", "查看审计", "audit", "查看审计日志"),
    # 智能分析
    PermissionDef("chat.use", "使用智能分析", "chat", "对话式问答"),
    PermissionDef("chat.knowledge.write", "维护知识库", "chat", "存入/删除知识条目"),
    # 系统
    PermissionDef("system.admin", "系统管理", "system", "最高管理权限，隐含所有权限"),
    PermissionDef("session.read", "查看会话", "system", "查看活跃登录会话"),
    PermissionDef("session.revoke", "强制下线", "system", "撤销他人会话"),
]

PERMISSION_INDEX: dict[str, PermissionDef] = {p.code: p for p in PERMISSION_CATALOG}

CATEGORIES: list[tuple[str, str]] = [
    ("user", "用户"),
    ("role", "角色与权限"),
    ("org", "组织"),
    ("team", "团队"),
    ("task", "识别任务"),
    ("detection", "检测"),
    ("feedback", "反馈工单"),
    ("dataset", "数据集"),
    ("weight", "权重"),
    ("train", "训练"),
    ("config", "配置"),
    ("audit", "审计"),
    ("chat", "智能分析"),
    ("system", "系统"),
]


# ---------------- default roles ----------------
# Admin gets everything (via system.admin). Operator is the day-to-day user
# of the correction loop. Viewer is read-only.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": ["system.admin"],
    "operator": [
        "task.read",
        "task.write",
        "detection.read",
        "detection.correct",
        "feedback.read",
        "feedback.write",
        "dataset.read",
        "weight.read",
        "train.read",
        "config.read",
        "chat.use",
        "chat.knowledge.write",
    ],
    "viewer": [
        "task.read",
        "detection.read",
        "feedback.read",
        "dataset.read",
        "weight.read",
        "train.read",
    ],
}

DEFAULT_ROLES: list[tuple[str, str, str, bool]] = [
    ("admin", "管理员", "拥有所有权限，可管理角色与用户", True),
    ("operator", "操作员", "日常识别与校正的操作人员", True),
    ("viewer", "观察员", "只读用户，可查看但不能修改", True),
]


# ---------------- helpers ----------------
def is_admin_permission(code: str) -> bool:
    return code == "system.admin"


def expand_permissions(codes: set[str]) -> set[str]:
    """system.admin implies every other code."""
    if "system.admin" in codes:
        return {p.code for p in PERMISSION_CATALOG}
    return set(codes)


def describe(code: str) -> str:
    entry = PERMISSION_INDEX.get(code)
    return entry.name if entry else code
