import json
import logging
import math
from pydantic import BaseModel, ConfigDict, field_validator, ValidationError

from . import llm
from .llm import AIServiceError

logger = logging.getLogger("ai_pulse.scoring")

APPROVED_RISK_FLAGS = {
    "customer_data_shared",
    "confidential_data_shared",
    "unreviewed_output",
    "policy_unaware",
}


class AIValidationError(Exception):
    """Raised when AI response is malformed, invalid JSON, or violates schema."""
    pass


class AIScoreOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    score: float | int
    reason: str
    flags: list[str]

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if isinstance(v, bool):
            raise ValueError("Score cannot be a boolean")
        if not math.isfinite(v):
            raise ValueError("Score must be a finite number")
        if not (1.0 <= float(v) <= 5.0):
            raise ValueError("Score must be between 1 and 5")
        return float(v)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v):
        if not isinstance(v, str):
            raise ValueError("Reason must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("Reason cannot be empty")
        if len(stripped) > 1000:
            raise ValueError("Reason exceeds maximum length of 1000 characters")
        return stripped

    @field_validator("flags")
    @classmethod
    def validate_flags(cls, v):
        if not isinstance(v, list):
            raise ValueError("Flags must be a list")
        for f in v:
            if not isinstance(f, str):
                raise ValueError("Flag must be a string")
            if f not in APPROVED_RISK_FLAGS:
                raise ValueError(f"Unapproved risk flag: '{f}'")
        return sorted(set(v))


def extract_json_payload(raw: str) -> str:
    """Extracts a JSON object string, safely unwrapping a single Markdown code fence if present."""
    if not isinstance(raw, str):
        raise AIValidationError("AI output must be a text string")
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```") and lines[-1].strip() == "```":
            inner = "\n".join(lines[1:-1]).strip()
            if "```" in inner:
                raise AIValidationError("Multiple or ambiguous markdown code fences detected in AI response")
            text = inner
        else:
            raise AIValidationError("Malformed markdown code fence in AI response")
    return text


def score_open_answer(question_text: str, answer: str) -> dict:
    """Scores an open-ended answer via LLM, safely validating schema and constraints."""
    raw = llm.score_answer(question_text, answer)
    cleaned = extract_json_payload(raw)

    try:
        data = json.loads(cleaned)
    except Exception as exc:
        logger.warning("Failed to parse JSON from AI response: %s", type(exc).__name__)
        raise AIValidationError("AI response is not valid JSON") from exc

    if not isinstance(data, dict):
        raise AIValidationError("AI response must be a JSON object")

    try:
        validated = AIScoreOutput.model_validate(data)
    except ValidationError as exc:
        error_types = [e.get("type", "unknown") for e in exc.errors()]
        error_fields = [".".join(str(loc) for loc in e.get("loc", ())) for e in exc.errors()]
        logger.warning(
            "AI response schema validation failed with %d error(s): fields=%s types=%s",
            len(exc.errors()),
            error_fields,
            error_types,
        )
        raise AIValidationError("AI response failed schema validation") from exc

    return {
        "score": validated.score,
        "reason": validated.reason,
        "flags": validated.flags,
    }
