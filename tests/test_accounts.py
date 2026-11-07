"""Sign-in throttling, password changes, admin user management and the dashboard overview."""
import api
from tests.test_api import PASSWORD, approve, generate, sign_in, upload_two_page_pdf
from tests.test_api import client as client  # noqa: F401  (the shared fixture)


def users(client):
    return {u["username"]: u for u in client.get("/api/users", headers=client.admin).json()["users"]}


def test_repeated_wrong_passwords_are_throttled_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(api, "LOGIN_MAX_FAILURES", 3)
    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "rita", "password": "wrong-password"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"username": "rita", "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    # Another account is not blocked by rita's failures (the per-client limit is higher).
    assert client.post("/api/auth/login", json={"username": "rob", "password": PASSWORD}).status_code == 200


def test_a_successful_sign_in_clears_the_failures(client, monkeypatch):
    monkeypatch.setattr(api, "LOGIN_MAX_FAILURES", 3)
    for _ in range(2):
        client.post("/api/auth/login", json={"username": "rita", "password": "wrong-password"})
    sign_in(client, "rita")
    for _ in range(2):
        assert client.post("/api/auth/login", json={"username": "rita", "password": "wrong"}).status_code == 401


def test_wrong_approval_signatures_are_throttled_too(client, monkeypatch):
    monkeypatch.setattr(api, "LOGIN_MAX_FAILURES", 2)
    doc_id = upload_two_page_pdf(client)
    version = generate(client, doc_id, description="use torque 20Nm").json()
    url = f"/api/versions/{version['version_id']}/reviews"
    for _ in range(2):
        response = client.post(url, data={"decision": "approved", "feedback": "ok", "password": "guess-guess"},
                               headers=client.reviewer)
        assert response.status_code == 403
    response = client.post(url, data={"decision": "approved", "feedback": "ok", "password": PASSWORD},
                           headers=client.reviewer)
    assert response.status_code == 429


def test_changing_your_password_ends_old_sessions_and_is_audited(client):
    old = sign_in(client, "rob")
    wrong = client.post("/api/auth/password", json={"current_password": "nope-nope-nope", "new_password": "x" * 12},
                        headers=old)
    assert wrong.status_code == 403
    short = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"},
                        headers=old)
    assert short.status_code == 400
    changed = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "a-new-password-42"},
                          headers=old)
    assert changed.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401  # the old token stopped working
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).json()["username"] == "rob"
    assert client.post("/api/auth/login", json={"username": "rob", "password": PASSWORD}).status_code == 401
    sign_in(client, "rob", "a-new-password-42")
    events = client.get("/api/audit", headers=client.admin).json()["events"]
    assert events[0]["action"] == "password_changed" and "a-new-password-42" not in str(events[0])
    assert client.get("/api/audit/verify").json()["ok"] is True


def test_admin_changes_roles_and_resets_passwords(client):
    rob = users(client)["rob"]
    url = f"/api/users/{rob['id']}"
    assert client.patch(url, json={"role": "author"}).status_code == 403  # alice is not admin
    assert client.patch(url, json={"role": "boss"}, headers=client.admin).status_code == 400
    assert client.patch(url, json={}, headers=client.admin).status_code == 400
    assert client.patch(url, json={"role": "author"}, headers=client.admin).json()["role"] == "author"
    assert client.patch(url, json={"password": "reset-password-1"}, headers=client.admin).status_code == 200
    sign_in(client, "rob", "reset-password-1")
    assert client.patch("/api/users/missing", json={"role": "author"}, headers=client.admin).status_code == 404
    actions = [e["action"] for e in client.get("/api/audit", headers=client.admin).json()["events"][:2]]
    assert actions == ["user_password_reset", "user_role_changed"]


def test_the_last_admin_cannot_be_demoted(client):
    admin = users(client)["admin"]
    response = client.patch(f"/api/users/{admin['id']}", json={"role": "reviewer"}, headers=client.admin)
    assert response.status_code == 409
    rita = users(client)["rita"]
    client.patch(f"/api/users/{rita['id']}", json={"role": "admin"}, headers=client.admin)
    assert client.patch(f"/api/users/{admin['id']}", json={"role": "reviewer"},
                        headers=client.admin).json()["role"] == "reviewer"


def test_overview_counts_and_review_queue(client):
    assert client.get("/api/overview", headers={"Authorization": ""}).status_code == 401
    empty = client.get("/api/overview").json()
    assert empty["documents"] == 0 and empty["versions"] == 0 and empty["awaiting_review"] == []
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="use torque 20Nm").json()
    generate(client, doc_id, description="use torque 25Nm")
    approve(client, v1["version_id"])
    data = client.get("/api/overview").json()
    assert data["documents"] == 1 and data["versions"] == 2
    assert data["versions_by_status"] == {"approved": 1, "draft": 1}
    assert sum(data["versions_by_evaluation"].values()) == 2
    assert [item["version_number"] for item in data["awaiting_review"]] == [2]
    assert data["recent_decisions"][0]["decision"] == "approved"

