import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.auth import (
    bearer_token,
    create_token,
    decode_token,
    hash_password,
    is_valid_username,
    normalise_username,
    verify_password,
)
from app.config import settings


def signed_token(claims, secret):
    return jwt.encode(claims, secret, algorithm="HS256")


def test_normalise_username():
    assert normalise_username("  Rupinder_01 ") == "rupinder_01"


def test_valid_usernames():
    assert is_valid_username("abc")
    assert is_valid_username("rupinder_01")
    assert is_valid_username("a" * 30)


def test_invalid_usernames():
    assert not is_valid_username("ab")
    assert not is_valid_username("a" * 31)
    assert not is_valid_username("rupinder singh")
    assert not is_valid_username("rupinder-singh")
    assert not is_valid_username("Rupinder")
    assert not is_valid_username("rupinder\n")


def test_password_hash_verifies():
    password_hash = hash_password("correct horse")

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct horse")
    assert not verify_password(password_hash, "wrong horse")


def test_verify_password_with_broken_hash():
    assert not verify_password("not-a-hash", "anything")


def test_token_round_trip():
    user_id = uuid.uuid4()

    claims = decode_token(create_token(user_id, "rupinder"))

    assert claims["sub"] == str(user_id)
    assert claims["username"] == "rupinder"
    assert claims["exp"] - claims["iat"] == 7 * 24 * 60 * 60


def test_expired_token_is_rejected():
    now = datetime.now(timezone.utc)
    claims = {"sub": "user", "username": "u", "iat": now - timedelta(days=8), "exp": now - timedelta(days=1)}

    assert decode_token(signed_token(claims, settings.jwt_secret)) is None


def test_token_with_wrong_secret_is_rejected():
    now = datetime.now(timezone.utc)
    claims = {"sub": "user", "username": "u", "iat": now, "exp": now + timedelta(days=1)}

    assert decode_token(signed_token(claims, "some-other-secret-that-is-long-enough")) is None


def test_token_without_expiry_is_rejected():
    claims = {"sub": "user", "username": "u", "iat": datetime.now(timezone.utc)}

    assert decode_token(signed_token(claims, settings.jwt_secret)) is None


def test_garbage_token_is_rejected():
    assert decode_token("not-a-token") is None


def test_bearer_token():
    assert bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"
    assert bearer_token("abc.def.ghi") is None
    assert bearer_token(None) is None
