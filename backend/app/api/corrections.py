"""Correction + Feedback endpoints (docs/API.md §4-5, PRD FR-3 FR-4)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.schemas.common import Page
from app.schemas.correction import (
    CorrectionBatchRequest,
    CorrectionCreate,
    CorrectionOut,
    CorrectionResult,
    FeedbackCreate,
    FeedbackOut,
    FeedbackReply,
    FeedbackStatusUpdate,
    UndoRequest,
)
from app.services import correction_service, feedback_service

router = APIRouter(tags=["corrections"], route_class=EnvelopeRoute)


# ---------- Corrections ----------
@router.post("/corrections", response_model=CorrectionResult)
def create_correction(
    payload: CorrectionCreate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> CorrectionResult:
    try:
        row = correction_service.apply_correction(db, payload, operator=user.username)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(Err.INTERNAL, f"correction failed: {exc}", 500) from exc

    from app.models.detection import Detection

    det = db.query(Detection).filter(Detection.id == row.detection_id).first() if row.detection_id else None
    return CorrectionResult(
        correction_id=row.id,
        detection_id=row.detection_id,
        action=row.action,
        old_value=row.old_value,
        new_value=row.new_value,
        detection_status=det.status if det else None,
        created_at=row.created_at,
    )


@router.post("/corrections/batch", response_model=list[CorrectionResult])
def create_batch(
    payload: CorrectionBatchRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[CorrectionResult]:
    from app.schemas.correction import CorrectionCreate

    out: list[CorrectionResult] = []
    for item in payload.items:
        row = correction_service.apply_correction(
            db,
            CorrectionCreate(
                action=item.action,
                detection_id=item.detection_id,
                task_id=item.task_id,
                new_class_name=item.new_class_name,
                new_bbox=item.new_bbox,
                comment=item.comment,
            ),
            operator=user.username,
        )
        from app.models.detection import Detection

        det = db.query(Detection).filter(Detection.id == row.detection_id).first() if row.detection_id else None
        out.append(
            CorrectionResult(
                correction_id=row.id,
                detection_id=row.detection_id,
                action=row.action,
                old_value=row.old_value,
                new_value=row.new_value,
                detection_status=det.status if det else None,
                created_at=row.created_at,
            )
        )
    return out


@router.post("/corrections/undo", response_model=CorrectionResult)
def undo(
    payload: UndoRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> CorrectionResult:
    row = correction_service.undo_correction(
        db, target_id=payload.correction_id, operator=user.username
    )
    from app.models.detection import Detection

    det = db.query(Detection).filter(Detection.id == row.detection_id).first() if row.detection_id else None
    return CorrectionResult(
        correction_id=row.id,
        detection_id=row.detection_id,
        action=row.action,
        old_value=row.old_value,
        new_value=row.new_value,
        detection_status=det.status if det else None,
        created_at=row.created_at,
    )


@router.get("/corrections/audit", response_model=Page[CorrectionOut])
def audit(
    user: CurrentUser,
    db: Session = Depends(get_db),
    task_id: int | None = Query(default=None),
    detection_id: int | None = Query(default=None),
    operator: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[CorrectionOut]:
    payload = correction_service.list_corrections(
        db,
        task_id=task_id,
        detection_id=detection_id,
        operator=operator,
        page=page,
        page_size=page_size,
    )
    return Page[CorrectionOut](
        items=[CorrectionOut.model_validate(r) for r in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        pages=payload["pages"],
    )


# Enforce FR-3.7: corrections are append-only
def _forbidden_mutate(correction_id: int):
    raise AppError(Err.AUDIT_IMMUTABLE, "corrections are append-only", 403)


for _method in ("PUT", "PATCH", "DELETE"):
    router.add_api_route(
        "/corrections/{correction_id}",
        _forbidden_mutate,
        methods=[_method],
        include_in_schema=False,
    )


# ---------- Feedback ----------
@router.post("/feedback", response_model=FeedbackOut, status_code=201)
def create_feedback(
    payload: FeedbackCreate,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> FeedbackOut:
    ticket = feedback_service.create_ticket(
        db,
        content=payload.content,
        username=user.username,
        user_id=user.id,
        detection_id=payload.detection_id,
        task_id=payload.task_id,
    )
    return FeedbackOut.model_validate(ticket)


@router.get("/feedback", response_model=Page[FeedbackOut])
def list_feedback(
    user: CurrentUser,
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    mine: bool = Query(default=False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[FeedbackOut]:
    payload = feedback_service.list_tickets(
        db,
        status=status,
        username=user.username,
        only_mine=mine or user.role != "admin",
        page=page,
        page_size=page_size,
    )
    return Page[FeedbackOut](
        items=[FeedbackOut.model_validate(r) for r in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        pages=payload["pages"],
    )


@router.put("/feedback/{ticket_id}/reply", response_model=FeedbackOut)
def reply_feedback(
    ticket_id: int,
    payload: FeedbackReply,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> FeedbackOut:
    ticket = feedback_service.reply(db, ticket_id, reply_text=payload.reply, admin_username=admin.username)
    return FeedbackOut.model_validate(ticket)


@router.put("/feedback/{ticket_id}/status", response_model=FeedbackOut)
def update_feedback_status(
    ticket_id: int,
    payload: FeedbackStatusUpdate,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> FeedbackOut:
    ticket = feedback_service.update_status(db, ticket_id, payload.status, admin_username=admin.username)
    return FeedbackOut.model_validate(ticket)
