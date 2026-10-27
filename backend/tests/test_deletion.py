import pytest
from app.db import SessionLocal
from app import models
from app.auth import hash_password, make_token
from tests.conftest import login
from tests.test_dashboard_privacy import (
    setup_org_with_members,
    complete_diagnostic_for_employee,
)


def test_employee_successfully_deletes_own_answers(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")

    # Priya has 2 seeded responses
    db = SessionLocal()
    priya_user = db.query(models.User).filter_by(email="priya@northwind.test").first()
    priya_m = db.query(models.Membership).filter_by(user_id=priya_user.id).first()
    priya_m_id = priya_m.id
    before_count = db.query(models.Response).filter_by(membership_id=priya_m_id).count()
    assert before_count == 2
    db.close()

    r = client.delete("/diagnostic/me", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "deleted": 2}

    # Verify rows are deleted in database
    db = SessionLocal()
    after_count = db.query(models.Response).filter_by(membership_id=priya_m_id).count()
    assert after_count == 0
    db.close()


def test_personal_report_empty_after_deletion(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    client.delete("/diagnostic/me", headers=headers)

    r = client.get("/reports/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["answered"] == 0
    assert data["average_score"] is None
    assert data["level"] == "Not assessed"
    assert data["risks"] == []


def test_repeated_deletion_succeeds_safely(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    r1 = client.delete("/diagnostic/me", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["deleted"] == 2

    # Second deletion is idempotent: deletes 0, returns 200
    r2 = client.delete("/diagnostic/me", headers=headers)
    assert r2.status_code == 200
    assert r2.json() == {"status": "ok", "deleted": 0}


def test_unauthenticated_deletion_rejected(client):
    # Missing token
    r1 = client.delete("/diagnostic/me")
    assert r1.status_code == 401
    assert "Missing token" in r1.json()["detail"]

    # Unscoped token (no org selected)
    r_login = client.post("/auth/login", json={"email": "priya@northwind.test", "password": "pulse123"})
    unscoped_token = r_login.json()["token"]
    r2 = client.delete("/diagnostic/me", headers={"Authorization": f"Bearer {unscoped_token}"})
    assert r2.status_code == 400
    assert "Select an organization first" in r2.json()["detail"]


def test_one_employee_cannot_delete_another_employee_records(client):
    priya_headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")

    db = SessionLocal()
    vikram_user = db.query(models.User).filter_by(email="vikram@northwind.test").first()
    vikram_m = db.query(models.Membership).filter_by(user_id=vikram_user.id).first()
    vikram_m_id = vikram_m.id
    vikram_before = db.query(models.Response).filter_by(membership_id=vikram_m_id).count()
    assert vikram_before == 2
    db.close()

    # Priya deletes her diagnostic data
    r = client.delete("/diagnostic/me", headers=priya_headers)
    assert r.status_code == 200

    # Vikram's responses remain completely untouched
    db = SessionLocal()
    vikram_after = db.query(models.Response).filter_by(membership_id=vikram_m_id).count()
    assert vikram_after == 2
    db.close()


def test_deletion_in_org_a_preserves_same_user_records_in_org_b(client):
    # Ravi belongs to both Northwind (org 1) and Bluepeak (org 2)
    db = SessionLocal()
    ravi = db.query(models.User).filter_by(email="ravi@consult.test").first()
    m_nw = db.query(models.Membership).filter_by(user_id=ravi.id, org_id=1).first()
    m_bp = db.query(models.Membership).filter_by(user_id=ravi.id, org_id=2).first()
    m_nw_id = m_nw.id
    m_bp_id = m_bp.id

    # Add 1 response for Ravi in Northwind and 1 in Bluepeak
    db.add(models.Response(membership_id=m_nw_id, question_id="common-freq", answer="Daily", score=4.0))
    db.add(models.Response(membership_id=m_bp_id, question_id="common-freq", answer="Weekly", score=3.0))
    db.commit()
    db.close()

    # Ravi logs into Northwind and deletes
    nw_headers, _ = login(client, "ravi@consult.test", "Northwind Logistics")
    r_del = client.delete("/diagnostic/me", headers=nw_headers)
    assert r_del.status_code == 200
    assert r_del.json()["deleted"] == 1

    # Verify Northwind response is gone, but Bluepeak response is preserved
    db = SessionLocal()
    nw_count = db.query(models.Response).filter_by(membership_id=m_nw_id).count()
    bp_count = db.query(models.Response).filter_by(membership_id=m_bp_id).count()
    assert nw_count == 0
    assert bp_count == 1
    db.close()


def test_deletion_preserves_other_employees_records(client):
    org_id, _, emp_ids, _ = setup_org_with_members(num_members=3)
    complete_diagnostic_for_employee(emp_ids[0], score=4.0)
    complete_diagnostic_for_employee(emp_ids[1], score=3.0)

    # Emp 0 logs in and deletes
    db = SessionLocal()
    m0 = db.get(models.Membership, emp_ids[0])
    token0 = make_token(m0.user_id, org_id)
    headers0 = {"Authorization": f"Bearer {token0}"}
    db.close()

    r = client.delete("/diagnostic/me", headers=headers0)
    assert r.status_code == 200

    # Emp 1's responses are completely preserved
    db = SessionLocal()
    emp0_count = db.query(models.Response).filter_by(membership_id=emp_ids[0]).count()
    emp1_count = db.query(models.Response).filter_by(membership_id=emp_ids[1]).count()
    assert emp0_count == 0
    assert emp1_count > 0
    db.close()


def test_dashboard_analytics_updates_immediately_after_deletion(client):
    # 6 completed employees
    org_id, _, emp_ids, admin_headers = setup_org_with_members(num_members=6)
    for i in range(6):
        complete_diagnostic_for_employee(emp_ids[i], score=4.0)

    # Initial dashboard check: 6 completers
    r_before = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r_before.status_code == 200
    assert r_before.json()["departments"][0]["responded"] == 6

    # Employee 0 deletes their diagnostic
    db = SessionLocal()
    m0 = db.get(models.Membership, emp_ids[0])
    token0 = make_token(m0.user_id, org_id)
    headers0 = {"Authorization": f"Bearer {token0}"}
    db.close()

    r_del = client.delete("/diagnostic/me", headers=headers0)
    assert r_del.status_code == 200

    # Dashboard requested immediately: drops to 5 completers
    r_after = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r_after.status_code == 200
    assert r_after.json()["departments"][0]["responded"] == 5


def test_five_completers_drops_to_four_and_causes_privacy_suppression(client):
    # Exactly 5 completed employees
    org_id, _, emp_ids, admin_headers = setup_org_with_members(num_members=5)
    for i in range(4):
        complete_diagnostic_for_employee(emp_ids[i], score=4.0)
    # Emp 4 has a unique risk flag
    complete_diagnostic_for_employee(emp_ids[4], score=4.0, flags=["customer_data_shared"])

    # Dashboard is visible with 5 completers
    r1 = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r1.status_code == 200
    assert len(r1.json()["departments"]) == 1
    assert r1.json()["departments"][0]["responded"] == 5
    assert r1.json()["top_risks"] == [["customer_data_shared", 1]]

    # Emp 4 deletes their data
    db = SessionLocal()
    m4 = db.get(models.Membership, emp_ids[4])
    token4 = make_token(m4.user_id, org_id)
    headers4 = {"Authorization": f"Bearer {token4}"}
    db.close()

    r_del = client.delete("/diagnostic/me", headers=headers4)
    assert r_del.status_code == 200

    # Dashboard requested immediately: only 4 completers remain (< 5)
    # The department must now be suppressed and risks hidden!
    r2 = client.get(f"/dashboard?org_id={org_id}", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["departments"] == []
    assert r2.json()["top_risks"] == []


def test_diagnostic_resubmission_after_deletion(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")

    # Delete existing responses
    r_del = client.delete("/diagnostic/me", headers=headers)
    assert r_del.status_code == 200

    # Verify report is empty
    r_rep1 = client.get("/reports/me", headers=headers)
    assert r_rep1.json()["answered"] == 0

    # Resubmit diagnostic answers with exact option text matching questions.json
    submission = {
        "answers": [
            {"question_id": "common-freq", "answer": "Daily"},
            {"question_id": "common-policy", "answer": "Yes, and I follow it"},
            {"question_id": "common-data", "answer": "Always, and I know which tools are approved"},
            {"question_id": "common-review", "answer": "Check facts and edit it"},
            {"question_id": "common-open", "answer": "Wrote automation scripts using AI with code review."},
            {"question_id": "sup-drafts", "answer": "To draft replies and summarise ticket history"},
        ]
    }
    r_sub = client.post("/diagnostic/submit", json=submission, headers=headers)
    assert r_sub.status_code == 200
    assert r_sub.json()["saved"] == 6

    # Verify report reflects newly submitted diagnostic
    r_rep2 = client.get("/reports/me", headers=headers)
    assert r_rep2.status_code == 200
    assert r_rep2.json()["answered"] == 6
    assert r_rep2.json()["average_score"] is not None
    assert r_rep2.json()["level"] != "Not assessed"
