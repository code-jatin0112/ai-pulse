from app.services.questions import questions_for


def ids(qs):
    return {q["id"] for q in qs}


def test_everyone_gets_common_questions():
    got = ids(questions_for("sales", "junior"))
    assert {"common-freq", "common-policy", "common-data", "common-review", "common-open"} <= got


def test_junior_engineer_does_not_get_senior_questions():
    got = ids(questions_for("engineering", "junior"))
    assert "eng-assistant" in got
    assert "eng-review" not in got
    assert "eng-arch" not in got


def test_senior_support_gets_escalation_question():
    assert "sup-escalation" in ids(questions_for("support", "senior"))


def test_lead_manager_gets_policy_questions():
    got = ids(questions_for("manager", "lead"))
    assert "mgr-policy" in got
    assert "mgr-open" in got


def test_seniority_ladder_for_engineering():
    # Junior: assistant only
    junior_ids = ids(questions_for("engineering", "junior"))
    assert "eng-assistant" in junior_ids
    assert "eng-review" not in junior_ids
    assert "eng-arch" not in junior_ids

    # Mid: assistant + review, but not arch
    mid_ids = ids(questions_for("engineering", "mid"))
    assert "eng-assistant" in mid_ids
    assert "eng-review" in mid_ids
    assert "eng-arch" not in mid_ids

    # Senior: assistant + review + arch
    senior_ids = ids(questions_for("engineering", "senior"))
    assert "eng-assistant" in senior_ids
    assert "eng-review" in senior_ids
    assert "eng-arch" in senior_ids

    # Lead: inherits all senior tier questions
    lead_ids = ids(questions_for("engineering", "lead"))
    assert "eng-assistant" in lead_ids
    assert "eng-review" in lead_ids
    assert "eng-arch" in lead_ids


def test_unknown_seniority_gets_common_questions_only():
    common_ids = {"common-freq", "common-policy", "common-data", "common-review", "common-open"}
    got = ids(questions_for("engineering", "unknown"))
    assert common_ids <= got
    assert "eng-assistant" not in got
    assert "eng-review" not in got
    assert "eng-arch" not in got


def test_role_filtering_isolates_questions_between_roles():
    eng_lead = ids(questions_for("engineering", "lead"))
    assert "eng-assistant" in eng_lead
    # Ensure no sales, support, or manager specific questions leak in
    assert "sales-outreach" not in eng_lead
    assert "sales-crm" not in eng_lead
    assert "sup-drafts" not in eng_lead
    assert "sup-escalation" not in eng_lead
    assert "mgr-adoption" not in eng_lead
    assert "mgr-policy" not in eng_lead

