"""Thin wrapper around the LLM used to score open-ended answers.

AI_MODE=mock  -> returns canned responses from data/mock_ai_responses.json
AI_MODE=live  -> calls an OpenAI-compatible chat completions endpoint
"""
import hashlib
import json
import logging
import os
import time

import httpx

from ..config import AI_MODE, LLM_API_URL, LLM_API_KEY, LLM_MODEL

_MOCK_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "mock_ai_responses.json")
logger = logging.getLogger("ai_pulse.llm")

DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_ATTEMPTS = 2


class AIServiceError(Exception):
    """Raised when external AI provider fails or times out."""
    pass


PROMPT = """You are scoring how well an employee uses AI at work.
Rubric: 1 = no AI use, 2 = occasional basic use, 3 = regular use for simple tasks,
4 = regular, thoughtful use with review of outputs, 5 = advanced use that changes how the work is done.
Flag risks using only these labels: customer_data_shared, confidential_data_shared, unreviewed_output, policy_unaware.
Answer the question: {question}
Employee's answer: {answer}
Return JSON: {{"score": <1-5>, "reason": "<one sentence>", "flags": [<labels>]}}"""


def _mock(answer: str) -> str:
    with open(_MOCK_PATH) as f:
        canned = json.load(f)
    idx = int(hashlib.md5(answer.encode()).hexdigest(), 16) % len(canned)
    return canned[idx]


def score_answer(question: str, answer: str) -> str:
    """Returns the raw text the model produced, with bounded timeout and retry."""
    if AI_MODE == "mock":
        return _mock(answer)

    if not LLM_API_URL or not LLM_API_KEY:
        logger.error("Live AI mode configured but LLM_API_URL or LLM_API_KEY is missing")
        raise AIServiceError("AI scoring provider is not properly configured")

    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": PROMPT.format(question=question, answer=answer)}],
    }

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                r = client.post(
                    LLM_API_URL,
                    headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                if not content or not isinstance(content, str):
                    raise AIServiceError("AI provider returned empty or non-string message content")
                return content
        except httpx.TimeoutException as exc:
            logger.warning("AI provider timed out on attempt %d/%d", attempt, MAX_ATTEMPTS)
            last_error = exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.warning("AI provider HTTP status %d on attempt %d/%d", status_code, attempt, MAX_ATTEMPTS)
            last_error = exc
            if status_code not in (429, 503):
                break
        except (httpx.RequestError, KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.warning("AI provider request/format error on attempt %d/%d: %s", attempt, MAX_ATTEMPTS, type(exc).__name__)
            last_error = exc
            break

        if attempt < MAX_ATTEMPTS:
            time.sleep(0.5)

    logger.error("AI scoring failed after %d attempt(s): %s", attempt, type(last_error).__name__)
    raise AIServiceError("AI scoring provider error")
