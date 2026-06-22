# app/routes/image_routes.py
#
# Endpoints:
#   POST /api/images/upload     — upload a new image (operators, managers)
#   GET  /api/images/           — list images (operators see their own, others see all)
#   GET  /api/images/{id}       — full details for one image
#   GET  /api/images/{id}/file  — the actual image bytes
#
# The detection work itself now happens in app/tasks.py via Celery — this
# file just saves the upload and hands off a job. See tasks.py for why we
# moved off FastAPI's BackgroundTasks.

import os
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, require_role
from ..database import get_db
from ..config import UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES
from ..tasks import run_detection

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/upload",
    response_model=schemas.ImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a production-line image for defect analysis"
)
async def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(require_role("operator", "manager")),
    db: Session = Depends(get_db)
):
    """
    Save the upload, create its DB record, queue the detection job, and
    respond right away — the caller doesn't wait around for the model to
    finish, they just poll (or refresh) for the result later.
    """

    # extension check first, it's the cheapest thing to reject on
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file_extension}' is not allowed. "
                   f"Accepted types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_contents = await file.read()
    file_size = len(file_contents)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large ({file_size / 1024 / 1024:.1f} MB). "
                   f"Maximum allowed: {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB"
        )
    if file_size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")

    # UUID filename — avoids collisions and stops anyone trying something
    # like a filename of "../../etc/passwd" from doing anything funny
    unique_name = f"{uuid.uuid4().hex}{file_extension}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)

    try:
        with open(save_path, "wb") as f:
            f.write(file_contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save the file: {str(e)}")

    new_image = models.Image(
        original_filename=file.filename,
        saved_filename=unique_name,
        filepath=save_path,
        file_size_bytes=file_size,
        status="pending",
        uploaded_by_id=current_user.id,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)

    # Hand this off to Celery and move on — .delay() just drops a message
    # on the Redis queue and returns immediately, it doesn't wait for a
    # worker to actually pick it up.
    #
    # If Redis itself is down, .delay() raises right here instead of
    # quietly queuing. Without this try/except that turns into a raw 500
    # and leaves the image stuck at "pending" forever with nothing ever
    # going to pick it up. Catching it lets us tell the uploader plainly
    # that the queue is unreachable, and mark the row "failed" instead of
    # leaving it in limbo.
    try:
        run_detection.delay(image_id=new_image.id, filepath=save_path)
    except Exception as e:
        logger.error(f"couldn't queue detection for image {new_image.id} — Redis unreachable? ({e})")
        new_image.status = "failed"
        db.add(models.DetectionResult(
            image_id=new_image.id,
            is_defective=False,
            confidence_score=0.0,
            error_message="Could not reach the task queue (Redis). Make sure Redis "
                           "and the Celery worker are running, then re-upload this image.",
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The image was saved, but couldn't be queued for analysis — the task "
                   "queue (Redis) doesn't seem reachable right now. Make sure Redis and "
                   "the Celery worker are running, then try uploading again."
        )

    logger.info(f"image {new_image.id} uploaded by {current_user.username}, queued for detection")

    return new_image


@router.get(
    "/",
    response_model=schemas.ImageListResponse,
    summary="List images (operators see their own; inspectors/managers see all)"
)
def list_images(
    status_filter: str = None,
    limit: int = 50,
    offset: int = 0,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(models.Image)

    if current_user.role == "operator":
        query = query.filter(models.Image.uploaded_by_id == current_user.id)

    if status_filter:
        query = query.filter(models.Image.status == status_filter)

    query = query.order_by(models.Image.uploaded_at.desc())
    total = query.count()

    limit = min(limit, 100)
    images = query.offset(offset).limit(limit).all()

    return {"total": total, "images": images}


@router.get(
    "/{image_id}",
    response_model=schemas.ImageResponse,
    summary="Get full details for one image"
)
def get_image(
    image_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail=f"Image #{image_id} not found.")

    if current_user.role == "operator" and image.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view your own images.")

    return image


@router.get("/{image_id}/file", summary="Download the raw image file")
def get_image_file(
    image_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail=f"Image #{image_id} not found.")

    if current_user.role == "operator" and image.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view your own images.")

    if not os.path.exists(image.filepath):
        raise HTTPException(status_code=404, detail="Image file not found on disk.")

    return FileResponse(
        path=image.filepath,
        filename=image.original_filename,
        media_type="image/jpeg"
    )
