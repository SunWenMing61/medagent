from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_profile(
    req: UserUpdateRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    if req.username:
        current_user.username = req.username
    if req.email:
        current_user.email = req.email
    db.commit()
    db.refresh(current_user)
    return current_user
