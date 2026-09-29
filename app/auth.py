import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import ApiError
from app.models import User

USERNAME_PATTERN = re.compile(r"[a-z0-9_]{3,30}")
TOKEN_LIFETIME = timedelta(days=7)

password_hasher = PasswordHasher()


def normalise_username(raw):
    return raw.strip().lower()


def is_valid_username(username):
    return USERNAME_PATTERN.fullmatch(username) is not None


def hash_password(password):
    return password_hasher.hash(password)


def verify_password(password_hash, password):
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id, username):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + TOKEN_LIFETIME,
    }

    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.PyJWTError:
        return None


def bearer_token(authorization):
    if authorization is None or not authorization.startswith("Bearer "):
        return None

    return authorization.removeprefix("Bearer ")


def user_from_header(authorization, db):
    token = bearer_token(authorization)
    if token is None:
        return None

    claims = decode_token(token)
    if claims is None:
        return None

    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError:
        return None

    return db.get(User, user_id)


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = user_from_header(authorization, db)
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Please log in again")

    return user
