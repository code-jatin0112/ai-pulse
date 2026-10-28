import os
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .config import get_secret_key, TOKEN_HOURS
from .db import get_db
from . import models

BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt with a cryptographically secure random salt."""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def is_legacy_hash(hashed: str) -> bool:
    """Checks whether the hash is a legacy unsalted SHA-256 hex string."""
    if not hashed or not isinstance(hashed, str):
        return False
    return (
        not hashed.startswith(("$2a$", "$2b$", "$2y$"))
        and len(hashed) == 64
        and all(c in "0123456789abcdefABCDEF" for c in hashed)
    )


def verify_password(password: str, hashed: str) -> bool:
    """Verifies a plaintext password against a stored hash.

    Supports modern bcrypt hashes and gracefully verifies legacy SHA-256 hashes
    to enable seamless on-login migration.
    """
    if not password or not hashed:
        return False
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False
    # Constant-time comparison for legacy SHA-256 hashes
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, hashed)


def make_token(user_id: int, org_id: int | None = None) -> str:
    secret = get_secret_key()
    payload = {
        "sub": str(user_id),
        "org": org_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _decode(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    secret = get_secret_key()
    try:
        return jwt.decode(authorization[7:], secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")



def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> models.User:
    data = _decode(authorization)
    user = db.get(models.User, int(data["sub"]))
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def current_membership(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> models.Membership:
    """The membership for the organization selected after login."""
    data = _decode(authorization)
    if not data.get("org"):
        raise HTTPException(400, "Select an organization first")
    m = (
        db.query(models.Membership)
        .filter_by(user_id=int(data["sub"]), org_id=data["org"])
        .first()
    )
    if not m:
        raise HTTPException(403, "Not a member of this organization")
    return m
