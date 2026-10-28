import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth import verify_password, hash_password, is_legacy_hash, make_token, current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class SelectOrgIn(BaseModel):
    org_id: int


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")

    # Seamless migration: if user has a legacy unsalted SHA-256 hash, upgrade to bcrypt on login
    if is_legacy_hash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()

    orgs = [
        {"org_id": m.org_id, "org_name": m.org.name, "role": m.role}
        for m in user.memberships
    ]
    try:
        token = make_token(user.id)
    except Exception as exc:
        logger.error("Token issuance failed due to %s", type(exc).__name__)
        raise HTTPException(500, "Authentication service unavailable")
    return {"token": token, "name": user.name, "organizations": orgs}


@router.post("/select-org")
def select_org(body: SelectOrgIn, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    membership = (
        db.query(models.Membership)
        .filter_by(user_id=user.id, org_id=body.org_id)
        .first()
    )
    if not membership:
        raise HTTPException(403, "Not a member of this organization")
    # Issue a token scoped to the chosen organization
    try:
        token = make_token(user.id, body.org_id)
    except Exception as exc:
        logger.error("Scoped token issuance failed due to %s", type(exc).__name__)
        raise HTTPException(500, "Authentication service unavailable")
    return {"token": token, "org_id": body.org_id}

