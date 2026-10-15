"""NAV-1 / CUSTOMER-LIST-1: formal application reads, fixtures never production."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import customer_operations_projection as projection
from app.canonical_gateway import CanonicalOperationError
from conftest import login_and_change_password


def hashes(root):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.json")}


def test_list_http_is_bounded_authenticated_and_read_only(client, settings):
    assert client.get("/api/customers/operations").status_code == 401
    login_and_change_password(client)
    before = hashes(settings.pipeline_root)
    response = client.get("/api/customers/operations?page_size=1")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["projection_only"] and len(data["customers"]) <= 1
    assert data["counts_scope"] == "all_search_matches"
    assert data["filter_counts"]["all"] >= len(data["customers"])
    assert "facts" not in data["customers"][0]
    assert client.get("/api/customers/operations?page_size=51").status_code == 422
    assert client.get("/api/customers/operations?page=0").status_code == 422
    assert client.get("/api/customers/operations?filter_by=invalid").status_code == 422
    assert client.get("/api/customers/operations?search=NoMatchingFictionalCustomer").json()["total"] == 0
    assert hashes(settings.pipeline_root) == before


def test_scoped_creation_options_never_fall_back_to_another_customer(client, settings):
    login_and_change_password(client)
    data = client.get("/api/create/options?business_id=fixture_business_001")
    assert data.status_code == 200, data.text
    assert data.json()["customer_context"]["business_id"] == "fixture_business_001"
    assert all(c["business_id"] == "fixture_business_001" for c in data.json()["customers"])
    assert client.get("/api/create/options?business_id=missing_customer").status_code >= 400
    assert client.get("/api/customers/missing_customer/creation-records").status_code >= 400


def test_history_counts_requests_and_preserves_original_sha(client, settings):
    login_and_change_password(client)
    before = hashes(settings.pipeline_root)
    response = client.get("/api/customers/fixture_business_001/creation-records")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len({r["record_id"] for r in data["records"]}) == len(data["records"])
    assert all(r["business_id"] == "fixture_business_001" for r in data["records"])
    for row in data["records"]:
        if row["profile"] != "mix":
            continue
        context = client.get("/api/create/request-context", params={"request_id": row["request_id"], "business_id": "fixture_business_001"})
        assert context.status_code == 200, context.text
        assert context.json()["request_id"] == row["request_id"]
        assert client.get("/api/create/request-context", params={"request_id": row["request_id"], "business_id": "wrong_business"}).status_code >= 400
    assert hashes(settings.pipeline_root) == before


def test_baseline_list_uses_canonical_gate_not_only_business_approval(client, settings):
    login_and_change_password(client)
    row = next(r for r in client.get("/api/customers/operations").json()["customers"] if r["business_id"] == "fixture_business_001")
    assert row["approved_speaker_count"] >= 1, row
    assert row["operation"]["kind"] != "error", row
    assert row["creation_ready"] == any(p["supported"] for p in row["creation_conditions"]["paths"])
    assert row["region"] is None  # no manufactured city from raw materials
    assert "birth" not in json.dumps(row).lower()


@pytest.mark.parametrize("canonical_status,expected_kind,expected_label", [
    ("draft", "setup", "继续完善资料"),
    ("fact_review_required", "review", "去核对资料"),
    ("persona_review_required", "approval", "查看待批准事项"),
    ("needs_more_info", "setup", "继续处理资料"),
    ("approved", "conditions", "查看创作条件"),
])
def test_action_matrix_is_a_derived_display_not_a_lifecycle(monkeypatch, settings, canonical_status, expected_kind, expected_label):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": canonical_status, "display_name": "虚构客户", "industry": "AI未确认行业", "submitted_at": "2026-01-01"})
    current = {"artifact": {"facts": {}, "lifecycle": {}}, "revision": 1} if canonical_status == "approved" else None
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=current))
    monkeypatch.setattr(projection, "_creation_conditions", lambda *a, **k: {"ready": False, "paths": []})
    row = projection._operation_row(settings, "fictional_business", [], [], [])
    assert row["industry"] is None
    assert row["operation"]["kind"] == expected_kind
    assert row["operation"]["primary"]["label"] == expected_label
    assert row["creation_ready"] is False


def test_major_r2_conflict_beats_old_approved_r1_and_running_task(monkeypatch, settings):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "approved", "display_name": "虚构客户"})
    current = {"artifact": {"facts": {}}, "production_constraints": {"blockers": ["identity_conflict"]}}
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=current))
    monkeypatch.setattr(projection, "_creation_conditions", lambda *a, **k: {"ready": True, "paths": []})
    row = projection._operation_row(settings, "fictional_business", [], [{"task_id": "t", "task_type": "content_generation", "status": "running"}], [])
    assert row["operation"]["kind"] == "blocked"
    assert row["creation_ready"] is False


def test_first_persona_core_conflict_also_has_a_blocker_entry(monkeypatch, settings):
    import customer_constraints_v1 as owner
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "needs_more_info", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=None))
    monkeypatch.setattr(owner, "collect", lambda *a: [])
    monkeypatch.setattr(owner, "policy", lambda *a: {"blockers": [{"constraint_type": "identity_conflict", "scope": "business"}]})
    row = projection._operation_row(settings, "fictional_business", [], [], [])
    assert row["operation"]["primary"]["label"] == "查看阻断原因"
    assert row["operation"]["kind"] == "blocked" and row["pending_count"] == 1
    assert not row["creation_ready"]


def test_request_pending_deduplicates_failed_execution_and_beats_running(monkeypatch, settings):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "approved", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current={"artifact": {"facts": {}}}))
    monkeypatch.setattr(projection, "_creation_conditions", lambda *a, **k: {"ready": False, "paths": []})
    records = [{"record_id": "generation:r", "request_id": "r", "action_required": True, "url": "/create?request_id=r", "label": "待审核"}]
    tasks = [{"task_id": "t", "task_type": "content_generation", "subject_ref": "r", "status": "running"}]
    row = projection._operation_row(settings, "fictional_business", [], tasks, records)
    assert row["pending_count"] == 1
    assert row["operation"]["primary"]["url"] == records[0]["url"]
    tasks[0]["status"] = "failed"
    failed = projection._operation_row(settings, "fictional_business", [], tasks, records)
    assert failed["pending_count"] == 1
    assert failed["operation"]["primary"]["url"] == records[0]["url"]


def test_draft_and_revalidation_are_not_approved_speaker(monkeypatch, settings):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "approved", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda _, identifier, scope: SimpleNamespace(current={"artifact": {"facts": {}}} if scope == "business" else None))
    monkeypatch.setattr(projection, "_speaker_projection", lambda *a: {"status": "draft"})
    monkeypatch.setattr(projection, "_creation_conditions", lambda *a, **k: {"ready": False, "paths": []})
    row = projection._operation_row(settings, "fictional_business", ["draft_speaker"], [], [])
    assert row["approved_speaker_count"] == 0 and row["speaker"] is None
    assert row["pending_count"] == 1


def test_unknown_metrics_do_not_become_zero(monkeypatch, settings):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "draft", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=None))
    row = projection._operation_row(settings, "fictional_business", [], [], [], records_known=False)
    assert row["creation_record_count"] is None and row["pending_count"] is None
    assert row["approved_speaker_count"] == 0


def test_speaker_waiting_for_customer_is_not_an_additional_actionable_item(monkeypatch, settings):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "needs_more_info", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=None))
    monkeypatch.setattr(projection, "_speaker_projection", lambda *a: {"status": "pending_customer_profile"})
    row = projection._operation_row(settings, "fictional_business", ["pending_speaker"], [], [])
    assert row["pending_count"] == 1  # customer action, no second impossible Speaker review
    assert row["approved_speaker_count"] == 0


@pytest.mark.parametrize("task_type,subject,expected", [
    ("customer_analysis", "fictional_business", "/customers/fictional_business"),
    ("speaker_analysis", "fictional_speaker", "/customers/fictional_business/speakers/fictional_speaker"),
])
def test_failed_analysis_links_to_existing_recovery_controls(monkeypatch, settings, task_type, subject, expected):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "analysis_pending", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=None))
    task = {"task_id": "failure", "subject_ref": subject, "task_type": task_type, "status": "failed"}
    row = projection._operation_row(settings, "fictional_business", [], [task], [])
    assert row["operation"]["kind"] == "error"
    assert row["operation"]["primary"]["url"] == expected
    assert row["pending_count"] == 1


def test_task_read_is_one_query_and_suppresses_superseded_attempts(monkeypatch, settings, client):
    queries = []
    original = projection.connect
    def counted(path):
        db = original(path)
        db.set_trace_callback(queries.append)
        return db
    monkeypatch.setattr(projection, "connect", counted)
    result = projection._task_index(settings, {f"business_{i}" for i in range(25)}, {}, {})
    assert result == {}
    assert sum("FROM tasks" in q for q in queries) == 1


def test_running_execution_is_not_pending_operator_work(monkeypatch, settings):
    monkeypatch.setattr(projection, "_customer_projection", lambda *a, **k: {"status": "analysis_pending", "display_name": "虚构客户"})
    monkeypatch.setattr(projection, "resolve_persona_authority", lambda *a: SimpleNamespace(current=None))
    task = {"task_id": "t", "subject_ref": "r", "task_type": "content_generation", "status": "running", "operation": "script_generation"}
    record = {"record_id": "generation:r", "request_id": "r", "action_required": True, "stage": "GENERATE_SCRIPTS"}
    row = projection._operation_row(settings, "fictional_business", [], [task], [record])
    assert row["pending_count"] == 0 and row["operation"]["kind"] == "running"
    record.update(stage="HUMAN_REVIEW", label="待审核", url="/create?request_id=r")
    row = projection._operation_row(settings, "fictional_business", [], [task], [record])
    assert row["pending_count"] == 1 and row["operation"]["primary"]["url"] == record["url"]


def test_formal_golden_creation_conditions_and_request_context_without_gate_mocks(settings):
    """Preset model candidates + fictional reference library; all real Human/Creation gates."""
    import shutil
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.auth_service import provision_user
    from app.main import build_app
    from test_customer_speaker_e2_golden import boundary, decisions, approve_full_flow, FIXTURES
    settings = replace(settings, pipeline_python_executable=str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"))
    shutil.copy2(settings.repo_root / "ops-pipeline/speaker_prompt.md", settings.pipeline_root / "speaker_prompt.md")
    shutil.copytree(Path(__file__).parent / "fixtures/customer_navigation_v1/data", settings.pipeline_root / "data", dirs_exist_ok=True)
    outputs = json.loads((FIXTURES / "synthetic_outputs.json").read_text(encoding="utf-8"))
    conflict_quote = next(c["evidence_quote"] for c in outputs["business"]["constraints"] if c["constraint_type"] == "identity_conflict")
    material = (FIXTURES / "GOLDEN_INPUT_FICTIONAL.md").read_text(encoding="utf-8").replace(conflict_quote, "本品牌与合作餐厅分别归属，引用时分别核实。") + "\n[E2_UX_NORMAL]"
    with TestClient(build_app(settings)) as client:
        provision_user(settings.database_path, "13800000000")
        csrf = login_and_change_password(client)
        headers = {"X-CSRF-Token": csrf}
        body = client.post("/api/customers/analyze", headers=headers, json={"customer_name": "虚构导航餐厅", "materials": material}).json()
        business = body["business_id"]
        boundary(settings, body["task"])
        detail = client.get(f"/api/customers/{business}").json()
        before = client.get("/api/customers/operations").json()
        row = next(r for r in before["customers"] if r["business_id"] == business)
        assert row["industry"] is None and row["approved_speaker_count"] == 0 and not row["creation_ready"]
        final = approve_full_flow(client, settings, csrf, business, decisions(detail))
        protected = hashes(settings.pipeline_root)
        row = next(r for r in client.get("/api/customers/operations").json()["customers"] if r["business_id"] == business)
        assert row["creation_ready"], row["creation_conditions"]
        result = client.get("/api/customers/operations?filter_by=ready").json()
        row = next(r for r in result["customers"] if r["business_id"] == business)
        assert row["industry"] == "餐饮" and row["approved_speaker_count"] == 1
        assert row["creation_ready"] and row["operation"]["primary"]["label"] == "开始创作", row
        assert row["creation_record_count"] == 0 and row["pending_count"] == 0
        assert business in row["operation"]["primary"]["url"]
        assert hashes(settings.pipeline_root) == protected  # list/filter/preview read-only
        speaker = final["speakers"][0]["speaker_id"]
        confirmation = {"business_id": business, "speaker_id": speaker, "profile": "mix", "requested_quantity": 1, "confirmed_quantity": 1, "idempotency_key": "nav-valid-request"}
        assert client.post("/api/create/confirm", json=confirmation).status_code == 403
        confirmed = client.post("/api/create/confirm", headers=headers, json=confirmation)
        assert confirmed.status_code == 200, confirmed.text
        request_id = confirmed.json()["result"]["request_id"]
        before = hashes(settings.pipeline_root)
        assert client.get("/api/create/request-context", params={"request_id": request_id}).json()["business_id"] == business
        assert client.get(f"/api/customers/{business}/creation-records").json()["total"] == 1
        rows = client.get("/api/customers/operations").json()["customers"]
        row = next(r for r in rows if r["business_id"] == business)
        assert row["creation_record_count"] == 1 and request_id in row["operation"]["primary"]["url"]
        assert hashes(settings.pipeline_root) == before
        # Exact same creation identity resumes, never a navigation-induced new request.
        assert client.post("/api/create/confirm", headers=headers, json=confirmation).json()["result"]["request_id"] == request_id
        # Test-only adversarial copy: a missing exact sidecar cannot be replaced
        # by unrelated frozen historical IDs in the aggregate fixture.
        sidecar = settings.pipeline_root / "data/cases/7999999999999999902/case_profile_compatibility_approval_v1.json"
        sidecar.unlink()
        row = next(r for r in client.get("/api/customers/operations").json()["customers"] if r["business_id"] == business)
        assert not row["creation_ready"]


def test_many_customers_bounded_pages_search_and_single_task_query(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    for i in range(25):
        response = client.post("/api/customers/analyze", headers={"X-CSRF-Token": csrf}, json={
            "customer_name": f"虚构分页门店{i:02}", "materials": "", "save_only": True})
        assert response.status_code == 200, response.text
    queries = []
    original = projection.connect
    def counted(path):
        db = original(path)
        db.set_trace_callback(queries.append)
        return db
    monkeypatch.setattr(projection, "connect", counted)
    first = client.get("/api/customers/operations?search=虚构分页&sort_by=updated&page_size=10").json()
    assert first["total"] == 25 and len(first["customers"]) == 10
    assert first["filter_counts"] == {"all": 25, "pending": 25, "ready": 0}
    assert all(row["creation_record_count"] == 0 and row["approved_speaker_count"] == 0 for row in first["customers"])
    assert sum("FROM tasks" in q for q in queries) == 1
    second = client.get("/api/customers/operations?search=虚构分页&sort_by=updated&page=2&page_size=10").json()
    assert not {r["business_id"] for r in first["customers"]} & {r["business_id"] for r in second["customers"]}
    assert first["customers"] == client.get("/api/customers/operations?search=虚构分页&sort_by=updated&page_size=10").json()["customers"]


def test_persisted_time_order_is_timezone_normalized():
    assert projection._timestamp("2026-10-14T08:00:00+08:00") == projection._timestamp("2026-10-14T00:00:00Z")
    assert projection._timestamp("not-a-date") == ""
