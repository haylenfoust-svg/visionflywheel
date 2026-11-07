"""Dataset export / Weights / Training endpoints (docs/API.md §6-8)."""

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import AdminUser, CurrentUser
from app.core.envelope import EnvelopeRoute
from app.core.exceptions import AppError, Err
from app.schemas.common import Page
from app.schemas.dataset import (
    DatasetExportOut,
    DatasetExportRequest,
    DatasetExportRow,
    DatasetPendingOut,
    DatasetSampleOut,
    TrainRequest,
    TrainRunDetail,
    TrainRunOut,
    WeightHotSwapOut,
    WeightOut,
)
from app.services import dataset_exporter, train_service, weight_manager

router = APIRouter(tags=["dataset"], route_class=EnvelopeRoute)


# ---------- Dataset ----------
@router.get("/dataset/pending", response_model=DatasetPendingOut)
def dataset_pending(_: AdminUser, db: Session = Depends(get_db)) -> DatasetPendingOut:
    return DatasetPendingOut(**dataset_exporter.pending_count(db))


@router.post("/dataset/export", response_model=DatasetExportOut, status_code=201)
def dataset_export(
    payload: DatasetExportRequest,
    admin: AdminUser,
    db: Session = Depends(get_db),
) -> DatasetExportOut:
    result = dataset_exporter.export_dataset(
        db,
        name=payload.name,
        val_ratio=payload.val_ratio,
        include_rejected=payload.include_rejected,
        seed=payload.seed,
        operator=admin.username,
    )
    return DatasetExportOut(**result)


@router.get("/dataset", response_model=Page[DatasetExportRow])
def dataset_list(
    _: AdminUser,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[DatasetExportRow]:
    payload = dataset_exporter.list_exports(db, page=page, page_size=page_size)
    return Page[DatasetExportRow](
        items=[DatasetExportRow.model_validate(r) for r in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        pages=payload["pages"],
    )


@router.get("/dataset/holdout", response_model=Page[DatasetSampleOut])
def dataset_holdout(
    _: AdminUser,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[DatasetSampleOut]:
    payload = dataset_exporter.holdout_list(db, page=page, page_size=page_size)
    return Page[DatasetSampleOut](
        items=[DatasetSampleOut.model_validate(r) for r in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        pages=payload["pages"],
    )


@router.get("/dataset/{dataset_version}", response_model=DatasetExportRow)
def dataset_detail(dataset_version: str, _: AdminUser, db: Session = Depends(get_db)) -> DatasetExportRow:
    return DatasetExportRow.model_validate(dataset_exporter.get_export(db, dataset_version))


@router.get("/dataset/{dataset_version}/download")
def dataset_download(dataset_version: str, _: AdminUser, db: Session = Depends(get_db)) -> StreamingResponse:
    export = dataset_exporter.get_export(db, dataset_version)
    settings = get_settings()
    runtime_root = Path(settings.upload_dir).parent.resolve()
    root = runtime_root / export.path
    if not root.is_dir():
        raise AppError(Err.NOT_FOUND, f"dataset directory missing: {export.path}", 404)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())
    buffer.seek(0)
    filename = f"{dataset_version}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Weights ----------
@router.get("/weights", response_model=list[WeightOut])
def weights_list(user: CurrentUser, db: Session = Depends(get_db)) -> list[WeightOut]:
    weight_manager.scan_weights_dir(db)
    return [WeightOut.model_validate(w) for w in weight_manager.list_weights(db)]


@router.post("/weights/upload", response_model=WeightOut, status_code=201)
def weights_upload(
    admin: AdminUser,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    note: str | None = None,
) -> WeightOut:
    if not file.filename:
        raise AppError(Err.VALIDATION, "filename is required", 400)
    data = file.read()
    row = weight_manager.upload_weight(db, filename=file.filename, content=data, operator=admin.username, note=note)
    return WeightOut.model_validate(row)


@router.get("/weights/{weight_id}", response_model=WeightOut)
def weights_detail(weight_id: int, user: CurrentUser, db: Session = Depends(get_db)) -> WeightOut:
    return WeightOut.model_validate(weight_manager.get_weight(db, weight_id))


@router.put("/weights/{weight_id}/default", response_model=WeightHotSwapOut)
def weights_set_default(weight_id: int, admin: AdminUser, db: Session = Depends(get_db)) -> WeightHotSwapOut:
    return WeightHotSwapOut(**weight_manager.set_default(db, weight_id, operator=admin.username))


@router.delete("/weights/{weight_id}", status_code=204)
def weights_delete(weight_id: int, admin: AdminUser, db: Session = Depends(get_db)) -> None:
    weight_manager.delete_weight(db, weight_id)


# ---------- Training ----------
@router.post("/train", response_model=TrainRunOut, status_code=202)
def train_start(payload: TrainRequest, admin: AdminUser, db: Session = Depends(get_db)) -> TrainRunOut:
    run = train_service.create_training(
        db,
        dataset_version=payload.dataset_version,
        base_weight=payload.base_weight,
        epochs=payload.epochs,
        imgsz=payload.imgsz,
        batch=payload.batch,
        name=payload.name,
        operator=admin.username,
    )
    return TrainRunOut.model_validate(run)


@router.get("/train", response_model=Page[TrainRunOut])
def train_list(
    _: AdminUser,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[TrainRunOut]:
    payload = train_service.list_runs(db, page=page, page_size=page_size)
    return Page[TrainRunOut](
        items=[TrainRunOut.model_validate(r) for r in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        pages=payload["pages"],
    )


@router.get("/train/{run_id}", response_model=TrainRunDetail)
def train_detail(run_id: int, _: AdminUser, db: Session = Depends(get_db)) -> TrainRunDetail:
    return TrainRunDetail.model_validate(train_service.get_run(db, run_id))


@router.post("/train/{run_id}/cancel", response_model=TrainRunOut)
def train_cancel(run_id: int, admin: AdminUser, db: Session = Depends(get_db)) -> TrainRunOut:
    return TrainRunOut.model_validate(train_service.cancel_run(db, run_id))
