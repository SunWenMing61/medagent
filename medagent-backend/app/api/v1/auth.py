from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token
from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, AuthMeResponse
from app.schemas.common import MessageResponse

router = APIRouter()


@router.post("/register", response_model=MessageResponse)
def register(req: RegisterRequest, db: Session = Depends(get_mysql_db)):
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        email=req.email or "",
        role="user",
        status=1,
    )
    db.add(user)
    db.commit()
    return {"message": "Registration successful"}


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_mysql_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.status != 1:
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=AuthMeResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return AuthMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email or "",
        role=current_user.role,
        status=current_user.status,
    )
