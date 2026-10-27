import os

# Load .env if present (very small loader, no extra dependency)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    for line in open(_env_path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

MIN_SECRET_LENGTH = 32
DISALLOWED_SECRETS = {
    "ai-pulse-dev-secret",
    "pulse-7f3a9c2e1b-prod",
    "replace-with-a-secure-random-secret-key-at-least-32-chars",
    "replace-with-a-secure-random-secret-key",
}


def get_secret_key() -> str:
    """Returns the validated JWT signing secret.

    Raises RuntimeError if the secret is missing, insecure, or insufficiently strong.
    Never exposes secret values in error messages.
    """
    key = os.getenv("SECRET_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "JWT signing secret is missing. Set SECRET_KEY in your environment or local .env file."
        )
    if key in DISALLOWED_SECRETS:
        raise RuntimeError(
            "JWT signing secret is configured with an insecure or known compromised default key. Please rotate it."
        )
    if len(key) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT signing secret is insufficiently strong. It must be at least {MIN_SECRET_LENGTH} characters."
        )
    return key


SECRET_KEY = os.getenv("SECRET_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aipulse.db")
AI_MODE = os.getenv("AI_MODE", "mock")  # "mock" or "live"
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
TOKEN_HOURS = 12
