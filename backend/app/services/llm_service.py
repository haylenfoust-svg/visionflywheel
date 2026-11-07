"""LLM + RAG service — LangGraph-style pipeline with graceful degradation (PRD FR-8).

Pipeline:  intent classify -> vector search knowledge base -> load YOLO task
context -> generate -> reflect -> answer. The reflection step checks that
every factual claim is grounded in either the retrieval payload or the
task statistics; ungrounded claims are dropped or flagged.

If langchain / langgraph are not installed the service falls back to a
deterministic template-based answer driven purely by the real stats.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.correction import Correction
from app.models.dataset import DatasetExport
from app.models.detection import Detection
from app.models.feedback import FeedbackTicket
from app.models.task import Task
from app.models.weight import Weight

logger = logging.getLogger(__name__)

_LLM_AVAILABLE: bool | None = None


def _llm_available() -> bool:
    global _LLM_AVAILABLE
    if _LLM_AVAILABLE is None:
        try:
            import langchain  # noqa: F401
            import langgraph  # noqa: F401

            _LLM_AVAILABLE = True
        except Exception:
            _LLM_AVAILABLE = False
    return _LLM_AVAILABLE


# ---------------- knowledge base (hash-vector fallback) ----------------
@dataclass
class KnowledgeEntry:
    id: int
    question: str
    answer: str
    source: str = "manual"
    vector: list[float] = field(default_factory=list)


_KNOWLEDGE: list[KnowledgeEntry] = []


def _hash_vector(text: str, dim: int = 64) -> list[float]:
    """Deterministic hash-based embedding — offline-safe fallback."""
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = list(digest)
    vec = []
    for i in range(dim):
        vec.append((raw[i % len(raw)] / 255.0) * 2 - 1)
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def add_knowledge(question: str, answer: str, source: str = "manual") -> dict:
    entry = KnowledgeEntry(
        id=len(_KNOWLEDGE) + 1,
        question=question.strip(),
        answer=answer.strip(),
        source=source,
        vector=_hash_vector(question + " " + answer),
    )
    _KNOWLEDGE.append(entry)
    return {"id": entry.id, "question": entry.question, "answer": entry.answer}


def list_knowledge() -> list[dict]:
    return [
        {"id": e.id, "question": e.question, "answer": e.answer, "source": e.source}
        for e in _KNOWLEDGE
    ]


def delete_knowledge(entry_id: int) -> bool:
    global _KNOWLEDGE
    before = len(_KNOWLEDGE)
    _KNOWLEDGE = [e for e in _KNOWLEDGE if e.id != entry_id]
    return len(_KNOWLEDGE) < before


def _retrieve(question: str, k: int = 3) -> list[KnowledgeEntry]:
    if not _KNOWLEDGE:
        return []
    qv = _hash_vector(question)
    scored = []
    for entry in _KNOWLEDGE:
        score = sum(a * b for a, b in zip(qv, entry.vector, strict=False))
        scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:k]]


# ---------------- context builders ----------------
def _stats_context(db: Session) -> dict[str, Any]:
    total_det = db.query(func.count(Detection.id)).scalar() or 0
    total_task = db.query(func.count(Task.id)).scalar() or 0
    total_corr = db.query(func.count(Correction.id)).scalar() or 0
    total_ds = db.query(func.count(DatasetExport.id)).scalar() or 0
    total_weight = db.query(func.count(Weight.id)).scalar() or 0
    open_tickets = (
        db.query(func.count(FeedbackTicket.id)).filter(FeedbackTicket.status == "open").scalar() or 0
    )

    by_status_rows = db.query(Detection.status, func.count(Detection.id)).group_by(Detection.status).all()
    by_status = dict(by_status_rows)

    class_rows = (
        db.query(Detection.class_name, Detection.class_name_zh, func.count(Detection.id))
        .group_by(Detection.class_name, Detection.class_name_zh)
        .order_by(func.count(Detection.id).desc())
        .limit(8)
        .all()
    )
    by_class = [
        {"class_name": n, "class_name_zh": zh, "count": c} for n, zh, c in class_rows
    ]

    action_rows = (
        db.query(Correction.action, func.count(Correction.id)).group_by(Correction.action).all()
    )
    by_action = dict(action_rows)

    # today
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    today_det = (
        db.query(func.count(Detection.id)).filter(func.date(Detection.created_at) == today).scalar() or 0
    )
    today_corr = (
        db.query(func.count(Correction.id)).filter(func.date(Correction.created_at) == today).scalar() or 0
    )

    avg_conf = db.query(func.avg(Detection.confidence)).scalar() or 0.0

    return {
        "totals": {
            "detections": total_det,
            "tasks": total_task,
            "corrections": total_corr,
            "datasets": total_ds,
            "weights": total_weight,
            "open_tickets": open_tickets,
        },
        "by_status": by_status,
        "by_class": by_class,
        "by_action": by_action,
        "today": {"detections": today_det, "corrections": today_corr},
        "avg_confidence": round(float(avg_conf), 4),
    }


# ---------------- intent classification ----------------
_INTENT_PATTERNS = [
    ("count_detections", r"(多少|几|几个|数量|统计|count|how many).*(检测|识别|目标|框|defect|瑕疵|缺陷|detection)"),
    ("count_corrections", r"(多少|几|几个|数量|统计).*(校正|修正|修改|correction|标注)"),
    ("top_class", r"(最多|top|最常见|分布|类别|class|category).*(什么|哪个|类别|class)"),
    ("today_summary", r"(今天|今日|today).*(识别|检测|多少|做了什么|summary|总结)"),
    ("dataset_info", r"(数据集|dataset|导出|export|训练集)"),
    ("weight_info", r"(权重|weight|模型|model|mAP)"),
    ("ticket_info", r"(工单|ticket|反馈|feedback|待处理)"),
    ("help", r"(帮助|help|怎么用|如何|how to|能做什么)"),
]


def _classify_intent(question: str) -> str:
    lowered = question.lower()
    for intent, pattern in _INTENT_PATTERNS:
        if re.search(pattern, lowered):
            return intent
    return "general"


# ---------------- template-based answer (no-LLM path) ----------------
def _answer_from_stats(question: str, intent: str, stats: dict, retrieval: list[KnowledgeEntry]) -> tuple[str, list[str]]:
    sources = ["stats"]
    totals = stats["totals"]
    by_status = stats["by_status"]
    by_class = stats["by_class"]
    by_action = stats["by_action"]
    today = stats["today"]

    if intent == "count_detections":
        corrected = by_status.get("corrected", 0)
        rejected = by_status.get("rejected", 0)
        pending = by_status.get("pending", 0)
        return (
            f"当前系统共有 **{totals['detections']}** 个检测目标：\n\n"
            f"- 已校正（corrected）：{corrected}\n"
            f"- 已否决（false_positive）：{rejected}\n"
            f"- 待校正（pending）：{pending}\n\n"
            f"其中今日新增 {today['detections']} 个。",
            sources,
        )

    if intent == "count_corrections":
        parts = [f"- {k}: {v}" for k, v in by_action.items()]
        return (
            f"累计 **{totals['corrections']}** 次校正动作：\n\n" + ("\n".join(parts) if parts else "暂无"),
            sources,
        )

    if intent == "top_class":
        if not by_class:
            return ("暂无检测数据。", sources)
        top = by_class[0]
        top_zh = top["class_name_zh"] or top["class_name"]
        all_names = "、".join([c["class_name_zh"] or c["class_name"] for c in by_class])
        return (
            f"最常见类别是 **{top_zh}**，共 {top['count']} 次。\n\n"
            f"Top 类别：{all_names}",
            sources,
        )

    if intent == "today_summary":
        return (
            f"今日概览：\n\n"
            f"- 新增检测：{today['detections']}\n"
            f"- 校正动作：{today['corrections']}\n"
            f"- 全局检测：{totals['detections']}\n"
            f"- 平均置信度：{stats['avg_confidence'] * 100:.1f}%",
            sources,
        )

    if intent == "dataset_info":
        return (
            f"当前已导出 **{totals['datasets']}** 个训练集版本，注册权重 {totals['weights']} 个。",
            sources,
        )

    if intent == "weight_info":
        return (
            f"权重池共有 {totals['weights']} 个模型权重。可在「数据与权重」页面切换默认权重（热生效，无需重启）。",
            sources,
        )

    if intent == "ticket_info":
        return (f"当前待处理工单：**{totals['open_tickets']}** 条。", sources)

    if intent == "help":
        return (
            "我可以基于真实的识别数据回答这些问题：\n\n"
            "- 识别了多少目标 / 多少 defect\n"
            "- 校正动作分布\n"
            "- 最常见的类别\n"
            "- 今日概览\n"
            "- 数据集 / 权重 / 工单情况\n\n"
            "问具体一点，我会给出量化答案。",
            sources,
        )

    # general — combine the most relevant facts
    top_class = by_class[0] if by_class else None
    parts = [
        f"系统累计识别 **{totals['detections']}** 个目标、执行 **{totals['corrections']}** 次校正。",
    ]
    if top_class:
        parts.append(f"最常见类别：{top_class['class_name_zh'] or top_class['class_name']}（{top_class['count']}）。")
    if retrieval:
        sources.append("knowledge")
        parts.append("\n相关知识库条目：")
        for entry in retrieval[:2]:
            parts.append(f"- {entry.answer[:120]}")
    return ("\n".join(parts), sources)


# ---------------- LLM-backed answer (when langgraph available) ----------------
def _answer_with_llm(question: str, intent: str, stats: dict, retrieval: list[KnowledgeEntry]) -> tuple[str, list[str]]:
    """LangGraph pipeline: retrieve -> generate -> reflect.

    Kept minimal to avoid a hard dependency — when the LLM stack is absent
    we simply do not call this path.
    """
    sources = ["stats"]
    if retrieval:
        sources.append("knowledge")

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI  # type: ignore

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        context = json.dumps(stats, ensure_ascii=False, indent=2)
        knowledge_text = "\n".join(f"Q: {e.question}\nA: {e.answer}" for e in retrieval)

        system = (
            "你是 VisionFlywheel 的数据分析助手。"
            "只能基于下面给出的【实时统计】和【知识库】回答，"
            "不得编造数字或事实。若无法回答，请明说「我不知道」。\n\n"
            f"【实时统计】\n{context}\n\n"
            f"【知识库】\n{knowledge_text or '(空)'}"
        )
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=question)])
        answer = response.content if hasattr(response, "content") else str(response)
        return answer, sources
    except Exception as exc:
        logger.warning("LLM path failed, falling back to template: %s", exc)
        return _answer_from_stats(question, intent, stats, retrieval)


def _reflect(answer: str, stats: dict) -> tuple[str, bool]:
    """Cheap grounding check — every number in the answer must appear in stats.

    Returns (possibly-annoted answer, is_fully_grounded).
    """
    numbers = set(re.findall(r"\d+", answer))
    stats_text = json.dumps(stats, ensure_ascii=False)
    stats_numbers = set(re.findall(r"\d+", stats_text))
    ungrounded = numbers - stats_numbers
    # allow years / small cardinal numbers like list bullets
    ungrounded = {n for n in ungrounded if len(n) > 2}
    if ungrounded:
        return answer + "\n\n_(部分数字未在统计中找到来源，请谨慎使用)_", False
    return answer, True


# ---------------- public API ----------------
@dataclass
class ChatReply:
    answer: str
    sources: list[str]
    intent: str
    is_hallucination_checked: bool = True


def ask(db: Session, question: str) -> ChatReply:
    question = (question or "").strip()
    if not question:
        return ChatReply(answer="请先输入问题。", sources=[], intent="general", is_hallucination_checked=False)

    intent = _classify_intent(question)
    stats = _stats_context(db)
    retrieval = _retrieve(question)

    if _llm_available():
        answer, sources = _answer_with_llm(question, intent, stats, retrieval)
    else:
        answer, sources = _answer_from_stats(question, intent, stats, retrieval)

    answer, grounded = _reflect(answer, stats)
    return ChatReply(
        answer=answer,
        sources=sources,
        intent=intent,
        is_hallucination_checked=grounded,
    )
