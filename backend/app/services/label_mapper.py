"""English ↔ Chinese label mapping (PRD FR-2.6).

Canonical class names are English (matches ultralytics checkpoints).
The UI displays the Chinese name when a mapping is configured.

The mapping lives in `configs.label_map` (JSON) so admins can extend it
without a code change (ADR-003).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.config_service import get_config_service

# COCO-80 seed so the common case works out of the box. Admins can override
# or extend any of these through the `label_map` config key.
COCO_ZH_SEED: dict[str, str] = {
    "person": "人",
    "bicycle": "自行车",
    "car": "汽车",
    "motorcycle": "摩托车",
    "airplane": "飞机",
    "bus": "公交车",
    "train": "火车",
    "truck": "卡车",
    "boat": "船",
    "traffic light": "红绿灯",
    "fire hydrant": "消防栓",
    "stop sign": "停车标志",
    "parking meter": "停车计时器",
    "bench": "长椅",
    "bird": "鸟",
    "cat": "猫",
    "dog": "狗",
    "horse": "马",
    "sheep": "羊",
    "cow": "牛",
    "elephant": "大象",
    "bear": "熊",
    "zebra": "斑马",
    "giraffe": "长颈鹿",
    "backpack": "背包",
    "umbrella": "雨伞",
    "handbag": "手提包",
    "tie": "领带",
    "suitcase": "行李箱",
    "frisbee": "飞盘",
    "skis": "滑雪板",
    "snowboard": "滑雪橇",
    "sports ball": "运动球",
    "kite": "风筝",
    "baseball bat": "棒球棒",
    "baseball glove": "棒球手套",
    "skateboard": "滑板",
    "surfboard": "冲浪板",
    "tennis racket": "网球拍",
    "bottle": "瓶子",
    "wine glass": "酒杯",
    "cup": "杯子",
    "fork": "叉子",
    "knife": "刀",
    "spoon": "勺子",
    "bowl": "碗",
    "banana": "香蕉",
    "apple": "苹果",
    "sandwich": "三明治",
    "orange": "橙子",
    "broccoli": "西兰花",
    "carrot": "胡萝卜",
    "hot dog": "热狗",
    "pizza": "披萨",
    "donut": "甜甜圈",
    "cake": "蛋糕",
    "chair": "椅子",
    "couch": "沙发",
    "potted plant": "盆栽",
    "bed": "床",
    "dining table": "餐桌",
    "toilet": "马桶",
    "tv": "电视",
    "laptop": "笔记本电脑",
    "mouse": "鼠标",
    "remote": "遥控器",
    "keyboard": "键盘",
    "cell phone": "手机",
    "microwave": "微波炉",
    "oven": "烤箱",
    "toaster": "烤面包机",
    "sink": "水槽",
    "refrigerator": "冰箱",
    "book": "书",
    "clock": "时钟",
    "vase": "花瓶",
    "scissors": "剪刀",
    "teddy bear": "泰迪熊",
    "hair drier": "吹风机",
    "toothbrush": "牙刷",
}


class LabelMapper:
    """Resolves English canonical class names to display labels."""

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def _load(self) -> dict[str, str]:
        merged = dict(COCO_ZH_SEED)
        if self._db is not None:
            try:
                override = get_config_service().get(self._db, "label_map")
                if isinstance(override, dict):
                    merged.update({str(k): str(v) for k, v in override.items()})
            except Exception:
                pass
        return merged

    def to_zh(self, class_name: str) -> str:
        """Chinese display name; falls back to the English name when unmapped."""
        return self._load().get(class_name.lower(), class_name)

    def to_en(self, class_name: str) -> str:
        """Reverse lookup — used when a user edits a label to a Chinese name."""
        table = self._load()
        lowered = class_name.lower()
        for en, zh in table.items():
            if zh == class_name or en == lowered:
                return en
        return class_name

    def all_mappings(self) -> dict[str, str]:
        return self._load()


def map_labels(db: Session | None, class_name: str) -> str:
    return LabelMapper(db).to_zh(class_name)


def batch_map_labels(db: Session | None, names: list[str]) -> list[str]:
    mapper = LabelMapper(db)
    return [mapper.to_zh(n) for n in names]
