from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


#  users

class UserCreate(BaseModel):
    username: str
    email:    str
    password: str            # plain text in, hashed before it ever touches the DB
    role:     str = "operator"

    @field_validator("role")
    def role_must_be_valid(cls, v):
        allowed = {"operator", "inspector", "manager"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(allowed)}")
        return v


class UserResponse(BaseModel):
   
    id:         int
    username:   str
    email:      str
    role:       str
    is_active:  bool
    created_at: datetime

    class Config:
        from_attributes = True  # lets us build this straight from a SQLAlchemy row


class UserSummary(BaseModel):
   
    id:       int
    username: str
    role:     str

    class Config:
        from_attributes = True


#  auth 

class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type:   str
    user:         UserResponse  # send the user back too, saves the frontend a round trip


# images 

class DetectionResultResponse(BaseModel):
    is_defective:     bool
    confidence_score: float
    model_version:    str
    processed_at:     datetime

    class Config:
        from_attributes = True


class ReviewResponse(BaseModel):
    id:          int
    decision:    str
    notes:       Optional[str]
    reviewed_at: datetime
    reviewer:    UserSummary

    class Config:
        from_attributes = True


class ImageResponse(BaseModel):
    id:                int
    original_filename: str
    saved_filename:    str
    file_size_bytes:   Optional[int]
    status:            str
    uploaded_at:       datetime
    uploader:          UserSummary
    detection_result:  Optional[DetectionResultResponse]  # None until the model's run
    review:            Optional[ReviewResponse]            # None until a human's reviewed it

    class Config:
        from_attributes = True


class ImageListResponse(BaseModel):
    total:  int
    images: list[ImageResponse]


#  reviews 

class ReviewCreate(BaseModel):
    decision: str
    notes:    Optional[str] = None

    @field_validator("decision")
    def decision_must_be_valid(cls, v):
        allowed = {"confirmed_defective", "cleared"}
        if v not in allowed:
            raise ValueError(f"Decision must be one of: {', '.join(allowed)}")
        return v


#  stats (managers only) 

class StatsResponse(BaseModel):
    total_images:          int
    pending_count:         int
    processing_count:      int
    awaiting_review_count: int
    reviewed_count:        int
    failed_count:          int
    defect_rate_percent:   float
    ai_accuracy_percent:   float
    total_users:           int


# profile self-service 

class UpdateProfile(BaseModel):
    
    username: Optional[str] = None
    email:    Optional[str] = None

    @field_validator("username")
    def username_not_empty(cls, v):
        if v is not None and len(v.strip()) < 3:
            raise ValueError("Username must be at least 3 characters.")
        return v.strip() if v else v


class ChangePassword(BaseModel):
    old_password: str   
    new_password: str

    @field_validator("new_password")
    def password_long_enough(cls, v):
        if len(v) < 6:
            raise ValueError("New password must be at least 6 characters.")
        return v


#  admin / user management 

class AdminUpdateUser(BaseModel):
    """A manager editing someone else's account — both fields optional, only sent ones apply."""
    role:      Optional[str]  = None
    is_active: Optional[bool] = None

    @field_validator("role")
    def role_must_be_valid(cls, v):
        if v is not None:
            allowed = {"operator", "inspector", "manager"}
            if v not in allowed:
                raise ValueError(f"Role must be one of: {', '.join(allowed)}")
        return v


class AdminResetPassword(BaseModel):
   
    new_password: str

    @field_validator("new_password")
    def password_long_enough(cls, v):
        if len(v) < 6:
            raise ValueError("New password must be at least 6 characters.")
        return v


class UserListResponse(BaseModel):
    total: int
    users: list[UserResponse]
