"""E2-D full ASGI, real Human gates; only remote extraction is preset fictional data."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from browser_customer_speaker_intake_v1 import EXTRACT_CODE
from conftest import login_and_change_password
from app.task_service import update_task
from test_customer_constraints_e2_http import no_external_network

FIXTURES = Path(__file__).parent / "fixtures/customer_speaker_e2"
RESOLUTION = "本品牌不等于示例合作餐厅，不自动继承其荣誉或评价。"


@pytest.fixture
def settings(settings):
    shutil.copy2(settings.repo_root / "ops-pipeline/speaker_prompt.md", settings.pipeline_root / "speaker_prompt.md")
    return replace(settings, pipeline_python_executable=str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boundary(settings, task, kind="customer_analysis", *, expect_success=True):
    run = subprocess.run([settings.pipeline_python_executable, "-X", "utf8", "-c", EXTRACT_CODE,
        str(settings.pipeline_root), str(settings.repo_root), kind, task["payload"]["request_path"]],
        capture_output=True, text=True, encoding="utf-8", timeout=40)
    if expect_success:
        assert run.returncode == 0, run.stderr
        update_task(settings.database_path, task["task_id"], status="awaiting_review", stage="等待人工核对", progress=100)
    return run


def seed(client, settings, csrf, *, omission=False):
    materials = (FIXTURES / "GOLDEN_INPUT_FICTIONAL.md").read_text(encoding="utf-8")
    if omission:
        materials += "\n[SYNTHETIC_HISTORICAL_OMISSION]"
    response = client.post("/api/customers/analyze", headers={"X-CSRF-Token": csrf}, json={
        "customer_name": "澄禾小馆（完全虚构E2）", "materials": materials, "submission_key": "fictional-e2-golden-one"})
    assert response.status_code == 200, response.text
    body = response.json()
    boundary(settings, body["task"])
    return body, client.get(f'/api/customers/{body["business_id"]}').json()


def decisions(detail, *, select_speaker=True):
    controls = []
    for item in detail["constraint_candidates"]:
        kind = item["constraint_type"]
        choice = {"constraint_id": item["constraint_id"], "decision": "exclude" if kind == "unverified_claim" else "resolve" if kind == "identity_conflict" else "confirm"}
        if kind == "identity_conflict":
            choice.update(resolution_quote=RESOLUTION, note="虚构人审：原文明确本品牌不等于合作餐厅，分别归属，不继承荣誉。")
        controls.append(choice)
    return {"decisions": [{"candidate_id": item["candidate_id"], "decision": "approve"} for item in detail["fact_candidates"] if item["state"] == "requires_review"],
        "constraint_decisions": controls,
        "speaker_confirmations": [{"candidate_id": item["candidate_id"], "selected": select_speaker, "speaker_type": "owner_founder"} for item in detail["speaker_candidates"] if not item["confirmed"]]}


def test_exception_review_context_partial_shared_actor_stale_and_replay(client, settings):
    from app.auth_service import provision_user
    from fastapi.testclient import TestClient
    from app.main import build_app
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf)
    business = body["business_id"]
    url = f"/api/customers/{business}/facts/review"
    directory = settings.pipeline_root / "data/customer_intakes" / business / detail["latest_intake_id"]
    protected = {p: sha(p) for p in directory.glob("*.json")}
    assert not (directory / "review_progress").exists()
    assert client.get(f"/api/customers/{business}").status_code == 200
    assert not (directory / "review_progress").exists()  # opening and default suggestions are read-only
    with TestClient(build_app(settings)) as other:
        provision_user(settings.database_path, "13800000001")
        auth = other.post("/api/auth/login", json={"phone": "13800000001", "password": "123456"}).json()
        auth = other.post("/api/auth/change-password", headers={"X-CSRF-Token": auth["csrf_token"]}, json={
            "current_password": "123456", "new_password": "FictionalUx2026!", "confirm_password": "FictionalUx2026!"}).json()
        other_detail = other.get(f"/api/customers/{business}").json()
        assert other_detail["business_id"] == business  # shared customer read is retained
        payload = decisions(detail, select_speaker=False)
        payload["speaker_confirmations"] = []
        payload["constraint_decisions"] = []
        payload["decisions"] = payload["decisions"][:2]
        payload["review_context"] = detail["review_context"]["token"]
        assert client.post(url, json=payload).status_code == 403  # CSRF
        assert other.post(url, headers={"X-CSRF-Token": auth["csrf_token"]}, json=payload).status_code == 403
        response = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["review"]["status"] == "review_progress_saved"
        receipts = {p: sha(p) for p in (directory / "review_progress").glob("*.json")}
        assert len(receipts) == 1
        assert client.post(url, headers={"X-CSRF-Token": csrf}, json=payload).status_code == 200
        assert all(sha(p) == h for p, h in receipts.items())
        stale = {"review_context": other_detail["review_context"]["token"], "decisions": payload["decisions"]}
        failed = other.post(url, headers={"X-CSRF-Token": auth["csrf_token"]}, json=stale)
        assert failed.status_code == 409 and failed.json()["detail"]["code"] == "REVIEW_CONTEXT_STALE"
        changed = {**payload, "decisions": payload["decisions"][:1]}
        assert client.post(url, headers={"X-CSRF-Token": csrf}, json=changed).status_code == 409
        fresh = other.get(f"/api/customers/{business}").json()
        assert len([v for v in fresh["fact_candidates"] if v["state"] == "requires_review"]) == 2
        remaining = decisions(fresh, select_speaker=False)
        remaining["speaker_confirmations"] = []
        remaining["review_context"] = fresh["review_context"]["token"]
        response = other.post(url, headers={"X-CSRF-Token": auth["csrf_token"]}, json=remaining)
        assert response.status_code == 200, response.text
        assert response.json()["review"]["authority"]["fact_review_completed"] is True
        final = client.get(f"/api/customers/{business}").json()
        assert final["business_persona"]["approved"] is False and final["creation_entry_ready"] is False
        assert all(sha(p) == h for p, h in protected.items())
        from customer_fact_review_v1 import read_review_progress
        state = read_review_progress(directory)
        assert {r["reviewer"] for r in state["receipts"]} == {"13800000000", "13800000001"}


def test_safe_default_projection_uses_evidence_not_confidence(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf)
    assert all(v["default_review_selection"] is None for v in detail["fact_candidates"])  # unresolved business-scope conflict
    from app.customer_gateway import _safe_review_selection
    directory = settings.pipeline_root / "data/customer_intakes" / body["business_id"] / detail["latest_intake_id"]
    intake = json.loads((directory / "customer_intake_v1.json").read_text(encoding="utf-8"))
    candidates = json.loads((directory / "persona_fact_candidates_v1.json").read_text(encoding="utf-8"))["fact_candidates"]
    ordinary = next(v for v in candidates if v["target_field"] == "primary_products_or_services")
    assert _safe_review_selection(ordinary, intake, [])[0] == "approve"
    assert _safe_review_selection({**ordinary, "source_excerpt": "不存在的来源", "confidence": 1}, intake, [])[0] is None
    assert _safe_review_selection({**ordinary, "conflict_refs": ["conflict"]}, intake, [])[0] is None


def test_unseen_candidate_or_altered_snapshot_cannot_be_reviewed_by_old_page(client, settings):
    """Adversarial change in an isolated fixture; never mutate a runtime Intake."""
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf)
    directory = settings.pipeline_root / "data/customer_intakes" / body["business_id"] / detail["latest_intake_id"]
    candidate_path = directory / "persona_fact_candidates_v1.json"
    artifact = json.loads(candidate_path.read_text(encoding="utf-8"))
    extra = {**artifact["fact_candidates"][0], "candidate_id": "unseen_candidate"}
    artifact["fact_candidates"].append(extra)
    candidate_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    payload = {**decisions(detail, select_speaker=False), "speaker_confirmations": [],
        "review_context": detail["review_context"]["token"]}
    response = client.post(f'/api/customers/{body["business_id"]}/facts/review',
        headers={"X-CSRF-Token": csrf}, json=payload)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "REVIEW_CONTEXT_STALE"
    assert not (directory / "review_progress").exists()
    assert not (directory / "customer_fact_review_v1.json").exists()


def test_durable_receipt_browser_fault_gateway_resume_without_duplicate_decision(client, settings, monkeypatch):
    from browser_customer_speaker_intake_v1 import inject_review_interruption
    from app import customer_gateway
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf)
    business = body["business_id"]
    directory = settings.pipeline_root / "data/customer_intakes" / business / detail["latest_intake_id"]
    # New isolated fixture source, before any review. Never mutate a runtime intake.
    source_path = directory / "customer_intake_v1.json"
    intake = json.loads(source_path.read_text(encoding="utf-8"))
    intake["fixture_fault_marker"] = "[E2_UX_REVIEW_INTERRUPT_ONCE]"
    source_path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
    detail = client.get(f"/api/customers/{business}").json()
    original = customer_gateway._run_json_command
    inject_review_interruption(settings, settings.pipeline_root.parent)
    wrapper = customer_gateway._run_json_command
    monkeypatch.setattr(customer_gateway, "_run_json_command", original)
    monkeypatch.setattr(customer_gateway, "_run_json_command", wrapper)
    payload = {**decisions(detail, select_speaker=False), "speaker_confirmations": [],
        "review_context": detail["review_context"]["token"]}
    response = client.post(f"/api/customers/{business}/facts/review", headers={"X-CSRF-Token": csrf}, json=payload)
    assert response.status_code == 200 and response.json()["review"]["recovery_required"], response.text
    receipts = {p: sha(p) for p in (directory / "review_progress").glob("*.json")}
    assert len(receipts) == 1
    fresh = client.get(f"/api/customers/{business}").json()
    assert fresh["review_progress"]["completion_retry_required"] is True
    assert fresh["status"] == "fact_review_required" and fresh["creation_entry_ready"] is False
    response = client.post(f"/api/customers/{business}/facts/review", headers={"X-CSRF-Token": csrf}, json={
        "decisions": [], "resume_review": True, "review_context": fresh["review_context"]["token"]})
    assert response.status_code == 200 and response.json()["review"]["authority"]["fact_review_completed"], response.text
    assert all(sha(p) == h for p, h in receipts.items())
    assert len(list((directory / "review_progress").glob("*.json"))) == 1
    assert client.get(f"/api/customers/{business}").json()["business_persona"]["approved"] is False


def approve_full_flow(client, settings, csrf, business, payload):
    headers = {"X-CSRF-Token": csrf}
    reviewed = client.post(f"/api/customers/{business}/facts/review", headers=headers, json=payload)
    assert reviewed.status_code == 200, reviewed.text
    detail = client.get(f"/api/customers/{business}").json()
    assert detail["business_persona"]["approved"] is False
    assert detail["creation_entry_ready"] is False
    assert len(detail["speakers"]) == 1
    approved = client.post(f"/api/customers/{business}/persona/approve", headers=headers,
        json={"note": "隔离虚构Golden：明确Business独立人工批准"})
    assert approved.status_code == 200, approved.text
    detail = client.get(f"/api/customers/{business}").json()
    assert detail["current_business_persona"]["approved"] is True
    assert detail["creation_entry_ready"] is False
    speaker = detail["speakers"][0]["speaker_id"]
    url = f"/api/customers/{business}/speakers/{speaker}"
    personal = client.get(url).json()
    boundary(settings, personal["task"], "speaker_analysis")
    personal = client.get(url).json()
    response = client.post(url + "/facts/review", headers=headers, json={"decisions": [
        {"candidate_id": item["candidate_id"], "decision": "approve"} for item in personal["fact_candidates"] if item["state"] == "requires_review"],
        "note": "只确认本人有逐字来源的经历与表达范围"})
    assert response.status_code == 200, response.text
    assert client.get(url).json()["speaker_persona"]["approved"] is False
    response = client.post(url + "/persona/approve", headers=headers, json={"note": "隔离虚构Golden：明确Speaker独立人工批准"})
    assert response.status_code == 200, response.text
    final = client.get(f"/api/customers/{business}").json()
    assert final["creation_entry_ready"] is True
    options = client.get("/api/create/options").json()
    assert next(item for item in options["customers"] if item["business_id"] == business)["creation_ready"] is True
    assert options["authority"]["media_rights_required_for_script_capacity_preview"] is False
    return final


def test_golden_full_application_independent_human_gates_and_no_truth_transfer(client, settings):
    csrf = login_and_change_password(client)
    cases = {p: sha(p) for p in (settings.pipeline_root / "data/cases").rglob("*.json")}
    body, detail = seed(client, settings, csrf)
    assert detail["speaker_candidates"][0]["speaker_type_hint"] == "owner_founder"
    assert next(v for v in detail["fact_candidates"] if v["field"] == "industry")["value"] == "餐饮"
    business = body["business_id"]
    payload = decisions(detail)
    final = approve_full_flow(client, settings, csrf, business, payload)
    persona_path = Path(final["current_business_persona"]["path"])
    persona = json.loads(persona_path.read_text(encoding="utf-8"))
    assert "城市餐饮奖" not in json.dumps(persona["facts"], ensure_ascii=False)
    assert persona["persona_control_layer"]["contract_version"] == "business-restriction-v1.0"
    protected = {p: sha(p) for p in settings.pipeline_root.joinpath("data/personas").rglob("*.json")}
    replay = client.post(f"/api/customers/{business}/facts/review", headers={"X-CSRF-Token": csrf}, json=payload)
    assert replay.status_code == 200
    assert all(sha(p) == h for p, h in protected.items())
    assert all(sha(p) == h for p, h in cases.items())


def test_historical_golden_omission_recovery_preserves_review_and_one_speaker(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf, omission=True)
    business = body["business_id"]
    assert len(detail["fact_candidates"]) == 1
    response = client.post(f"/api/customers/{business}/facts/review", headers={"X-CSRF-Token": csrf}, json=decisions(detail))
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/customers/{business}").json()
    assert len(detail["speakers"]) == 1
    assert all(v["reason"] == "extraction_omission" for v in detail["gap_explanations"] if v["capability_group"] != "critical_constraints")
    source = Path(body["task"]["payload"]["request_path"]).parent
    protected = {p: sha(p) for p in source.glob("*.json")}
    recovery = detail["saved_source_recovery"]
    payload = {"source_intake_id": recovery["source_intake_id"], "targets": recovery["targets"], "execution_identity": "golden-historical-recovery"}
    response = client.post(f"/api/customers/{business}/intake/recover", headers={"X-CSRF-Token": csrf}, json=payload)
    assert response.status_code == 200, response.text
    boundary(settings, response.json()["task"])
    detail = client.get(f"/api/customers/{business}").json()
    assert detail["speaker_candidates"] == []
    assert all(v["field"] != "public_display_name" for v in detail["fact_candidates"])
    final = approve_full_flow(client, settings, csrf, business, decisions(detail))
    assert len(final["speakers"]) == 1
    assert all(sha(p) == h for p, h in protected.items())
    replay = client.post(f"/api/customers/{business}/intake/recover", headers={"X-CSRF-Token": csrf}, json=payload)
    assert replay.status_code == 200 and replay.json()["replayed"] is True


def test_nonmatching_fixture_is_explicitly_unsupported_and_never_calls_model(client, settings):
    csrf = login_and_change_password(client)
    response = client.post("/api/customers/analyze", headers={"X-CSRF-Token": csrf}, json={
        "customer_name": "不匹配的虚构输入", "materials": "仅有一句任意描述，不能套用预置客户。"})
    run = boundary(settings, response.json()["task"], expect_success=False)
    assert run.returncode != 0 and "UNSUPPORTED_OFFLINE_FIXTURE" in run.stderr
    assert not list(Path(response.json()["task"]["payload"]["request_path"]).parent.glob("persona_fact_candidates_v1.json"))
