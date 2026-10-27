import jwt
import pytest
from fastapi import HTTPException

from app.auth import make_token, _decode
from app.config import get_secret_key


def test_missing_secret_key_fails_safely(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError) as exc_info:
        get_secret_key()
    assert "missing" in str(exc_info.value).lower()

    # Verify token issuance fails safely without printing secrets
    with pytest.raises(RuntimeError):
        make_token(1)


def test_insufficiently_strong_secret_key_fails_safely(monkeypatch):
    short_key = "short-key-16-ch"
    monkeypatch.setenv("SECRET_KEY", short_key)
    with pytest.raises(RuntimeError) as exc_info:
        get_secret_key()
    assert "insufficiently strong" in str(exc_info.value).lower()
    # Confirm secret value is never exposed in error message
    assert short_key not in str(exc_info.value)


def test_disallowed_compromised_default_keys_fail_safely(monkeypatch):
    for bad_key in ["ai-pulse-dev-secret", "pulse-7f3a9c2e1b-prod", "replace-with-a-secure-random-secret-key-at-least-32-chars"]:
        monkeypatch.setenv("SECRET_KEY", bad_key)
        with pytest.raises(RuntimeError) as exc_info:
            get_secret_key()
        assert "insecure or known compromised" in str(exc_info.value).lower()
        # Confirm secret value is never exposed in error message
        assert bad_key not in str(exc_info.value)


def test_valid_configuration_permits_token_generation_and_verification(monkeypatch):
    valid_key = "test-custom-strong-signing-secret-key-64-hex-value-1234567890abcdef"
    monkeypatch.setenv("SECRET_KEY", valid_key)
    assert get_secret_key() == valid_key

    token = make_token(42, 7)
    assert isinstance(token, str)
    decoded = _decode(f"Bearer {token}")
    assert decoded["sub"] == "42"
    assert decoded["org"] == 7


def test_tokens_signed_with_old_exposed_key_are_rejected():
    # Token minted using the old compromised key from git history
    old_compromised_key = "pulse-7f3a9c2e1b-prod"
    old_token = jwt.encode({"sub": "1", "org": 1}, old_compromised_key, algorithm="HS256")

    # The current running application uses rotated valid secret
    with pytest.raises(HTTPException) as exc_info:
        _decode(f"Bearer {old_token}")
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail
