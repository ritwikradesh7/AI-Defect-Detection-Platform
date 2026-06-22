# structure to track an image from upload through AI processing through human sign-off, with a full history of who did what.

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class User(Base):
    """
    Three roles:
      operator   — uploads images, can only see their own
      inspector  — works the review queue, confirms or clears flagged images
      manager    — everything above plus stats, user management, all-images view
    """
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, index=True)
    username         = Column(String, unique=True, index=True, nullable=False)
    email            = Column(String, unique=True, index=True, nullable=False)
    hashed_password  = Column(String, nullable=False)  
    role             = Column(String, default="operator")
    is_active        = Column(Boolean, default=True)   # flip to False to lock someone out
    created_at       = Column(DateTime, server_default=func.now())

    uploaded_images = relationship(
        "Image",
        back_populates="uploader",
        foreign_keys="Image.uploaded_by_id"
    )
    reviews = relationship("Review", back_populates="reviewer")


class Image(Base):

    __tablename__ = "images"

    id                = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)    # whatever the uploader named it
    saved_filename    = Column(String, nullable=False)    # the UUID name it's actually stored under
    filepath          = Column(String, nullable=False)
    file_size_bytes   = Column(Integer)
    status            = Column(String, default="pending")
    uploaded_by_id    = Column(Integer, ForeignKey("users.id"))
    uploaded_at       = Column(DateTime, server_default=func.now())

    uploader         = relationship("User", back_populates="uploaded_images", foreign_keys=[uploaded_by_id])
    detection_result = relationship("DetectionResult", back_populates="image", uselist=False)
    review           = relationship("Review", back_populates="image", uselist=False)


class DetectionResult(Base):
    
    __tablename__ = "detection_results"

    id               = Column(Integer, primary_key=True, index=True)
    image_id         = Column(Integer, ForeignKey("images.id"), unique=True)
    is_defective     = Column(Boolean, nullable=False)
    confidence_score = Column(Float, nullable=False)   
    model_version    = Column(String, default="v1.0")  
    error_message    = Column(String, nullable=True)   
    processed_at     = Column(DateTime, server_default=func.now())

    image = relationship("Image", back_populates="detection_result")


class Review(Base):
    __tablename__ = "reviews"

    id           = Column(Integer, primary_key=True, index=True)
    image_id     = Column(Integer, ForeignKey("images.id"), unique=True)
    reviewer_id  = Column(Integer, ForeignKey("users.id"))
    decision     = Column(String, nullable=False)
    notes        = Column(String, nullable=True)
    reviewed_at  = Column(DateTime, server_default=func.now())

    image    = relationship("Image", back_populates="review")
    reviewer = relationship("User", back_populates="reviews")
