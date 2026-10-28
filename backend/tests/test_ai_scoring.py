import json
import pytest
import httpx
from unittest.mock import MagicMock, patch

from app.services.scoring import (
    score_open_answer,
    AIValidationError,
    APPROVED_RISK_FLAGS,
)
from app.services.llm import score_answer, AIServiceError
from app.db import SessionLocal
from app import models
from tests.conftest import login
from tests.test_submission_validation import get_priya_valid_answers


def test_valid_json_output(monkeypatch):
    canned = '{"score": 4, "reason": "Thoughtful use with verified accuracy.", "flags": ["customer_data_shared"]}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    result = score_open_answer("How do you use AI?", "I use it with care.")
    assert result["score"] == 4.0
    assert result["reason"] == "Thoughtful use with verified accuracy."
    assert result["flags"] == ["customer_data_shared"]


def test_valid_json_inside_markdown_code_fence(monkeypatch):
    canned = "```json\n{\"score\": 4, \"reason\": \"Thoughtful use with review.\", \"flags\": []}\n```"
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    result = score_open_answer("How do you use AI?", "I review everything.")
    assert result["score"] == 4.0
    assert result["reason"] == "Thoughtful use with review."
    assert result["flags"] == []


def test_malformed_json_rejected(monkeypatch):
    bad_canned = '{score: 4, "reason": unquoted_value}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: bad_canned)

    with pytest.raises(AIValidationError) as exc:
        score_open_answer("Question", "Answer")
    assert "not valid JSON" in str(exc.value)


def test_out_of_range_score_rejected(monkeypatch):
    for bad_score in [7, 0, -1, 5.5, float("inf"), float("nan")]:
        canned = json.dumps({"score": bad_score, "reason": "Some reason.", "flags": []})
        monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

        with pytest.raises(AIValidationError):
            score_open_answer("Question", "Answer")


def test_string_score_rejected(monkeypatch):
    canned = '{"score": "four", "reason": "Good regular use.", "flags": []}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")


def test_boolean_score_rejected(monkeypatch):
    canned = '{"score": true, "reason": "Good regular use.", "flags": []}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")


def test_missing_reason_rejected(monkeypatch):
    canned = '{"score": 3, "flags": ["unreviewed_output"]}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")


def test_empty_reason_rejected(monkeypatch):
    for empty in ["", "   ", "\n\t"]:
        canned = json.dumps({"score": 3, "reason": empty, "flags": []})
        monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

        with pytest.raises(AIValidationError):
            score_open_answer("Question", "Answer")


def test_invalid_or_unknown_risk_flags_rejected(monkeypatch):
    canned = '{"score": 2, "reason": "Limited use.", "flags": ["probably_lying", "made_up_flag"]}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    with pytest.raises(AIValidationError) as exc:
        score_open_answer("Question", "Answer")
    assert "failed schema validation" in str(exc.value)


def test_missing_flags_field_rejected(monkeypatch):
    # Missing required flags field
    canned = '{"score": 4, "reason": "Good regular use."}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    with pytest.raises(AIValidationError) as exc:
        score_open_answer("Question", "Answer")
    assert "failed schema validation" in str(exc.value)


def test_explicitly_empty_flags_array_accepted(monkeypatch):
    canned = '{"score": 4, "reason": "Good regular use.", "flags": []}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned)

    result = score_open_answer("Question", "Answer")
    assert result["score"] == 4.0
    assert result["flags"] == []


def test_sensitive_marker_absent_from_logs_and_api_errors(client, monkeypatch, caplog):
    sensitive_marker = "CONFIDENTIAL_SSN_987-65-4321_SECRET_TOKEN_XYZ"
    bad_ai_output = json.dumps({
        "score": 99,
        "reason": f"Sensitive data leaked: {sensitive_marker}",
        "flags": [sensitive_marker],
    })
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: bad_ai_output)

    with caplog.at_level("DEBUG"):
        headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
        answers = get_priya_valid_answers()
        r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)

    # 1. API error must be generic 502 without leaking the sensitive marker
    assert r.status_code == 502
    assert r.json() == {"detail": "AI scoring service temporarily unavailable. Please try again."}
    assert sensitive_marker not in r.text

    # 2. Server-side captured logs must NOT contain the sensitive marker
    assert sensitive_marker not in caplog.text


def test_flags_of_wrong_type_rejected(monkeypatch):
    # Flags as a string instead of a list
    canned1 = '{"score": 3, "reason": "Valid reason.", "flags": "customer_data_shared"}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned1)
    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")

    # Flags as a list containing numbers
    canned2 = '{"score": 3, "reason": "Valid reason.", "flags": [123]}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned2)
    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")


def test_unexpected_response_structure_rejected(monkeypatch):
    # Extra unexpected key
    canned1 = '{"score": 4, "reason": "Good.", "flags": [], "unexpected_field": "hacked"}'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned1)
    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")

    # Array instead of object
    canned2 = '[{"score": 4, "reason": "Good.", "flags": []}]'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned2)
    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")

    # Conversational text surrounding JSON
    canned3 = 'Sure! Here is the JSON: {"score": 4, "reason": "Good.", "flags": []} Hope it helps!'
    monkeypatch.setattr("app.services.scoring.llm.score_answer", lambda q, a: canned3)
    with pytest.raises(AIValidationError):
        score_open_answer("Question", "Answer")


def test_provider_timeout_and_http_errors(monkeypatch):
    monkeypatch.setattr("app.services.llm.AI_MODE", "live")
    monkeypatch.setattr("app.services.llm.LLM_API_URL", "https://api.fake.ai/v1/chat")
    monkeypatch.setattr("app.services.llm.LLM_API_KEY", "fake-test-key")

    # Timeout
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(AIServiceError) as exc:
            score_answer("Question", "Answer")
        assert "AI scoring provider error" in str(exc.value)

    # HTTP 500 error
    mock_resp = httpx.Response(status_code=500, request=httpx.Request("POST", "https://api.fake.ai/v1/chat"))
    with patch("httpx.Client.post", side_effect=httpx.HTTPStatusError("500 Server Error", request=mock_resp.request, response=mock_resp)):
        with pytest.raises(AIServiceError) as exc:
            score_answer("Question", "Answer")
        assert "AI scoring provider error" in str(exc.value)


def test_failed_ai_resubmission_preserves_previous_diagnostic(client, monkeypatch):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()

    # 1. Successful initial submission
    r1 = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r1.status_code == 200

    db = SessionLocal()
    priya = db.query(models.User).filter_by(email="priya@northwind.test").first()
    m = db.query(models.Membership).filter_by(user_id=priya.id, org_id=1).first()
    before_rows = db.query(models.Response).filter_by(membership_id=m.id).all()
    assert len(before_rows) == 6
    before_scores = {r.question_id: r.score for r in before_rows}
    db.close()

    # 2. Resubmission fails due to invalid AI response (score 7)
    monkeypatch.setattr(
        "app.services.scoring.llm.score_answer",
        lambda q, a: '{"score": 7, "reason": "Out of bounds.", "flags": []}',
    )
    r2 = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r2.status_code == 502
    assert r2.json()["detail"] == "AI scoring service temporarily unavailable. Please try again."

    # 3. Verify database was preserved completely
    db = SessionLocal()
    after_rows = db.query(models.Response).filter_by(membership_id=m.id).all()
    assert len(after_rows) == 6
    after_scores = {r.question_id: r.score for r in after_rows}
    assert after_scores == before_scores
    db.close()


def test_no_invalid_score_or_risk_flag_persisted(client, monkeypatch):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()

    # Attempt submission with unapproved risk flag
    monkeypatch.setattr(
        "app.services.scoring.llm.score_answer",
        lambda q, a: '{"score": 3, "reason": "Good.", "flags": ["made_up_flag"]}',
    )
    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 502

    # Verify no response with made_up_flag exists in database
    db = SessionLocal()
    all_responses = db.query(models.Response).all()
    for resp in all_responses:
        for f in (resp.flags or []):
            assert f in APPROVED_RISK_FLAGS
    db.close()


def test_mock_ai_responses_json_regression_fixtures():
    """Validates each of the 10 canned items in mock_ai_responses.json against expected pass/fail."""
    with open("data/mock_ai_responses.json") as f:
        canned = json.load(f)

    # Indices 0 to 4 are valid
    for idx in range(5):
        with patch("app.services.scoring.llm.score_answer", return_value=canned[idx]):
            res = score_open_answer("Question", "Answer")
            assert 1.0 <= res["score"] <= 5.0
            assert res["reason"]

    # Index 5: score 7 (invalid)
    with patch("app.services.scoring.llm.score_answer", return_value=canned[5]):
        with pytest.raises(AIValidationError):
            score_open_answer("Question", "Answer")

    # Index 6: missing reason (invalid)
    with patch("app.services.scoring.llm.score_answer", return_value=canned[6]):
        with pytest.raises(AIValidationError):
            score_open_answer("Question", "Answer")

    # Index 7: score 'four' (invalid)
    with patch("app.services.scoring.llm.score_answer", return_value=canned[7]):
        with pytest.raises(AIValidationError):
            score_open_answer("Question", "Answer")

    # Index 8: invalid flags (invalid)
    with patch("app.services.scoring.llm.score_answer", return_value=canned[8]):
        with pytest.raises(AIValidationError):
            score_open_answer("Question", "Answer")

    # Index 9: markdown code block (valid)
    with patch("app.services.scoring.llm.score_answer", return_value=canned[9]):
        res = score_open_answer("Question", "Answer")
        assert res["score"] == 4.0
        assert res["reason"] == "Thoughtful use with review."
