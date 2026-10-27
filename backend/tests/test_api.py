from tests.conftest import login


def test_login_lists_organizations(client):
    _, data = login(client, "ravi@consult.test")
    names = {o["org_name"] for o in data["organizations"]}
    assert names == {"Northwind Logistics", "Bluepeak Retail"}


def test_employee_sees_questions(client):
    headers, _ = login(client, "priya@northwind.test", "Northwind Logistics")
    r = client.get("/diagnostic/questions", headers=headers)
    assert r.status_code == 200
    assert any(q["id"] == "sup-drafts" for q in r.json())


def test_admin_dashboard(client):
    headers, data = login(client, "asha@northwind.test", "Northwind Logistics")
    org_id = data["organizations"][0]["org_id"]
    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["organization"] == "Northwind Logistics"
    # Seeded demo data has no department with >= 5 completers, so all departments are safely suppressed
    assert len(r.json()["departments"]) == 0
    assert r.json()["top_risks"] == []



def test_admin_cannot_see_other_org(client):
    headers, _ = login(client, "asha@northwind.test", "Northwind Logistics")
    r = client.get("/dashboard?org_id=2", headers=headers)
    assert r.status_code == 403
    assert "Not authorized for this organization" in r.json()["detail"]


def test_employee_cannot_see_admin_dashboard(client):
    headers, data = login(client, "priya@northwind.test", "Northwind Logistics")
    org_id = data["organizations"][0]["org_id"]
    r = client.get(f"/dashboard?org_id={org_id}", headers=headers)
    assert r.status_code == 403
    assert "Admins only" in r.json()["detail"]


def test_user_cannot_select_unaffiliated_org(client):
    # Priya only belongs to Northwind (org 1), attempts to select Bluepeak (org 2)
    r = client.post("/auth/login", json={"email": "priya@northwind.test", "password": "pulse123"})
    token = r.json()["token"]
    r_select = client.post(
        "/auth/select-org",
        json={"org_id": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_select.status_code == 403
    assert "Not a member of this organization" in r_select.json()["detail"]


def test_multi_org_user_role_isolation(client):
    # Ravi is employee at Northwind (org 1), admin at Bluepeak (org 2)
    # When scoped to Northwind (as employee)
    nw_headers, _ = login(client, "ravi@consult.test", "Northwind Logistics")
    # Cannot view Northwind dashboard (employee)
    r_nw_self = client.get("/dashboard?org_id=1", headers=nw_headers)
    assert r_nw_self.status_code == 403
    assert "Admins only" in r_nw_self.json()["detail"]
    # Cannot view Bluepeak dashboard using Northwind token
    r_nw_bp = client.get("/dashboard?org_id=2", headers=nw_headers)
    assert r_nw_bp.status_code == 403

    # When scoped to Bluepeak (as admin)
    bp_headers, _ = login(client, "ravi@consult.test", "Bluepeak Retail")
    # Can view Bluepeak dashboard (authorized admin)
    r_bp_self = client.get("/dashboard?org_id=2", headers=bp_headers)
    assert r_bp_self.status_code == 200
    assert r_bp_self.json()["organization"] == "Bluepeak Retail"
    # Seeded data has < 5 completers per department in Bluepeak, so all are suppressed
    assert len(r_bp_self.json()["departments"]) == 0
    # Cannot view Northwind dashboard using Bluepeak admin token
    r_bp_nw = client.get("/dashboard?org_id=1", headers=bp_headers)
    assert r_bp_nw.status_code == 403
    assert "Not authorized for this organization" in r_bp_nw.json()["detail"]


