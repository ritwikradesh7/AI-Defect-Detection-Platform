# Login, registration, profile self-service, and (for managers) the user
# management endpoints.

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import hash_password, verify_password, create_access_token, get_current_user, require_role
from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """Anyone can create an account. Role upgrades after that go through a manager."""
    if db.query(models.User).filter(models.User.username == user_data.username).first():
        raise HTTPException(400, detail=f"Username '{user_data.username}' is already taken.")
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(400, detail=f"Email '{user_data.email}' is already registered.")

    new_user = models.User(
        username        = user_data.username,
        email           = user_data.email,
        hashed_password = hash_password(user_data.password),
        role            = user_data.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=schemas.Token)
def login(login_data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == login_data.username).first()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(401, detail="Incorrect username or password.")
    if not user.is_active:
        raise HTTPException(403, detail="This account has been deactivated. Contact your manager.")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserResponse)
def update_me(
    updates: schemas.UpdateProfile,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update your own username and/or email. At least one of them has to be set."""
    if updates.username is None and updates.email is None:
        raise HTTPException(400, detail="Provide at least one field to update.")

    if updates.username and updates.username != current_user.username:
        if db.query(models.User).filter(models.User.username == updates.username).first():
            raise HTTPException(400, detail=f"Username '{updates.username}' is already taken.")
        current_user.username = updates.username

    if updates.email and updates.email != current_user.email:
        if db.query(models.User).filter(models.User.email == updates.email).first():
            raise HTTPException(400, detail=f"Email '{updates.email}' is already in use.")
        current_user.email = updates.email

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/password", status_code=200)
def change_password(
    payload: schemas.ChangePassword,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Have to get the current password right before we'll set a new one."""
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(400, detail="Current password is incorrect.")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password changed successfully."}


@router.get("/users", response_model=schemas.UserListResponse)
def list_all_users(
    current_user: models.User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
):
    """Manager-only — every account, with current role and active/disabled status."""
    users = db.query(models.User).order_by(models.User.created_at).all()
    return {"total": len(users), "users": users}


@router.patch("/users/{user_id}", response_model=schemas.UserResponse)
def admin_update_user(
    user_id: int,
    updates: schemas.AdminUpdateUser,
    current_user: models.User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
):
    
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, detail="User not found.")

    if target.id == current_user.id and updates.is_active is False:
        raise HTTPException(400, detail="You cannot deactivate your own account.")

    if updates.role is not None:
        target.role = updates.role
    if updates.is_active is not None:
        target.is_active = updates.is_active

    db.commit()
    db.refresh(target)
    return target


@router.post("/users/{user_id}/reset-password", status_code=200)
def admin_reset_password(
    user_id: int,
    payload: schemas.AdminResetPassword,
    current_user: models.User = Depends(require_role("manager")),
    db: Session = Depends(get_db)
):
    
    if user_id == current_user.id:
        raise HTTPException(
            400,
            detail="Use the 'Change Password' option in your own Account "
                   "Settings instead — this endpoint is for resetting other people's passwords."
        )

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, detail="User not found.")

    target.hashed_password = hash_password(payload.new_password)
    db.commit()

    logger.info(f"manager '{current_user.username}' reset the password for '{target.username}'")

    return {"message": f"Password for '{target.username}' has been reset."}
