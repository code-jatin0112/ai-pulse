"""Safe, isolated privacy threshold demonstration for AI Pulse.

Demonstrates the 5-completer privacy rule using an isolated temporary SQLite database:
1. 4 completers: Department scores and risk tags are completely suppressed.
2. 5 completers: Department scores, maturity level, and aggregate risks become visible.
3. Right to delete (5 -> 4): 5th employee deletes their data; department immediately re-suppresses.

Usage:
    cd backend
    .venv/bin/python3 scripts/demo_privacy.py

Does NOT modify or overwrite the main aipulse.db database.
"""
import os
import sys
import tempfile

# Ensure app package is importable
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app import models
from app.auth import hash_password, make_token
from app.services.questions import questions_for


def run_privacy_demo(persist_path: str | None = None):
    # Use isolated temporary database
    if persist_path:
        db_path = persist_path
        cleanup = False
    else:
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = temp_file.name
        temp_file.close()
        cleanup = True

    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Recreate tables in isolated database
    Base.metadata.create_all(bind=engine)

    # Override database dependency for FastAPI app
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = TestingSessionLocal()
    try:
        print("=====================================================================")
        print("         AI PULSE PRIVACY DEMONSTRATION (ISOLATED DATABASE)          ")
        print("=====================================================================")
        print(f"Isolated DB: {db_path}\n")

        # 1. Seed isolated organization and department
        org = models.Organization(name="Apex Solutions")
        db.add(org)
        db.flush()

        dept = models.Department(org_id=org.id, name="Customer Operations")
        db.add(dept)
        db.flush()

        admin_user = models.User(
            name="Alice Vance (Admin)",
            email="admin@apex.test",
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

        # Create 5 employees in Customer Operations
        employees = []
        for i in range(1, 6):
            u = models.User(
                name=f"Worker {i}",
                email=f"worker{i}@apex.test",
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
            employees.append((u, m))

        db.commit()

        admin_token = make_token(admin_user.id, org.id)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        assigned_questions = questions_for("support", "junior")

        def submit_diagnostic(user, membership, score=4.0):
            token = make_token(user.id, org.id)
            headers = {"Authorization": f"Bearer {token}"}
            answers = [
                {"question_id": "common-freq", "answer": "Daily"},
                {"question_id": "common-policy", "answer": "Yes, and I follow it"},
                {"question_id": "common-data", "answer": "Always, and I know which tools are approved"},
                {"question_id": "common-review", "answer": "Check facts and edit it"},
                {"question_id": "common-open", "answer": "Used ChatGPT to draft 20 follow-up emails and edited each one."},
                {"question_id": "sup-drafts", "answer": "To draft replies and summarise ticket history"},
            ]
            resp = client.post("/diagnostic/submit", json={"answers": answers}, headers=headers)
            assert resp.status_code == 200, f"Submit failed: {resp.text}"
            return headers

        print("---------------------------------------------------------------------")
        print("STAGE 1: 4 Out of 5 Employees Complete Diagnostic (< 5 Threshold)")
        print("---------------------------------------------------------------------")
        for i in range(4):
            u, m = employees[i]
            submit_diagnostic(u, m)
            print(f"  [+] {u.name} submitted diagnostic.")

        r1 = client.get(f"/dashboard?org_id={org.id}", headers=admin_headers)
        assert r1.status_code == 200
        d1 = r1.json()

        print("\n  >> Admin Dashboard Query Result:")
        print(f"     - Organization: {d1['organization']}")
        print(f"     - Visible Departments: {len(d1['departments'])}")
        print(f"     - Top Risks: {d1['top_risks']}")
        print("  >> PRIVACY CHECK: Department is completely HIDDEN (below 5 completers).\n")
        assert len(d1["departments"]) == 0
        assert len(d1["top_risks"]) == 0

        print("---------------------------------------------------------------------")
        print("STAGE 2: 5th Employee Completes Diagnostic (>= 5 Threshold Met)")
        print("---------------------------------------------------------------------")
        u5, m5 = employees[4]
        w5_headers = submit_diagnostic(u5, m5)
        print(f"  [+] {u5.name} submitted diagnostic. Total completers = 5.")

        r2 = client.get(f"/dashboard?org_id={org.id}", headers=admin_headers)
        assert r2.status_code == 200
        d2 = r2.json()

        print("\n  >> Admin Dashboard Query Result:")
        print(f"     - Organization: {d2['organization']}")
        print(f"     - Visible Departments: {len(d2['departments'])}")
        dept_summary = d2["departments"][0]
        print(f"     - Department: {dept_summary['department']}")
        print(f"     - Completers: {dept_summary['responded']} / {dept_summary['employees']}")
        print(f"     - Average Score: {dept_summary['average_score']} ({dept_summary['level']})")
        print(f"     - Top Risks: {d2['top_risks']}")
        print("  >> PRIVACY CHECK: Department results UNMASKED at 5 completers.\n")
        assert len(d2["departments"]) == 1
        assert dept_summary["responded"] == 5

        print("---------------------------------------------------------------------")
        print("STAGE 3: 5th Employee Exercises Right to Delete (Completers 5 -> 4)")
        print("---------------------------------------------------------------------")
        r_del = client.delete("/diagnostic/me", headers=w5_headers)
        assert r_del.status_code == 200
        print(f"  [-] {u5.name} deleted their diagnostic. Deleted rows: {r_del.json()['deleted']}.")

        r3 = client.get(f"/dashboard?org_id={org.id}", headers=admin_headers)
        assert r3.status_code == 200
        d3 = r3.json()

        print("\n  >> Admin Dashboard Query Result:")
        print(f"     - Organization: {d3['organization']}")
        print(f"     - Visible Departments: {len(d3['departments'])}")
        print(f"     - Top Risks: {d3['top_risks']}")
        print("  >> PRIVACY CHECK: Department is IMMEDIATELY RE-SUPPRESSED (dropped below 5).\n")
        assert len(d3["departments"]) == 0
        assert len(d3["top_risks"]) == 0

        print("=====================================================================")
        print("    SUCCESS: PRIVACY THRESHOLD BEHAVIOR FULLY DEMONSTRATED!         ")
        print("=====================================================================")

    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        if cleanup and os.path.exists(db_path):
            os.remove(db_path)
            print(f"Disposable database {db_path} cleaned up safely.")


if __name__ == "__main__":
    persist_arg = None
    if len(sys.argv) > 1 and sys.argv[1] == "--persist":
        persist_arg = os.path.join(backend_dir, "privacy_demo.db")
    run_privacy_demo(persist_arg)

