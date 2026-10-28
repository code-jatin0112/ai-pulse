import pytest
from app.db import SessionLocal
from app import models
from app.auth import make_token
from app.services.insights import (
    calculate_growth_insights,
    get_question_category,
    QUESTION_CATEGORY_MAP,
    CATEGORIES,
    TIE_BREAKER_STRONGEST,
    TIE_BREAKER_IMPROVEMENT,
)
from app.services.questions import questions_for, load_questions
from tests.conftest import login
from tests.test_submission_validation import get_priya_valid_answers
from tests.test_dashboard_privacy import setup_org_with_members


def test_correct_calculation_of_breakdown_scores():
    expected_questions = [
        {"id": "common-freq"},
        {"id": "common-policy"},
        {"id": "common-data"},
        {"id": "common-review"},
        {"id": "common-open"},
        {"id": "sup-drafts"},
    ]
    # Responses:
    # adoption_frequency: common-freq -> 4.0 (avg: 4.0)
    # data_security: common-policy (2.0), common-data (4.0) -> (avg: 3.0)
    # output_verification: common-review -> 5.0 (avg: 5.0)
    # practical_application: common-open (3.0), sup-drafts (3.0) -> (avg: 3.0)
    responses = [
        models.Response(question_id="common-freq", score=4.0),
        models.Response(question_id="common-policy", score=2.0),
        models.Response(question_id="common-data", score=4.0),
        models.Response(question_id="common-review", score=5.0),
        models.Response(question_id="common-open", score=3.0),
        models.Response(question_id="sup-drafts", score=3.0),
    ]

    insights = calculate_growth_insights(responses, expected_questions)
    assert insights is not None

    breakdown_map = {b["key"]: b for b in insights["breakdown"]}
    assert breakdown_map["adoption_frequency"]["score"] == 4.0
    assert breakdown_map["adoption_frequency"]["question_count"] == 1
    assert breakdown_map["data_security"]["score"] == 3.0
    assert breakdown_map["data_security"]["question_count"] == 2
    assert breakdown_map["output_verification"]["score"] == 5.0
    assert breakdown_map["output_verification"]["question_count"] == 1
    assert breakdown_map["practical_application"]["score"] == 3.0
    assert breakdown_map["practical_application"]["question_count"] == 2


def test_correct_strongest_and_weakest_area_selection():
    expected_questions = [
        {"id": "common-freq"},
        {"id": "common-policy"},
        {"id": "common-data"},
        {"id": "common-review"},
        {"id": "common-open"},
    ]
    # Scores: freq: 2, policy: 5, data: 5 (data_sec: 5), review: 3, open: 4
    responses = [
        models.Response(question_id="common-freq", score=2.0),
        models.Response(question_id="common-policy", score=5.0),
        models.Response(question_id="common-data", score=5.0),
        models.Response(question_id="common-review", score=3.0),
        models.Response(question_id="common-open", score=4.0),
    ]

    insights = calculate_growth_insights(responses, expected_questions)
    assert insights is not None

    # Strongest is data_security (5.0)
    assert insights["strongest_area"]["key"] == "data_security"
    assert insights["strongest_area"]["score"] == 5.0

    # Weakest is adoption_frequency (2.0)
    assert insights["improvement_area"]["key"] == "adoption_frequency"
    assert insights["improvement_area"]["score"] == 2.0
    assert "routine daily tasks" in insights["improvement_area"]["recommendation"]


def test_consistent_tie_handling():
    expected_questions = [
        {"id": "common-freq"},
        {"id": "common-policy"},
        {"id": "common-review"},
        {"id": "common-open"},
    ]
    # All areas set to exactly 3.0
    responses = [
        models.Response(question_id="common-freq", score=3.0),
        models.Response(question_id="common-policy", score=3.0),
        models.Response(question_id="common-review", score=3.0),
        models.Response(question_id="common-open", score=3.0),
    ]

    insights = calculate_growth_insights(responses, expected_questions)
    assert insights is not None

    # On tie for strongest: practical_application is chosen first
    assert insights["strongest_area"]["key"] == TIE_BREAKER_STRONGEST[0]
    # On tie for improvement: data_security is prioritized (security first)
    assert insights["improvement_area"]["key"] == TIE_BREAKER_IMPROVEMENT[0]


def test_valid_1_to_5_score_bounds():
    expected_questions = [{"id": "common-freq"}]
    responses = [models.Response(question_id="common-freq", score=999.0)]

    insights = calculate_growth_insights(responses, expected_questions)
    assert insights is not None
    assert insights["strongest_area"]["score"] <= 5.0
    assert insights["improvement_area"]["score"] <= 5.0
    for b in insights["breakdown"]:
        assert 1.0 <= b["score"] <= 5.0


def test_no_insights_when_no_diagnostic_exists(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    # Delete Priya's responses
    client.delete("/diagnostic/me", headers=headers)

    r = client.get("/reports/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["answered"] == 0
    assert r.json()["growth_insights"] is None


def test_no_misleading_insights_for_incomplete_responses(client):
    # In seeded database, Priya only answered 2 questions (out of 6 assigned)
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")

    r = client.get("/reports/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["answered"] == 2
    # Incomplete diagnostic must return None for growth_insights
    assert r.json()["growth_insights"] is None


def test_only_authenticated_membership_data_included(client):
    headers_priya, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers_priya = get_priya_valid_answers()
    client.post("/diagnostic/submit", json={"answers": answers_priya}, headers=headers_priya)

    r = client.get("/reports/me", headers=headers_priya)
    assert r.status_code == 200
    assert r.json()["growth_insights"] is not None
    # Priya has 6 answers
    assert sum(b["question_count"] for b in r.json()["growth_insights"]["breakdown"]) == 6


def test_multi_organization_isolation(client):
    # Ravi belongs to Northwind (org 1) and Bluepeak (org 2)
    headers_nw, _ = login(client, "ravi@consult.test", "Northwind Logistics")
    headers_bp, _ = login(client, "ravi@consult.test", "Bluepeak Retail")

    # Ravi deletes diagnostic in Bluepeak
    client.delete("/diagnostic/me", headers=headers_bp)
    r_bp = client.get("/reports/me", headers=headers_bp)
    assert r_bp.json()["growth_insights"] is None


def test_growth_insights_disappear_after_deletion(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)

    # Initial check: insights present
    r1 = client.get("/reports/me", headers=headers)
    assert r1.json()["growth_insights"] is not None

    # Delete diagnostic
    r_del = client.delete("/diagnostic/me", headers=headers)
    assert r_del.status_code == 200

    # Subsequent check: insights gone immediately
    r2 = client.get("/reports/me", headers=headers)
    assert r2.json()["growth_insights"] is None


def test_growth_insights_update_after_valid_retake(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers1 = get_priya_valid_answers()
    # In answers1: common-policy is "Yes, and I follow it" (score 4)
    client.post("/diagnostic/submit", json={"answers": answers1}, headers=headers)

    r1 = client.get("/reports/me", headers=headers)
    insights1 = r1.json()["growth_insights"]
    assert insights1 is not None

    # Resubmit with lowest score on common-freq (Never -> score 1)
    answers2 = get_priya_valid_answers()
    answers2[0]["answer"] = "Never"
    client.post("/diagnostic/submit", json={"answers": answers2}, headers=headers)

    r2 = client.get("/reports/me", headers=headers)
    insights2 = r2.json()["growth_insights"]
    assert insights2 is not None
    # Adoption frequency is now the lowest score (1.0)
    assert insights2["improvement_area"]["key"] == "adoption_frequency"
    assert insights2["improvement_area"]["score"] == 1.0


def test_existing_personal_report_data_remaining_correct(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)

    r = client.get("/reports/me", headers=headers)
    data = r.json()
    assert data["name"] == "Priya Nair"
    assert data["organization"] == "Northwind Logistics"
    assert data["answered"] == 6
    assert isinstance(data["average_score"], float)
    assert isinstance(data["level"], str)
    assert isinstance(data["risks"], list)
    assert isinstance(data["next_steps"], list)
    assert "growth_insights" in data


def test_dashboard_privacy_and_authorization_regressions_green(client):
    # Setup an org with 5 members to verify dashboard privacy is unaffected
    org_id, _, emp_ids, admin_headers = setup_org_with_members(num_members=5)
    r = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r.status_code == 200
    # Growth insights are private to employees, never exposed on the admin dashboard
    assert "growth_insights" not in r.json()


def test_all_question_bank_questions_have_explicit_category_mappings():
    """Ensures every question in questions.json has an explicit, valid mapping in QUESTION_CATEGORY_MAP."""
    all_questions = load_questions()
    assert len(all_questions) > 0

    for q in all_questions:
        qid = q["id"]
        assert qid in QUESTION_CATEGORY_MAP, f"Question '{qid}' is missing an explicit mapping in QUESTION_CATEGORY_MAP"
        category = get_question_category(qid)
        assert category in CATEGORIES, f"Mapped category '{category}' for '{qid}' is not in CATEGORIES"


def test_unmapped_question_raises_key_error_instead_of_defaulting():
    """Ensures missing question mapping raises KeyError rather than silently defaulting to practical_application."""
    with pytest.raises(KeyError) as exc_info:
        get_question_category("unknown-future-question-id")
    assert "does not have an explicit competency category mapping" in str(exc_info.value)

    # Calling calculate_growth_insights with an unmapped question ID must also raise KeyError
    expected_questions = [{"id": "unmapped-question-xyz"}]
    responses = [models.Response(question_id="unmapped-question-xyz", score=4.0)]
    with pytest.raises(KeyError) as exc_info2:
        calculate_growth_insights(responses, expected_questions)
    assert "does not have an explicit competency category mapping" in str(exc_info2.value)


def test_incomplete_diagnostic_returns_consistent_unassessed_report(client):
    """Personal report must not show average score or risks for incomplete diagnostics."""
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    r = client.get("/reports/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["answered"] == 2
    assert data["average_score"] is None
    assert data["level"] == "Not assessed"
    assert data["risks"] == []
    assert data["growth_insights"] is None


def test_valid_complete_diagnostic_report(client):
    """Submitting all required valid answers produces a complete report with growth insights."""
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    r_sub = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
    assert r_sub.status_code == 200

    r = client.get("/reports/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["answered"] == 6
    assert isinstance(data["average_score"], float)
    assert data["level"] in ["Exploring", "Practitioner", "Leader"]
    assert isinstance(data["risks"], list)
    assert data["growth_insights"] is not None
    assert len(data["growth_insights"]["breakdown"]) == 4


def test_deleted_diagnostic_report_and_insights_disappear(client):
    """Deleting diagnostic removes answers, scores, risks, and growth insights immediately."""
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)

    # Ensure it's completed first
    r1 = client.get("/reports/me", headers=headers)
    assert r1.json()["growth_insights"] is not None

    # Delete
    r_del = client.delete("/diagnostic/me", headers=headers)
    assert r_del.status_code == 200

    # Ensure it is completely unassessed
    r2 = client.get("/reports/me", headers=headers)
    assert r2.status_code == 200
    data = r2.json()
    assert data["answered"] == 0
    assert data["average_score"] is None
    assert data["level"] == "Not assessed"
    assert data["risks"] == []
    assert data["growth_insights"] is None


def test_retaken_diagnostic_consistently_updates_report_and_dashboard(client):
    """Retaking diagnostic with new answers updates score, risks, and insights without leaving stale records."""
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers1 = get_priya_valid_answers()
    client.post("/diagnostic/submit", json={"answers": answers1}, headers=headers)

    r1 = client.get("/reports/me", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["growth_insights"] is not None

    # Retake with changed answers (change common-freq to Never, which scores 1.0)
    answers2 = get_priya_valid_answers()
    answers2[0]["answer"] = "Never"
    client.post("/diagnostic/submit", json={"answers": answers2}, headers=headers)

    r2 = client.get("/reports/me", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["answered"] == 6
    assert data2["growth_insights"] is not None
    assert data2["growth_insights"]["improvement_area"]["key"] == "adoption_frequency"
    assert data2["growth_insights"]["improvement_area"]["score"] == 1.0


def test_duplicate_responses_handled_by_canonical_deduplication(client):
    """If legacy or duplicated responses exist for a question, the canonical completion logic deduplicates them."""
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    answers = get_priya_valid_answers()
    client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)

    # Manually insert a duplicate response for common-freq into DB
    db = SessionLocal()
    priya = db.query(models.User).filter_by(email="priya@northwind.test").first()
    m = db.query(models.Membership).filter_by(user_id=priya.id, org_id=1).first()

    dup_response = models.Response(
        membership_id=m.id,
        question_id="common-freq",
        answer="Never",
        score=1.0,
        flags=["unreviewed_output"],
    )
    db.add(dup_response)
    db.commit()
    db.close()

    r = client.get("/reports/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    # Stored responses count is 7 due to the injected duplicate
    assert data["answered"] == 7
    # Canonical completion logic evaluated without crashing, growth insights calculated on deduplicated responses
    assert data["growth_insights"] is not None
    assert data["growth_insights"]["improvement_area"]["key"] == "adoption_frequency"
    assert data["growth_insights"]["improvement_area"]["score"] == 1.0

