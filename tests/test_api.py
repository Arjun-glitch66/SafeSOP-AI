"""End-to-end API tests with Gemini stubbed and a temporary database."""
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pymupdf
import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(api, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path / "originals")
    (tmp_path / "originals").mkdir()

    prompts = []

    def fake_generate_sop(original_text, change_request, output_scope, target_page):
        prompts.append(original_text)
        return {"text": f"DRAFT:\nREVISED ({output_scope}) {change_request}", "model": "stub-model",
                "prompt_version": "test", "input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr(api, "generate_sop", fake_generate_sop)
    monkeypatch.setattr(api, "BCRYPT_ROUNDS", 4)  # fast hashing in tests only
    monkeypatch.setattr(api, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(api, "ADMIN_PASSWORD", ADMIN_PASSWORD)
    with TestClient(api.app) as test_client:
        test_client.prompts = prompts
        test_client.admin = sign_in(test_client, "admin", ADMIN_PASSWORD)
        for name, role in (("alice", "author"), ("rita", "reviewer"), ("rob", "reviewer")):
            created = test_client.post("/api/users", json={"username": name, "password": PASSWORD, "role": role},
                                       headers=test_client.admin)
            assert created.status_code == 200, created.text
        test_client.reviewer = sign_in(test_client, "rita")
        test_client.headers.update(sign_in(test_client, "alice"))  # requests default to the author
        yield test_client


ADMIN_PASSWORD = "admin-password-123"
PASSWORD = "correct-horse-battery"


def sign_in(client, username, password=PASSWORD):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload_two_page_pdf(client):
    pdf = pymupdf.open()
    for text in ("PAGE ONE: WARNING disconnect power", "PAGE TWO: open the cover"):
        pdf.new_page().insert_text((72, 72), text)
    response = client.post("/api/documents/upload",
                           files={"file": ("Arjun 1.pdf", pdf.tobytes(), "application/pdf")})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def generate(client, doc_id, **data):
    return client.post(f"/api/documents/{doc_id}/generate", data={"scope": "full", **data})


def original_hash(doc_id):
    return hashlib.sha256((api.UPLOAD_DIR / f"{doc_id}.pdf").read_bytes()).hexdigest()


def test_upload_rejects_non_pdf(client):
    response = client.post("/api/documents/upload", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 400


def test_every_generation_reads_the_original_and_never_changes_it(client):
    doc_id = upload_two_page_pdf(client)
    before = original_hash(doc_id)

    v1 = generate(client, doc_id, description="use torque 20Nm").json()
    v2 = generate(client, doc_id, description="add gloves", scope="page", target_page=2).json()
    v3 = generate(client, doc_id, description="regen", parent_version_id=v1["version_id"]).json()

    assert [v["version_number"] for v in (v1, v2, v3)] == [1, 2, 3]
    assert v3["parent_version_id"] == v1["version_id"]
    assert "PAGE ONE" in client.prompts[0] and "PAGE TWO" in client.prompts[0]
    assert "PAGE TWO" in client.prompts[1] and "PAGE ONE" not in client.prompts[1]
    assert not any("REVISED" in prompt for prompt in client.prompts)
    assert original_hash(doc_id) == before


def test_generation_rejects_bad_input(client):
    doc_id = upload_two_page_pdf(client)
    assert generate(client, doc_id, description="x", scope="page", target_page=9).status_code == 400
    assert generate(client, doc_id, description="x", parent_version_id="nope").status_code == 400
    assert generate(client, doc_id, description="   ").status_code == 400
    assert generate(client, "missing-doc", description="x").status_code == 404


def test_generator_config_error_is_reported_without_creating_a_version(client, monkeypatch):
    doc_id = upload_two_page_pdf(client)

    def broken(**kwargs):
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    monkeypatch.setattr(api, "generate_sop", broken)
    response = generate(client, doc_id, description="x")
    assert response.status_code == 502
    assert "GEMINI_API_KEY is not configured" in response.json()["detail"]
    assert client.get(f"/api/documents/{doc_id}/versions").json()["versions"] == []


def test_version_listing_content_and_download(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="use torque 20Nm").json()
    v2 = generate(client, doc_id, description="add gloves", scope="page", target_page=2).json()

    versions = client.get(f"/api/documents/{doc_id}/versions").json()["versions"]
    assert [v["version_number"] for v in versions] == [2, 1]
    latest = versions[0]
    assert (latest["change_request"], latest["scope"], latest["target_page"]) == ("add gloves", "page", 2)
    assert (latest["model"], latest["source_document_id"]) == ("stub-model", doc_id)

    assert "torque 20Nm" in client.get(f"/api/versions/{v1['version_id']}/content").json()["content"]
    download = client.get(f"/api/versions/{v2['version_id']}/download")
    assert download.status_code == 200 and "add gloves" in download.text
    assert client.get("/api/documents").json()["documents"][0]["version_count"] == 2


def test_evaluation_runs_on_generation_and_can_be_rerun(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="use torque 20Nm").json()
    generate(client, doc_id, description="add gloves", scope="page", target_page=2)

    # The stub draft drops the source warning, so the evaluator must fail it.
    assert v1["safety_evaluation"]["status"] == "fail"
    assert any(f["type"] == "missing_warning" for f in v1["safety_evaluation"]["findings"])
    assert client.post(f"/api/versions/{v1['version_id']}/evaluate").json()["status"] == "fail"

    evaluations = client.get(f"/api/versions/{v1['version_id']}/evaluations").json()["evaluations"]
    assert len(evaluations) == 2 and evaluations[0]["metrics"]["source_warnings"] == 1

    statuses = {v["version_number"]: v["evaluation_status"]
                for v in client.get(f"/api/documents/{doc_id}/versions").json()["versions"]}
    # Page 2 has no warnings or numbered steps: uncertain, never a pass.
    assert statuses == {1: "fail", 2: "needs_review"}


def test_review_decision_changes_only_that_version(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="a").json()
    v2 = generate(client, doc_id, description="b").json()

    url = f"/api/versions/{v1['version_id']}/reviews"
    assert client.post(url, data={"decision": "lgtm"}, headers=client.reviewer).status_code == 400
    assert client.post(url, data={"decision": "needs_revision", "feedback": "check torque"},
                       headers=client.reviewer).status_code == 200
    review = client.get(url).json()["reviews"][0]
    assert (review["feedback"], review["reviewer"]) == ("check torque", "rita")

    statuses = {v["id"]: v["status"] for v in client.get(f"/api/documents/{doc_id}/versions").json()["versions"]}
    assert statuses == {v1["version_id"]: "needs_revision", v2["version_id"]: "draft"}


def test_diff_compares_original_with_draft_section(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="use torque 20Nm").json()

    diff = client.get(f"/api/versions/{v1['version_id']}/diff").json()
    original = [line for block in diff["blocks"] for line in block["original"]]
    draft = [line for block in diff["blocks"] for line in block["draft"]]
    assert any("PAGE ONE" in line for line in original)
    assert draft == ["REVISED (full) use torque 20Nm"]  # only the DRAFT section, not the header
    assert diff["source_warnings"] == ["PAGE ONE: WARNING disconnect power"]


def test_pdf_download_is_a_labelled_draft(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="use torque 20Nm").json()

    response = client.get(f"/api/versions/{v1['version_id']}/download?format=pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    with pymupdf.open(stream=response.content, filetype="pdf") as pdf:
        text = pdf[0].get_text()
    assert "AI-GENERATED DRAFT" in text and "Automated check: fail" in text and "torque 20Nm" in text
    assert client.get(f"/api/versions/{v1['version_id']}/download?format=doc").status_code == 400


def test_document_details_include_page_count_but_not_server_path(client):
    doc_id = upload_two_page_pdf(client)
    details = client.get(f"/api/documents/{doc_id}").json()
    assert details["page_count"] == 2 and "stored_path" not in details


def test_approval_needs_justification_when_checks_did_not_pass(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="a").json()  # stub draft fails the checks
    url = f"/api/versions/{v1['version_id']}/reviews"

    assert client.post(url, data={"decision": "approved"}, headers=client.reviewer).status_code == 400
    ok = client.post(url, data={"decision": "approved", "feedback": "Checked by hand: warning moved to step 1."},
                     headers=client.reviewer)
    assert ok.status_code == 200 and ok.json()["reviewer"] == "rita"
    assert client.get(f"/api/versions/{v1['version_id']}").json()["status"] == "approved"


def test_concurrent_generations_get_distinct_version_numbers(client, monkeypatch):
    doc_id = upload_two_page_pdf(client)
    workers = 8
    barrier = threading.Barrier(workers)

    def slow_generate_sop(**kwargs):
        barrier.wait(timeout=10)  # every request is past the (paid) model call before any insert
        return {"text": "DRAFT:\nx", "model": "stub-model"}

    monkeypatch.setattr(api, "generate_sop", slow_generate_sop)

    def run(index):
        author = {"id": "u1", "username": "alice", "role": "author"}
        return api.generate_revision(doc_id, f"change {index}", "full", None, None, None, author)["version_number"]

    with ThreadPoolExecutor(workers) as pool:
        numbers = list(pool.map(run, range(workers)))
    assert sorted(numbers) == list(range(1, workers + 1))


def test_text_inputs_have_length_limits(client):
    doc_id = upload_two_page_pdf(client)
    too_long = "x" * (api.MAX_DESCRIPTION_CHARS + 1)
    assert generate(client, doc_id, description=too_long).status_code == 422
    assert client.post(f"/api/documents/{doc_id}/requests", data={"description": too_long}).status_code == 422
    assert client.prompts == []

    url = f"/api/versions/{generate(client, doc_id, description='a').json()['version_id']}/reviews"
    long_feedback = {"decision": "rejected", "feedback": "f" * (api.MAX_FEEDBACK_CHARS + 1)}
    assert client.post(url, data=long_feedback, headers=client.reviewer).status_code == 422
    assert client.get(url).json()["reviews"] == []


def test_oversized_source_is_refused_before_calling_gemini(client, monkeypatch):
    doc_id = upload_two_page_pdf(client)

    monkeypatch.setattr(api, "MAX_PDF_PAGES", 1)
    response = generate(client, doc_id, description="x")
    assert response.status_code == 413 and "2 pages" in response.json()["detail"]
    # One page of a long PDF is still allowed.
    assert generate(client, doc_id, description="x", scope="page", target_page=1).status_code == 200

    monkeypatch.setattr(api, "MAX_SOURCE_CHARS", 10)
    response = generate(client, doc_id, description="x", scope="page", target_page=1)
    assert response.status_code == 413 and "characters" in response.json()["detail"]
    assert len(client.prompts) == 1  # only the allowed page-scope call reached the model


def test_approved_version_is_locked(client):
    doc_id = upload_two_page_pdf(client)
    v1 = generate(client, doc_id, description="a").json()
    url = f"/api/versions/{v1['version_id']}/reviews"

    assert client.post(url, data={"decision": "needs_revision"}, headers=client.reviewer).status_code == 200
    assert client.post(url, data={"decision": "approved", "feedback": "Checked by hand."},
                       headers=client.reviewer).status_code == 200
    for decision in ("approved", "rejected", "needs_revision"):
        response = client.post(url, data={"decision": decision, "feedback": "x"}, headers=sign_in(client, "rob"))
        assert response.status_code == 409 and "locked" in response.json()["detail"]

    assert client.get(f"/api/versions/{v1['version_id']}").json()["status"] == "approved"
    assert [r["decision"] for r in client.get(url).json()["reviews"]] == ["approved", "needs_revision"]


def save_request(client, doc_id, **data):
    return client.post(f"/api/documents/{doc_id}/requests", data=data)


def test_saved_request_stores_target_page_in_its_own_column(client):
    doc_id = upload_two_page_pdf(client)
    saved = save_request(client, doc_id, description="add gloves", scope="page", target_page=2).json()
    assert (saved["description"], saved["target_page"]) == ("add gloves", 2)

    full = save_request(client, doc_id, description="x", scope="full", target_page=2).json()
    assert full["target_page"] is None  # a page number means nothing for full scope

    assert save_request(client, doc_id, description="x", scope="page").status_code == 400
    assert save_request(client, doc_id, description="x", scope="page", target_page=3).status_code == 400

    stored = {r["id"]: r for r in client.get(f"/api/documents/{doc_id}/requests").json()["requests"]}
    assert stored[saved["id"]]["target_page"] == 2 and "[Target page" not in stored[saved["id"]]["description"]


def test_generate_from_saved_request_uses_and_links_it(client):
    doc_id = upload_two_page_pdf(client)
    saved = save_request(client, doc_id, description="add gloves", scope="page", target_page=2).json()

    # Submitted description/scope are ignored in favour of the saved request.
    version = generate(client, doc_id, request_id=saved["id"], description="something else").json()
    assert version["request_id"] == saved["id"] and version["target_page"] == 2
    assert "add gloves" in version["content"] and "(page)" in version["content"]
    assert "PAGE TWO" in client.prompts[0] and "PAGE ONE" not in client.prompts[0]
    assert len(client.get(f"/api/documents/{doc_id}/requests").json()["requests"]) == 1  # no duplicate

    listed = client.get(f"/api/documents/{doc_id}/versions").json()["versions"][0]
    assert (listed["change_request"], listed["scope"], listed["target_page"]) == ("add gloves", "page", 2)


def test_generate_rejects_unknown_or_foreign_request_id(client):
    doc_a = upload_two_page_pdf(client)
    doc_b = upload_two_page_pdf(client)
    foreign = save_request(client, doc_b, description="x").json()["id"]
    assert generate(client, doc_a, request_id=foreign).status_code == 400
    assert generate(client, doc_a, request_id="nope").status_code == 400
    assert generate(client, doc_a).status_code == 400  # neither description nor request_id
    assert client.prompts == []


def test_direct_generation_records_target_page_on_its_request(client):
    doc_id = upload_two_page_pdf(client)
    generate(client, doc_id, description="add gloves", scope="page", target_page=2)
    request = client.get(f"/api/documents/{doc_id}/requests").json()["requests"][0]
    assert (request["scope"], request["target_page"]) == ("page", 2)


def test_allowed_origins_come_from_env(client, monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert api.allowed_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://sop.example.com , ,http://localhost:3000")
    assert api.allowed_origins() == ["https://sop.example.com", "http://localhost:3000"]

    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in client.get(
        "/api/health", headers={"Origin": "https://evil.example"}).headers


def test_advisory_semantic_findings_are_saved_but_never_lower_status(client, monkeypatch):
    from src import semantic_checker

    class AlwaysContradicts:
        name = "fake"

        def find_contradictions(self, originals, drafts):
            return [(originals[0], drafts[0], 0.9, "fake reason")] if originals and drafts else []

    monkeypatch.setattr(semantic_checker, "backend_from_env", lambda: AlwaysContradicts())
    doc_id = upload_two_page_pdf(client)
    stub = {"text": "DRAFT:\nPAGE ONE: WARNING disconnect power\n1. Open the cover.", "model": "stub-model"}
    monkeypatch.setattr(api, "generate_sop", lambda **kwargs: stub)
    version = generate(client, doc_id, description="open the cover").json()

    evaluation = client.get(f"/api/versions/{version['version_id']}/evaluations").json()["evaluations"][0]
    advisory = [f for f in evaluation["findings"] if f.get("advisory")]
    assert advisory and advisory[0]["type"] == "semantic_contradiction"
    assert evaluation["metrics"]["semantic_check"]["status"] == "ran"
    assert evaluation["status"] == "needs_review"  # never pass_automated once an advisory finding exists


def test_structured_draft_json_is_stored_with_the_version(client, monkeypatch):
    import json
    structured = {"preamble": "", "steps": [{"id": "R1", "text": "Open the cover.", "source_step_ids": ["S1"],
                                             "change_type": "unchanged"}],
                  "warnings": [], "removed_warning_ids": []}
    monkeypatch.setattr(api, "generate_sop", lambda **kwargs: {
        "text": "DRAFT:\n1. Open the cover.", "model": "stub-model", "prompt_version": "v3", "structured": structured})
    doc_id = upload_two_page_pdf(client)
    version = generate(client, doc_id, description="x").json()
    assert version["structured"] == structured
    stored = client.get(f"/api/versions/{version['version_id']}").json()["structured_json"]
    assert json.loads(stored) == structured

    monkeypatch.setattr(api, "generate_sop", lambda **kwargs: {"text": "DRAFT:\n1. x", "model": "stub-model"})
    older_style = generate(client, doc_id, description="y").json()
    assert client.get(f"/api/versions/{older_style['version_id']}").json()["structured_json"] is None


def test_v3_versions_use_the_structured_evaluator_and_old_ones_the_text_path(client, monkeypatch):
    structured = {"preamble": "", "warnings": [{"id": "RW1", "text": "PAGE ONE: WARNING disconnect power",
                                                "source_warning_id": "W1"}],
                  "removed_warning_ids": [], "steps": [],
                  "change_summary": "", "preserved_safety_requirements": "", "unresolved_questions": "",
                  "source_limitations": ""}
    monkeypatch.setattr(api, "generate_sop", lambda **kwargs: {
        "text": "DRAFT:\nPAGE ONE: WARNING disconnect power", "model": "stub-model", "structured": structured})
    doc_id = upload_two_page_pdf(client)
    v3 = generate(client, doc_id, description="disconnect power first").json()
    assert v3["safety_evaluation"]["evaluator_version"].endswith("+structured")
    assert client.post(f"/api/versions/{v3['version_id']}/evaluate").json()["metrics"]["matching"] == "structured"

    monkeypatch.setattr(api, "generate_sop", lambda **kwargs: {"text": "DRAFT:\nx", "model": "stub-model"})
    old = generate(client, doc_id, description="y").json()
    assert "+structured" not in old["safety_evaluation"]["evaluator_version"]



# --- 2.4 authentication and roles ---

def test_everything_but_health_and_login_needs_a_signed_in_user(client):
    anonymous = {"Authorization": ""}
    assert client.get("/api/health", headers=anonymous).status_code == 200
    for method, url in (("get", "/api/documents"), ("post", "/api/documents/upload"),
                        ("get", "/api/documents/x/versions"), ("post", "/api/documents/x/generate"),
                        ("get", "/api/versions/x/diff"), ("post", "/api/versions/x/reviews"),
                        ("get", "/api/versions/x/download"), ("get", "/api/auth/me"), ("get", "/api/users")):
        assert getattr(client, method)(url, headers=anonymous).status_code == 401, url
    assert client.get("/api/documents", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_login_rejects_wrong_password_and_reports_the_user(client):
    assert client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "nobody", "password": PASSWORD}).status_code == 401
    me = client.get("/api/auth/me").json()
    assert (me["username"], me["role"]) == ("alice", "author") and "password_hash" not in me


def test_expired_and_foreign_tokens_are_rejected(client, monkeypatch):
    import jwt
    forged = jwt.encode({"sub": "anything"}, "some-other-secret-that-is-long-enough-for-hs256", algorithm="HS256")
    assert client.get("/api/documents", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    monkeypatch.setattr(api, "TOKEN_MINUTES", -1)
    expired = sign_in(client, "alice")
    assert client.get("/api/documents", headers=expired).status_code == 401


def test_roles_gate_writes(client):
    doc_id = upload_two_page_pdf(client)  # as the author
    reviewer = client.reviewer
    pdf = ("x.pdf", b"%PDF-1.4", "application/pdf")
    assert client.post("/api/documents/upload", files={"file": pdf}, headers=reviewer).status_code == 403
    assert client.post(f"/api/documents/{doc_id}/generate", data={"description": "x"}, headers=reviewer).status_code == 403
    assert client.post(f"/api/documents/{doc_id}/requests", data={"description": "x"}, headers=reviewer).status_code == 403
    version = generate(client, doc_id, description="a").json()
    assert version["created_by"] == "alice"
    url = f"/api/versions/{version['version_id']}/reviews"
    assert client.post(url, data={"decision": "rejected"}).status_code == 403  # author cannot review
    assert client.get(f"/api/documents/{doc_id}/versions", headers=reviewer).status_code == 200  # reading is open


def test_nobody_approves_a_version_they_generated(client):
    doc_id = upload_two_page_pdf(client)
    response = client.post(f"/api/documents/{doc_id}/generate", data={"scope": "full", "description": "a"},
                           headers=client.admin)  # admin may author and review, but not both on one version
    version = response.json()
    url = f"/api/versions/{version['version_id']}/reviews"
    approve = {"decision": "approved", "feedback": "Checked by hand."}
    denied = client.post(url, data=approve, headers=client.admin)
    assert denied.status_code == 403 and "another reviewer" in denied.json()["detail"]
    assert client.post(url, data={"decision": "needs_revision"}, headers=client.admin).status_code == 200
    assert client.post(url, data=approve, headers=client.reviewer).status_code == 200


def test_user_management_is_admin_only(client):
    new = {"username": "carol", "password": PASSWORD, "role": "reviewer"}
    assert client.post("/api/users", json=new).status_code == 403  # author
    assert client.post("/api/users", json=new, headers=client.admin).status_code == 200
    assert client.post("/api/users", json=new, headers=client.admin).status_code == 409
    assert client.post("/api/users", json={**new, "username": "dan", "password": "short"},
                       headers=client.admin).status_code == 400
    assert client.post("/api/users", json={**new, "username": "eve", "role": "owner"},
                       headers=client.admin).status_code == 400
    names = [u["username"] for u in client.get("/api/users", headers=client.admin).json()["users"]]
    assert names == ["admin", "alice", "carol", "rita", "rob"]


def test_admin_seed_never_resets_an_existing_password(client, monkeypatch):
    monkeypatch.setattr(api, "ADMIN_PASSWORD", "a-different-password")
    api.seed_admin()
    assert client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
