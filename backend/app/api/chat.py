"""Chat / knowledge endpoints (docs/API.md §10, PRD FR-8)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.services import llm_service

router = APIRouter(tags=["chat"], route_class=EnvelopeRoute)


@router.post("/chat")
def chat(payload: dict, user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    question = (payload.get("question") or "").strip()
    if not question:
        raise AppError(Err.VALIDATION, "question is required", 400)
    if len(question) > 1000:
        raise AppError(Err.VALIDATION, "question too long (max 1000 chars)", 400)

    reply = llm_service.ask(db, question)
    return {
        "answer": reply.answer,
        "sources": reply.sources,
        "intent": reply.intent,
        "is_hallucination_checked": reply.is_hallucination_checked,
    }


@router.post("/chat/knowledge", status_code=201)
def add_knowledge(payload: dict, user: CurrentUser) -> dict:
    question = (payload.get("question") or "").strip()
    answer = (payload.get("answer") or "").strip()
    if not question or not answer:
        raise AppError(Err.VALIDATION, "question and answer are required", 400)
    return llm_service.add_knowledge(question, answer, source=user.username)


@router.get("/knowledge")
def list_knowledge(_: CurrentUser) -> list[dict]:
    return llm_service.list_knowledge()


@router.delete("/knowledge/{entry_id}", status_code=204)
def delete_knowledge(entry_id: int, _: AdminUser) -> None:
    if not llm_service.delete_knowledge(entry_id):
        raise AppError(Err.NOT_FOUND, f"knowledge entry not found: {entry_id}", 404)
