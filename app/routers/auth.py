from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import create_token, current_user, hash_password, is_valid_username, normalise_username, verify_password
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.schemas import AuthResponse, Credentials, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def auth_response(user):
    return {
        "user": {"id": user.id, "username": user.username},
        "token": create_token(user.id, user.username),
    }


@router.post("/signup", status_code=201, response_model=AuthResponse)
def signup(credentials: Credentials, db: Session = Depends(get_db)):
    username = normalise_username(credentials.username)
    if not is_valid_username(username):
        raise ApiError(400, "BAD_REQUEST", "Username must be 3 to 30 letters, numbers or underscores")

    if len(credentials.password) < 8:
        raise ApiError(400, "BAD_REQUEST", "Password must be at least 8 characters")

    user = User(username=username, password_hash=hash_password(credentials.password))
    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "USERNAME_TAKEN", "That username is already taken")

    return auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(credentials: Credentials, db: Session = Depends(get_db)):
    username = normalise_username(credentials.username)
    user = db.scalar(select(User).where(User.username == username))

    if user is None or not verify_password(user.password_hash, credentials.password):
        raise ApiError(401, "INVALID_CREDENTIALS", "Wrong username or password")

    return auth_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username}
