"""Feedback ticket service (PRD FR-4)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, Err
from app.models.feedback import FeedbackTicket

ALLOWED_STATUSES = ("open", "replied", "resolved", "rejected")


def create_ticket(
    db: Session,
    *,
    content: str,
    username: str | None = None,
    user_id: int | None = None,
    detection_id: int | None = None,
    task_id: int | None = None,
) -> FeedbackTicket:
    if not content.strip():
        raise AppError(Err.VALIDATION, "content is required", 400)
    ticket = FeedbackTicket(
        content=content.strip(),
        username=username,
        user_id=user_id,
        detection_id=detection_id,
        task_id=task_id,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def list_tickets(
    db: Session,
    *,
    status: str | None = None,
    username: str | None = None,
    only_mine: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    q = db.query(FeedbackTicket)
    if status:
        q = q.filter(FeedbackTicket.status == status)
    if only_mine and username:
        q = q.filter(FeedbackTicket.username == username)
    total = q.count()
    rows = (
        q.order_by(FeedbackTicket.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    )
    pages = (total + page_size - 1) // page_size if total else 0
    return {"items": rows, "total": total, "page": page, "page_size": page_size, "pages": pages}


def get_ticket(db: Session, ticket_id: int) -> FeedbackTicket:
    ticket = db.query(FeedbackTicket).filter(FeedbackTicket.id == ticket_id).first()
    if ticket is None:
        raise AppError(Err.NOT_FOUND, f"ticket not found: {ticket_id}", 404)
    return ticket


def reply(db: Session, ticket_id: int, *, reply_text: str, admin_username: str | None = None) -> FeedbackTicket:
    ticket = get_ticket(db, ticket_id)
    if not reply_text.strip():
        raise AppError(Err.VALIDATION, "reply is required", 400)
    ticket.reply = reply_text.strip()
    ticket.replied_by = admin_username
    ticket.status = "replied"
    db.commit()
    db.refresh(ticket)
    return ticket


def update_status(db: Session, ticket_id: int, status: str, *, admin_username: str | None = None) -> FeedbackTicket:
    if status not in ALLOWED_STATUSES:
        raise AppError(Err.VALIDATION, f"invalid status: {status}", 400)
    ticket = get_ticket(db, ticket_id)
    ticket.status = status
    if status in ("resolved", "rejected") and admin_username and not ticket.replied_by:
        ticket.replied_by = admin_username
    db.commit()
    db.refresh(ticket)
    return ticket
