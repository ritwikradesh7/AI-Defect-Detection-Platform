# Endpoints:
#   GET  /api/reviews/queue   — images waiting for human review (inspectors, managers)
#   POST /api/reviews/{id}    — submit a review decision (inspectors, managers)
#   GET  /api/reviews/history — completed reviews (inspectors, managers)
#   GET  /api/reviews/stats   — dashboard numbers (managers only)

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..auth import get_current_user, require_role
from ..database import get_db
from ..services.vision_model import model as vision_model

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/queue",
    response_model=schemas.ImageListResponse,
    summary="Get images that are waiting for human review"
)
def get_review_queue(
    limit: int  = 50,
    offset: int = 0,
    current_user: models.User = Depends(require_role("inspector", "manager")),
    db: Session = Depends(get_db)
):
    query = (
        db.query(models.Image)
        .filter(models.Image.status == "awaiting_review")
        .order_by(models.Image.uploaded_at.asc())  # oldest first, FIFO
    )

    total  = query.count()
    images = query.offset(offset).limit(min(limit, 100)).all()

    return {"total": total, "images": images}


@router.post(
    "/{image_id}",
    response_model=schemas.ImageResponse,
    summary="Submit a review decision for an image"
)
def submit_review(
    image_id: int,
    review_data: schemas.ReviewCreate,
    current_user: models.User = Depends(require_role("inspector", "manager")),
    db: Session = Depends(get_db)
):

    image = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail=f"Image #{image_id} not found.")

    if image.status != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This image cannot be reviewed. Current status: '{image.status}'. "
                   f"Only images with status 'awaiting_review' can be reviewed."
        )

    existing_review = db.query(models.Review).filter(
        models.Review.image_id == image_id
    ).first()
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Image #{image_id} has already been reviewed by "
                   f"'{existing_review.reviewer.username}'."
        )

    new_review = models.Review(
        image_id    = image_id,
        reviewer_id = current_user.id,
        decision    = review_data.decision,
        notes       = review_data.notes,
    )
    db.add(new_review)
    image.status = "reviewed"

    db.commit()
    db.refresh(image)

    if review_data.decision == "cleared":
        try:
            vision_model.register_known_good(image.filepath)
        except Exception:
            logger.exception(f"couldn't update reference profile for image {image_id} (non-fatal)")

    verdict = "confirmed defective" if review_data.decision == "confirmed_defective" else "cleared"
    logger.info(
        f"image {image_id} reviewed by {current_user.username}: {verdict}"
        + (f" — notes: {review_data.notes}" if review_data.notes else "")
    )

    return image


@router.get(
    "/history",
    response_model=schemas.ImageListResponse,
    summary="Get all completed reviews"
)
def get_review_history(
    limit:  int = 50,
    offset: int = 0,
    current_user: models.User = Depends(require_role("inspector", "manager")),
    db: Session = Depends(get_db)
):
    """Every image that's been through a full review — the AI verdict and the human call, side by side."""
    query = (
        db.query(models.Image)
        .filter(models.Image.status == "reviewed")
        .order_by(models.Image.uploaded_at.desc())
    )

    total  = query.count()
    images = query.offset(offset).limit(min(limit, 100)).all()

    return {"total": total, "images": images}


@router.get(
    "/stats",
    response_model=schemas.StatsResponse,
    summary="Get platform-wide statistics (managers only)"
)
def get_stats(
    current_user: models.User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
):
    """Counts, defect rate, and AI/human agreement rate for the manager dashboard."""

    all_images       = db.query(models.Image).count()
    pending_count    = db.query(models.Image).filter(models.Image.status == "pending").count()
    processing_count = db.query(models.Image).filter(models.Image.status == "processing").count()
    awaiting_count   = db.query(models.Image).filter(models.Image.status == "awaiting_review").count()
    reviewed_count   = db.query(models.Image).filter(models.Image.status == "reviewed").count()
    failed_count     = db.query(models.Image).filter(models.Image.status == "failed").count()
    total_reviewed = db.query(models.Review).count()
    confirmed_defective = db.query(models.Review).filter(
        models.Review.decision == "confirmed_defective"
    ).count()
    defect_rate = (confirmed_defective / total_reviewed * 100) if total_reviewed > 0 else 0.0

    reviews_with_results = (
        db.query(models.Review, models.DetectionResult)
        .join(models.Image, models.Review.image_id == models.Image.id)
        .join(models.DetectionResult, models.DetectionResult.image_id == models.Image.id)
        .all()
    )

    if reviews_with_results:
        agreements = sum(
            1 for review, detection in reviews_with_results
            if (detection.is_defective and review.decision == "confirmed_defective")
            or (not detection.is_defective and review.decision == "cleared")
        )
        ai_accuracy = (agreements / len(reviews_with_results)) * 100
    else:
        ai_accuracy = 0.0

    total_users = db.query(models.User).count()

    return {
        "total_images":          all_images,
        "pending_count":         pending_count,
        "processing_count":      processing_count,
        "awaiting_review_count": awaiting_count,
        "reviewed_count":        reviewed_count,
        "failed_count":          failed_count,
        "defect_rate_percent":   round(defect_rate, 1),
        "ai_accuracy_percent":   round(ai_accuracy, 1),
        "total_users":           total_users,
    }
