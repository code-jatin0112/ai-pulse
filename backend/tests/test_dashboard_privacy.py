import pytest
from app.db import SessionLocal
from app import models
from app.auth import hash_password, make_token
from app.services.questions import questions_for


def setup_org_with_members(dept_name="Customer Support", num_members=5):
    """Creates an isolated test organization with an admin and a specified number of employees.

    Returns (org_id, dept_id, employee_membership_ids, admin_auth_headers).
    """
    db = SessionLocal()
    org = models.Organization(name=f"PrivacyOrg_{dept_name}_{num_members}")
    db.add(org)
    db.flush()

    dept = models.Department(org_id=org.id, name=dept_name)
    db.add(dept)
    db.flush()

    # Admin user
    admin_user = models.User(
        name="Admin User",
        email=f"admin_{org.id}@test.privacy",
        password_hash=hash_password("pulse123"),
    )
    db.add(admin_user)
    db.flush()

    admin_membership = models.Membership(
        user_id=admin_user.id,
        org_id=org.id,
        department_id=None,
        role="admin",
        job_role="manager",
        seniority="lead",
    )
    db.add(admin_membership)
    db.flush()

    # Create employee memberships and collect their IDs
    employee_ids = []
    for i in range(num_members):
        u = models.User(
            name=f"Employee {i}",
            email=f"emp_{org.id}_{i}@test.privacy",
            password_hash=hash_password("pulse123"),
        )
        db.add(u)
        db.flush()

        m = models.Membership(
            user_id=u.id,
            org_id=org.id,
            department_id=dept.id,
            role="employee",
            job_role="support",
            seniority="junior",
        )
        db.add(m)
        db.flush()
        employee_ids.append(m.id)

    db.commit()
    token = make_token(admin_user.id, org.id)
    headers = {"Authorization": f"Bearer {token}"}
    org_id = org.id
    dept_id = dept.id
    db.close()
    return org_id, dept_id, employee_ids, headers


def complete_diagnostic_for_employee(membership_id: int, score=4.0, flags=None):
    """Submits answers for all required questions for a support junior (6 questions)."""
    db = SessionLocal()
    m = db.get(models.Membership, membership_id)
    assert m is not None
    assigned_questions = questions_for(m.job_role, m.seniority)
    assert len(assigned_questions) > 0

    for q in assigned_questions:
        resp = models.Response(
            membership_id=m.id,
            question_id=q["id"],
            answer="Valid diagnostic response",
            score=score,
            flags=flags or [],
        )
        db.add(resp)
    db.commit()
    db.close()


def partial_diagnostic_for_employee(membership_id: int, score=3.0, flags=None):
    """Submits an incomplete diagnostic (only 2 out of 6 questions)."""
    db = SessionLocal()
    m = db.get(models.Membership, membership_id)
    assert m is not None
    assigned_questions = questions_for(m.job_role, m.seniority)
    assert len(assigned_questions) > 2

    for q in assigned_questions[:2]:
        resp = models.Response(
            membership_id=m.id,
            question_id=q["id"],
            answer="Partial response",
            score=score,
            flags=flags or [],
        )
        db.add(resp)
    db.commit()
    db.close()


def test_zero_completed_employees_suppressed(client):
    org_id, _, _, headers = setup_org_with_members(num_members=5)
    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["departments"] == []
    assert r.json()["top_risks"] == []


def test_one_completed_employee_suppressed(client):
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=5)
    complete_diagnostic_for_employee(emp_ids[0], score=4.0, flags=["customer_data_shared"])

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    # Suppressed: 1 < 5
    assert r.json()["departments"] == []
    # Risks from suppressed departments must never leak into top_risks
    assert r.json()["top_risks"] == []


def test_four_completed_employees_suppressed(client):
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=6)
    for i in range(4):
        complete_diagnostic_for_employee(emp_ids[i], score=4.0, flags=["unreviewed_output"])

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    # Suppressed: 4 < 5
    assert r.json()["departments"] == []
    assert r.json()["top_risks"] == []


def test_exactly_five_completed_employees_visible(client):
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=5)
    for i in range(5):
        complete_diagnostic_for_employee(emp_ids[i], score=4.0, flags=["customer_data_shared"])

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["departments"]) == 1
    dept = data["departments"][0]
    assert dept["responded"] == 5
    assert dept["employees"] == 5
    assert dept["average_score"] == 4.0
    assert dept["level"] == "Leader"
    assert data["top_risks"] == [["customer_data_shared", 5]]


def test_more_than_five_completed_employees_visible(client):
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=7)
    for i in range(6):
        complete_diagnostic_for_employee(emp_ids[i], score=3.0)

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["departments"]) == 1
    dept = data["departments"][0]
    assert dept["responded"] == 6
    assert dept["employees"] == 7
    assert dept["average_score"] == 3.0
    assert dept["level"] == "Practitioner"


def test_partial_diagnostic_does_not_count_as_completed(client):
    # 4 completed employees + 3 partial employees = 7 respondents, but only 4 completed
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=7)
    for i in range(4):
        complete_diagnostic_for_employee(emp_ids[i], score=4.0)
    for i in range(4, 7):
        partial_diagnostic_for_employee(emp_ids[i], score=2.0)

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    # Must be suppressed because valid completed count is 4 (< 5)
    assert r.json()["departments"] == []
    assert r.json()["top_risks"] == []


def test_duplicate_responses_do_not_inflate_participation_or_score(client):
    # 4 employees complete once, 1 employee submits answers 3 times
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=6)
    for i in range(4):
        complete_diagnostic_for_employee(emp_ids[i], score=4.0)
    # Employee 0 submits 2 more times (duplicates)
    complete_diagnostic_for_employee(emp_ids[0], score=4.0)
    complete_diagnostic_for_employee(emp_ids[0], score=4.0)

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    # Must still be suppressed because distinct completed employees is 4 (< 5)
    assert r.json()["departments"] == []


def test_hidden_groups_do_not_contribute_to_disclosed_risk_totals(client):
    db = SessionLocal()
    org = models.Organization(name="DualDeptOrg")
    db.add(org)
    db.flush()

    admin = models.User(name="DualAdmin", email="dual_admin@test.privacy", password_hash=hash_password("pulse123"))
    db.add(admin)
    db.flush()
    db.add(models.Membership(user_id=admin.id, org_id=org.id, role="admin", job_role="manager", seniority="lead"))

    # Dept A: 5 completers (visible), has "policy_unaware" flag
    dept_a = models.Department(org_id=org.id, name="LargeDept")
    db.add(dept_a)
    db.flush()

    # Dept B: 2 completers (suppressed), has "confidential_data_shared" flag
    dept_b = models.Department(org_id=org.id, name="SmallDept")
    db.add(dept_b)
    db.flush()

    db.commit()

    # Setup 5 completers in Dept A
    for i in range(5):
        u = models.User(name=f"UserA_{i}", email=f"a_{i}@test.privacy", password_hash=hash_password("pulse123"))
        db.add(u)
        db.flush()
        m = models.Membership(user_id=u.id, org_id=org.id, department_id=dept_a.id, role="employee", job_role="support", seniority="junior")
        db.add(m)
        db.commit()
        complete_diagnostic_for_employee(m.id, score=4.0, flags=["policy_unaware"])

    # Setup 2 completers in Dept B (suppressed)
    for i in range(2):
        u = models.User(name=f"UserB_{i}", email=f"b_{i}@test.privacy", password_hash=hash_password("pulse123"))
        db.add(u)
        db.flush()
        m = models.Membership(user_id=u.id, org_id=org.id, department_id=dept_b.id, role="employee", job_role="support", seniority="junior")
        db.add(m)
        db.commit()
        complete_diagnostic_for_employee(m.id, score=2.0, flags=["confidential_data_shared"])

    token = make_token(admin.id, org.id)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/dashboard?org_id={org.id}", headers=headers)
    assert r.status_code == 200
    data = r.json()

    # Dept A is visible, Dept B is suppressed
    assert len(data["departments"]) == 1
    assert data["departments"][0]["department"] == "LargeDept"

    # Only Dept A's risks appear; Dept B's "confidential_data_shared" is completely hidden
    risk_names = [r[0] for r in data["top_risks"]]
    assert "policy_unaware" in risk_names
    assert "confidential_data_shared" not in risk_names
    db.close()


def test_scores_remain_in_valid_range_between_1_and_5(client):
    org_id, _, emp_ids, headers = setup_org_with_members(num_members=5)
    # Varying valid scores: 1.0, 2.0, 3.0, 4.0, 5.0
    for i, s in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
        complete_diagnostic_for_employee(emp_ids[i], score=s)

    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["departments"]) == 1
    dept = data["departments"][0]
    avg = dept["average_score"]
    assert 1.0 <= avg <= 5.0
    assert avg == 3.0
    assert dept["level"] == "Practitioner"


def test_admin_cannot_bypass_privacy_by_requesting_another_org(client):
    org1_id, _, _, headers1 = setup_org_with_members(dept_name="Org1Support", num_members=5)
    org2_id, _, _, _ = setup_org_with_members(dept_name="Org2Support", num_members=5)

    # Admin from Org 1 attempts to request Org 2 dashboard
    r = client.get(f"/dashboard?org_id={org2_id}", headers=headers1)
    assert r.status_code == 403
    assert "Not authorized for this organization" in r.json()["detail"]
