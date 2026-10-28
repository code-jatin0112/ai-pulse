import os
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


def test_startup_validation_halts_on_missing_or_invalid_secret(monkeypatch):
    from app.main import validate_startup_configuration

    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError) as exc_info:
        validate_startup_configuration()
    assert "missing" in str(exc_info.value).lower()

    monkeypatch.setenv("SECRET_KEY", "ai-pulse-dev-secret")
    with pytest.raises(RuntimeError) as exc_info:
        validate_startup_configuration()
    assert "insecure or known compromised" in str(exc_info.value).lower()


def test_load_env_populates_empty_and_strips_quotes(tmp_path, monkeypatch):
    from app.config import load_env

    env_file = tmp_path / ".env"
    env_file.write_text(
        'TEST_CUSTOM_LOAD_KEY="test_custom_value"\n'
        'TEST_QUOTED_SINGLE=\'single_value\'\n'
        '# This is a comment\n'
        'TEST_UNQUOTED=unquoted_value\n'
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TEST_CUSTOM_LOAD_KEY", raising=False)
    monkeypatch.delenv("TEST_QUOTED_SINGLE", raising=False)
    monkeypatch.delenv("TEST_UNQUOTED", raising=False)

    load_env()

    assert os.getenv("TEST_CUSTOM_LOAD_KEY") == "test_custom_value"
    assert os.getenv("TEST_QUOTED_SINGLE") == "single_value"
    assert os.getenv("TEST_UNQUOTED") == "unquoted_value"


def test_login_returns_sanitized_500_on_runtime_config_error(client, monkeypatch):
    # Verify internal exception details and secret information are NEVER leaked in HTTP 500 responses
    internal_error_msg = "SENSITIVE_INTERNAL_SECRET_OR_KEY_DETAIL_MISSING"
    monkeypatch.setattr(
        "app.routes.auth_routes.make_token",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(internal_error_msg)),
    )
    res = client.post("/auth/login", json={"email": "asha@northwind.test", "password": "pulse123"})
    assert res.status_code == 500
    assert res.json()["detail"] == "Authentication service unavailable"
    # Proves internal details and secret traces are never leaked in response body
    assert internal_error_msg not in res.text
