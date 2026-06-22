import logging

from .celery_app import celery_app
from .database import SessionLocal
from . import models
from .services.vision_model import model as vision_model

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.run_detection")
def run_detection(image_id: int, filepath: str):
    
    db = SessionLocal()

    try:
        image = db.query(models.Image).filter(models.Image.id == image_id).first()
        if not image:
           
            logger.error(f"run_detection: image {image_id} not found, skipping")
            return

        image.status = "processing"
        db.commit()

        result = vision_model.predict(filepath)

        detection = models.DetectionResult(
            image_id=image_id,
            is_defective=result["is_defective"],
            confidence_score=result["confidence"],
            model_version=result.get("model_version", "v1.0"),
        )
        db.add(detection)
        image.status = "awaiting_review"
        db.commit()

        logger.info(
            f"image {image_id} processed — defective={result['is_defective']} "
            f"confidence={result['confidence']:.1%} model={result.get('model_version')}"
        )

    except Exception as exc:
        logger.exception(f"detection failed for image {image_id}")
        db.rollback()
        try:
            image = db.query(models.Image).filter(models.Image.id == image_id).first()
            if image:
                image.status = "failed"
                db.add(models.DetectionResult(
                    image_id=image_id,
                    is_defective=False,
                    confidence_score=0.0,
                    error_message=str(exc),
                ))
                db.commit()
        except Exception:
            logger.exception(f"couldn't even mark image {image_id} as failed — giving up")
       
    finally:
        db.close()
