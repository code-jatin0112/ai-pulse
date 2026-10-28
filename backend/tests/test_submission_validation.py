import pytest
from unittest.mock import MagicMock
from app.db import SessionLocal
from app import models
from app.auth import make_token
from tests.conftest import login
from tests.test_dashboard_privacy import setup_org_with_members


def get_priya_valid_answers():
    return [
        {"question_id": "common-freq", "answer": "Daily"},
        {"question_id": "common-policy", "answer": "Yes, and I follow it"},
        {"question_id": "common-data", "answer": "Always, and I know which tools are approved"},
        {"question_id": "common-review", "answer": "Check facts and edit it"},
        {"question_id": "common-open", "answer": "Wrote customer email summaries with clear review."},
        {"question_id": "sup-drafts", "answer": "To draft replies and summarise ticket history"},
    ]


def test_complete_valid_submission_succeeds(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"saved": 6}

    # Verify answers stored in DB
    db = SessionLocal()
    priya = db.query(models.User).filter_by(email="priya@northwind.test").first()
    m = db.query(models.Membership).filter_by(user_id=priya.id).first()
    responses = db.query(models.Response).filter_by(membership_id=m.id).all()
    assert len(responses) == 6
    assert all(r.score is not None and 1.0 <= r.score <= 5.0 for r in responses)
    db.close()


def test_missing_question_is_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    # Remove the support-specific question
    answers = [a for a in answers if a["question_id"] != "sup-drafts"]

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 422
    assert "Missing required questions" in r.json()["detail"]
    assert "sup-drafts" in r.json()["detail"]


def test_unknown_question_id_is_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    answers[0] = {"question_id": "nonexistent-q-999", "answer": "Daily"}

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 422
    assert "Ineligible or unknown questions" in r.json()["detail"]


def test_role_ineligible_question_is_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    # Replace support question with engineering architecture question
    answers[-1] = {"question_id": "eng-arch", "answer": "Several features, monitored"}

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 422
    assert "Ineligible or unknown questions" in r.json()["detail"]
    assert "eng-arch" in r.json()["detail"]


def test_duplicate_question_ids_are_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    # Duplicate first question
    answers.append({"question_id": "common-freq", "answer": "Daily"})

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 422
    assert "Duplicate question IDs" in r.json()["detail"]


def test_invalid_mcq_options_are_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    answers[0]["answer"] = "Not a valid option choice"

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 422
    assert "Invalid option" in r.json()["detail"]


def test_blank_answers_are_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    
    # Whitespace only
    answers = get_priya_valid_answers()
    answers[4]["answer"] = "   \n\t   "
    r1 = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r1.status_code == 422
    assert "Blank answer" in r1.json()["detail"]

    # Empty string
    answers[4]["answer"] = ""
    r2 = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r2.status_code == 422
    assert "Blank answer" in r2.json()["detail"]


def test_excessively_long_answers_are_rejected(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    answers[4]["answer"] = "A" * 5001

    r = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r.status_code == 422
    assert "exceeds maximum length" in r.json()["detail"]


def test_repeated_valid_submission_replaces_previous_responses(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers1 = get_priya_valid_answers()
    r1 = client.post("/diagnostic/submit", json={"answers": answers1}, headers=headers)
    assert r1.status_code == 200

    db = SessionLocal()
    priya = db.query(models.User).filter_by(email="priya@northwind.test").first()
    m = db.query(models.Membership).filter_by(user_id=priya.id).first()
    m_id = m.id
    count1 = db.query(models.Response).filter_by(membership_id=m_id).count()
    assert count1 == 6
    db.close()

    # Submit second time with different MCQ answers
    answers2 = get_priya_valid_answers()
    answers2[0]["answer"] = "Never"  # score: 1
    r2 = client.post("/diagnostic/submit", json={"answers": answers2}, headers=headers)
    assert r2.status_code == 200

    # Count must remain exactly 6, not 12
    db = SessionLocal()
    count2 = db.query(models.Response).filter_by(membership_id=m_id).count()
    assert count2 == 6
    # Verify the updated answer is what is stored
    freq_resp = db.query(models.Response).filter_by(membership_id=m_id, question_id="common-freq").first()
    assert freq_resp.answer == "Never"
    assert freq_resp.score == 1.0
    db.close()

    # Report shows answered: 6
    rep = client.get("/reports/me", headers=headers)
    assert rep.status_code == 200
    assert rep.json()["answered"] == 6


def test_failed_resubmission_preserves_previous_valid_responses(client, monkeypatch):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers1 = get_priya_valid_answers()
    r1 = client.post("/diagnostic/submit", json={"answers": answers1}, headers=headers)
    assert r1.status_code == 200

    db = SessionLocal()
    priya = db.query(models.User).filter_by(email="priya@northwind.test").first()
    m = db.query(models.Membership).filter_by(user_id=priya.id).first()
    m_id = m.id
    db.close()

    # 1. Validation failure: missing question
    invalid_sub = [answers1[0]]
    r_val_err = client.post("/diagnostic/submit", json={"answers": invalid_sub}, headers=headers)
    assert r_val_err.status_code == 422

    db = SessionLocal()
    assert db.query(models.Response).filter_by(membership_id=m_id).count() == 6
    db.close()

    # 2. LLM failure: mock scoring error
    def mock_broken_scoring(question, answer):
        raise RuntimeError("LLM API gateway timeout")

    monkeypatch.setattr("app.routes.diagnostic.score_open_answer", mock_broken_scoring)
    r_llm_err = client.post("/diagnostic/submit", json={"answers": answers1}, headers=headers)
    assert r_llm_err.status_code == 502
    assert "AI scoring service" in r_llm_err.json()["detail"]

    # Original 6 responses still intact
    db = SessionLocal()
    assert db.query(models.Response).filter_by(membership_id=m_id).count() == 6
    db.close()


def test_diagnostic_completion_counts_remain_accurate(client):
    org_id, _, emp_ids, admin_headers = setup_org_with_members(num_members=5)
    db = SessionLocal()
    members = [db.get(models.Membership, eid) for eid in emp_ids]
    tokens = [make_token(m.user_id, org_id) for m in members]
    db.close()

    # All 5 complete diagnostic
    for token in tokens:
        headers = {"Authorization": f"Bearer {token}"}
        # Support junior has questions: 5 common + sup-drafts
        support_junior_answers = [
            {"question_id": "common-freq", "answer": "Daily"},
            {"question_id": "common-policy", "answer": "Yes, and I follow it"},
            {"question_id": "common-data", "answer": "Always, and I know which tools are approved"},
            {"question_id": "common-review", "answer": "Check facts and edit it"},
            {"question_id": "common-open", "answer": "Automated ticket triage using Python and verified classifications."},
            {"question_id": "sup-drafts", "answer": "To draft replies and summarise ticket history"},
        ]
        r = client.post("/diagnostic/submit", json={"answers": support_junior_answers}, headers=headers)
        assert r.status_code == 200

    r_dash1 = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r_dash1.status_code == 200
    assert r_dash1.json()["departments"][0]["responded"] == 5

    # Member 0 resubmits 3 times
    m0_headers = {"Authorization": f"Bearer {tokens[0]}"}
    for _ in range(3):
        support_junior_answers[5]["answer"] = "I've built templates/prompts my team reuses"
        r_re = client.post("/diagnostic/submit", json={"answers": support_junior_answers}, headers=m0_headers)
        assert r_re.status_code == 200

    # Responded count must strictly remain 5
    r_dash2 = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r_dash2.status_code == 200
    assert r_dash2.json()["departments"][0]["responded"] == 5


def test_employee_and_organization_data_isolation(client):
    headers_priya, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers_priya = get_priya_valid_answers()
    r = client.post("/diagnostic/submit", json={"answers": answers_priya}, headers=headers_priya)
    assert r.status_code == 200

    db = SessionLocal()
    # Check that responses belong to Priya's membership only
    priya = db.query(models.User).filter_by(email="priya@northwind.test").first()
    priya_m = db.query(models.Membership).filter_by(user_id=priya.id, org_id=1).first()
    vikram = db.query(models.User).filter_by(email="vikram@northwind.test").first()
    vikram_m = db.query(models.Membership).filter_by(user_id=vikram.id, org_id=1).first()

    priya_responses = db.query(models.Response).filter_by(membership_id=priya_m.id).all()
    vikram_responses = db.query(models.Response).filter_by(membership_id=vikram_m.id).all()
    assert len(priya_responses) == 6
    # Vikram's seeded responses remain untouched
    assert len(vikram_responses) == 2
    db.close()


def test_resubmission_after_deletion_works(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    # Delete first
    r_del = client.delete("/diagnostic/me", headers=headers)
    assert r_del.status_code == 200

    # Verify report is empty
    r_rep1 = client.get("/reports/me", headers=headers)
    assert r_rep1.json()["answered"] == 0

    # Resubmit complete valid diagnostic
    answers = get_priya_valid_answers()
    r_sub = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r_sub.status_code == 200
    assert r_sub.json() == {"saved": 6}

    # Verify report now has 6 responses
    r_rep2 = client.get("/reports/me", headers=headers)
    assert r_rep2.json()["answered"] == 6
    assert r_rep2.json()["level"] != "Not assessed"


def test_failed_validation_triggers_zero_llm_calls(client, monkeypatch):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    
    mock_score = MagicMock(return_value={"score": 4.0, "reason": "Good", "flags": []})
    monkeypatch.setattr("app.routes.diagnostic.score_open_answer", mock_score)

    # 1. Duplicate question ID
    invalid_sub = get_priya_valid_answers()
    invalid_sub.append({"question_id": "common-freq", "answer": "Daily"})
    r1 = client.post("/diagnostic/submit", json={"answers": invalid_sub}, headers=headers)
    assert r1.status_code == 422
    assert mock_score.call_count == 0

    # 2. Missing question
    r2 = client.post("/diagnostic/submit", json={"answers": invalid_sub[:3]}, headers=headers)
    assert r2.status_code == 422
    assert mock_score.call_count == 0

    # 3. Invalid MCQ option
    invalid_mcq = get_priya_valid_answers()
    invalid_mcq[0]["answer"] = "Bogus Option"
    r3 = client.post("/diagnostic/submit", json={"answers": invalid_mcq}, headers=headers)
    assert r3.status_code == 422
    assert mock_score.call_count == 0
