import os


def load_env() -> None:
    """Loads configuration from local .env files if present.

    Searches candidate paths in priority order:
      1. backend/.env (canonical backend configuration)
      2. .env in current working directory
      3. .env in project repository root

    Populates values into os.environ if unset or empty, ensuring that
    empty environment variables do not block .env values. Quotes are cleanly stripped.
    """
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
        os.path.abspath(os.path.join(os.getcwd(), ".env")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    ]
    seen_files = set()
    for env_path in candidates:
        if env_path in seen_files or not os.path.isfile(env_path):
            continue
        seen_files.add(env_path)
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    # Strip matching outer quotes ("..." or '...')
                    if len(v) >= 2 and (
                        (v.startswith('"') and v.endswith('"'))
                        or (v.startswith("'") and v.endswith("'"))
                    ):
                        v = v[1:-1].strip()
                    # Only populate if not in os.environ or if the existing value is empty
                    if not os.environ.get(k, "").strip():
                        os.environ[k] = v
        except OSError:
            pass


load_env()

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
