import hashlib
import pytest
from app import models
from app.auth import hash_password, verify_password, is_legacy_hash
from app.db import SessionLocal
from tests.conftest import login


def test_password_hashing_is_salted_and_generates_distinct_hashes():
    """Two identical passwords must yield distinct salted bcrypt hashes."""
    pwd = "pulse123"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)

    assert h1 != h2, "Hashes for identical passwords must be distinct due to random salt"
    assert h1.startswith(("$2b$", "$2a$", "$2y$")), "Hash must use standard bcrypt format"
    assert h2.startswith(("$2b$", "$2a$", "$2y$")), "Hash must use standard bcrypt format"
    assert len(h1) == 60, "Bcrypt hash must be 60 characters"
    assert len(h2) == 60, "Bcrypt hash must be 60 characters"


def test_password_verification_logic():
    """Correct password verifies successfully; wrong or empty passwords fail safely."""
    pwd = "secure_password_abc"
    hashed = hash_password(pwd)

    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(pwd, "") is False
    assert verify_password(pwd, "invalid_hash_string") is False


def test_seeded_demo_accounts_authenticate(client):
    """All standard seeded accounts must authenticate with 'pulse123'."""
    demo_emails = [
        "asha@northwind.test",
        "meera@bluepeak.test",
        "priya@northwind.test",
        "dev@northwind.test",
        "ravi@consult.test",
    ]
    for email in demo_emails:
        r = client.post("/auth/login", json={"email": email, "password": "pulse123"})
        assert r.status_code == 200, f"Login failed for seeded user {email}"
        data = r.json()
        assert "token" in data
        assert len(data["organizations"]) > 0

        # Wrong password rejected
        r_bad = client.post("/auth/login", json={"email": email, "password": "incorrect_password"})
        assert r_bad.status_code == 401
        assert "Wrong email or password" in r_bad.json()["detail"]


def test_legacy_sha256_hash_verification_and_seamless_migration(client):
    """Legacy unsalted SHA-256 hashes authenticate and are seamlessly upgraded to bcrypt on login."""
    test_email = "migrating_user@test.legacy"
    test_password = "my_legacy_password_456"
    raw_sha256 = hashlib.sha256(test_password.encode("utf-8")).hexdigest()

    assert is_legacy_hash(raw_sha256) is True

    # Seed an isolated user with raw SHA-256 hash
    db = SessionLocal()
    org = models.Organization(name="Legacy Migration Org")
    db.add(org)
    db.flush()

    user = models.User(
        name="Legacy Migrating User",
        email=test_email,
        password_hash=raw_sha256,
    )
    db.add(user)
    db.flush()

    membership = models.Membership(
        user_id=user.id,
        org_id=org.id,
        role="employee",
        job_role="support",
        seniority="junior",
    )
    db.add(membership)
    db.commit()
    user_id = user.id
    db.close()

    # 1. Login with legacy hash: must succeed
    r_login = client.post("/auth/login", json={"email": test_email, "password": test_password})
    assert r_login.status_code == 200
    token = r_login.json()["token"]
    assert token

    # 2. Inspect database: hash must be seamlessly migrated to bcrypt
    db2 = SessionLocal()
    updated_user = db2.get(models.User, user_id)
    assert updated_user is not None
    assert updated_user.password_hash != raw_sha256, "Legacy hash should have been replaced"
    assert updated_user.password_hash.startswith(("$2b$", "$2a$", "$2y$")), "New hash must be bcrypt"
    assert is_legacy_hash(updated_user.password_hash) is False
    migrated_hash = updated_user.password_hash
    db2.close()

    # 3. Subsequent login: verifies against the newly stored bcrypt hash
    r_login2 = client.post("/auth/login", json={"email": test_email, "password": test_password})
    assert r_login2.status_code == 200

    # 4. Wrong password against migrated user is rejected
    r_bad = client.post("/auth/login", json={"email": test_email, "password": "wrong_password"})
    assert r_bad.status_code == 401


def test_auth_and_organization_isolation_preserved(client):
    """Organization selection and token scoping remain strictly enforced with new hashing."""
    headers, data = login(client, "priya@northwind.test", "Northwind Logistics")
    assert headers["Authorization"].startswith("Bearer ")

    # Priya belongs only to Northwind (org 1), attempt selecting Bluepeak (org 2)
    r_login = client.post("/auth/login", json={"email": "priya@northwind.test", "password": "pulse123"})
    token = r_login.json()["token"]

    r_cross = client.post(
        "/auth/select-org",
        json={"org_id": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_cross.status_code == 403
    assert "Not a member of this organization" in r_cross.json()["detail"]

