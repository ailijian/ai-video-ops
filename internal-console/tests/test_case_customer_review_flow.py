from review_protocol import post_review
"""Regression for the reported owner-checkbox dead end and approved legacy customer."""
import hashlib
import json

from conftest import login_and_change_password
from app.customer_gateway import customer_creation_constraints
from customer_constraints_v1 import digest
from test_case_library_security_v1 import node, ready, approve, CASE_ID


def hashes(root):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.json")}


def seed_legacy_conflict(settings):
    directory = settings.pipeline_root / "data/customer_intakes/fixture_business_001/intake_0001"
    directory.mkdir(parents=True)
    value = {"intake_id": "historical_materials_0001", "raw_answers": [],
             "raw_input_contract": {"raw_answers_sha256": digest([])},
             "conflicts": [{"conflict_id": "two_entity_relationship", "severity": "critical", "resolved": False,
                            "topic": "虚构主店与另一门店的主体关系", "resolution_question": "请核实两个主体及数据适用范围。"}]}
    (directory / "customer_intake_v1.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_approved_legacy_customer_blocker_is_explained_consistently_and_read_only(client, settings):
    csrf = login_and_change_password(client)
    seed_legacy_conflict(settings)
    before = hashes(settings.pipeline_root)
    response = client.get("/api/customers/fixture_business_001")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["status"] == "approved"
    assert any(s["status"] == "approved" for s in detail["speakers"])
    assert not detail["creation_entry_ready"] and detail["production_constraint_blocked"]
    constraints = detail["creation_constraints"]
    assert constraints["blocked"] and constraints["projection_only"]
    assert len(constraints["items"]) == 1
    item = constraints["items"][0]
    assert item["constraint_id"] == "two_entity_relationship"
    assert item["title"] == "虚构主店与另一门店的主体关系"
    assert item["reason"] == "请核实两个主体及数据适用范围。"
    assert item["source_intake_id"] == "historical_materials_0001"
    row = next(v for v in client.get("/api/customers/operations").json()["customers"] if v["business_id"] == detail["business_id"])
    assert row["operation"]["primary"]["url"] == constraints["url"]
    assert row["approved_speaker_count"] >= 1 and not row["creation_ready"]
    options = client.get("/api/create/options?business_id=fixture_business_001").json()["customers"][0]
    assert options["authority_blocker"]["url"] == constraints["url"]
    assert not options["creation_ready"]
    pending = client.get("/api/dashboard?section=attention").json()["list"]["items"]
    action = next(v for v in pending if v["kind"] == "business_constraints")
    assert action["action"]["url"] == constraints["url"]
    denied = client.post("/api/create/capacity-preview", headers={"X-CSRF-Token": csrf}, json={
        "business_id": detail["business_id"], "speaker_id": detail["speakers"][0]["speaker_id"],
        "profile": "mix", "quantity": 1})
    assert denied.status_code >= 400
    assert "BUSINESS_CONSTRAINT_BLOCKED" in denied.text
    assert hashes(settings.pipeline_root) == before
    supplement = client.post("/api/customers/fixture_business_001/gaps/supplement", headers={"X-CSRF-Token":csrf},
        json={"answers":[{"target_gap":"additional_materials", "raw_answer":"虚构补充：两个主体分别经营，所有适用数据仍须人工确认。"}]})
    assert supplement.status_code == 200, supplement.text
    assert supplement.json()["task"]["status"] == "queued"
    latest = client.get("/api/customers/fixture_business_001").json()
    assert latest["creation_constraints"]["blocked"] and not latest["creation_entry_ready"]
    assert latest["current_business_persona"]["approved"]
    assert latest["latest_intake_id"] != detail["latest_intake_id"]
    assert all(hashes(settings.pipeline_root).get(path) == sha for path,sha in before.items())


def test_pending_typed_restrictions_are_still_explained_by_canonical_policy(client, settings, monkeypatch):
    import customer_constraints_v1 as owner
    # A synthetic normalized policy result tests whitelist rendering, not approval.
    record = {"constraint_id":"typed-id", "constraint_type":"identity_conflict", "source":{"intake_id":"new-intake", "evidence_quote":"两个主体尚未确认"}}
    monkeypatch.setattr(owner,"collect",lambda *a:[])
    monkeypatch.setattr(owner,"unresolved_legacy_constraints",lambda *a:[])
    current = {"production_constraints":{"blockers":[record]}}
    projection = customer_creation_constraints(settings,"fixture_business_001",current)
    assert projection["blocked"]
    assert projection["items"][0]["reason"] == "两个主体尚未确认"
    assert "source" not in projection["items"][0]


def test_classified_owner_cannot_approve_and_reviewer_can_without_new_attempt(node):
    _, task, candidate, evidence, _, _ = ready(node)
    before = hashes(node[0].pipeline_root)
    owner, owner_headers, _ = node[1]["A"]
    detail = owner.get(f"/api/cases/{CASE_ID}").json()
    assert detail["classification"]["status"] == "confirmed"
    assert not detail["permissions"]["can_review"] and not detail["review"]["can_review"]
    assert detail["evidence_review"]["required"]
    denied = post_review(owner, f"/api/cases/{CASE_ID}/review", headers=owner_headers,
                        json={"decision":"approve", "evidence_review":evidence})
    assert denied.status_code == 403
    assert hashes(node[0].pipeline_root) == before
    approve(node,evidence)
    after = owner.get(f"/api/cases/{CASE_ID}").json()
    assert after["review"]["approved"]
    assert after["classification"]["status"] == "confirmed"
    assert after["review"]["attempt_id"] == task["task_id"]
