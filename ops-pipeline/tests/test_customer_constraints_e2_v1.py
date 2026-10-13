"""E2-A acceptance: fictional inputs, real canonical review/approval, no network."""
from __future__ import annotations

import copy
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import customer_onboarding_analysis_v1 as analysis
import customer_fact_review_v1 as review
import customer_constraints_v1 as contract
from approve_persona_v1 import approve_persona
from build_persona_v1 import validate_required_fact_authority, persona_content_hash
from generate_mix_scripts_v1 import safe_persona_projection, requires_review_blocked_terms, validate_generated_item
from privacy_projection_v1 import assert_safe_for_external_model

STAMP = "2026-10-10T00:00:00+00:00"
MATERIAL = "虚构小馆提供地方菜堂食。附近家庭安排聚餐。菜单先确认人数和忌口。不得宣传绝对最好。示例奖项尚未核实。经营主体身份冲突需要核实。宴席需要预约。新证据明确经营主体为虚构小馆。"


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Remote Model Calls must remain zero")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def request(intake_id="intake_0001", materials=MATERIAL):
    return {"business_id": "fictional_e2_business", "intake_id": intake_id,
        "customer_name": "虚构小馆", "industry": "", "materials": materials}


def progress_request(summary, decisions, operation="1" * 32, version=None, controls=None, actor="fictional_operator_a"):
    return {"business_id": summary["business_id"], "intake_id": summary["intake_id"],
        "reviewer": actor, "decisions": decisions, "constraint_decisions": controls or [],
        "operation_id": operation, "context_version": version, "context_sha256": "a" * 64,
        "review_mode": "progress"}


@pytest.mark.parametrize("single_submission", [False, True])
def test_ten_candidates_eight_then_two_immutable_actors_and_complete_gate(tmp_path, single_submission):
    summary, candidates = seed(tmp_path)
    path = Path(summary["artifacts"]["fact_candidates_v1"])
    template = next(v for v in candidates["fact_candidates"] if v["target_field"] == "process_facts")
    for index in range(7):
        item = copy.deepcopy(template)
        item["fact_candidate_id"] += f"-fixture-{index}"
        candidates["fact_candidates"].append(item)
    path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
    directory = path.parent
    originals = {p: contract.file_sha(p) for p in directory.glob("*.json")}
    required = [v for v in candidates["fact_candidates"] if v["candidate_state"] == "requires_review"]
    assert len(required) == 10
    if single_submission:
        req = progress_request(summary, [{"candidate_id": v["fact_candidate_id"], "decision": "approve"} for v in required])
        result = review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
        state = review.read_review_progress(directory)
        assert result["authority"]["fact_review_completed"] and not result["authority"]["persona_approved"]
        assert len(state["receipts"]) == 1 and state["complete"]
        for item in state["artifact"]["fact_candidates"]:
            if item["fact_candidate_id"] in {v["fact_candidate_id"] for v in required}:
                assert item["human_review"]["reviewer"] == "fictional_operator_a"
                assert item["human_review"]["candidate_sha256"] == originals[path]
        hashes = {p: contract.file_sha(p) for p in (directory / "review_progress").glob("*.json")}
        review.review_customer_facts(request=req, pipeline_root=tmp_path)
        assert all(contract.file_sha(p) == h for p, h in {**originals, **hashes}.items())
        return
    first = [{"candidate_id": v["fact_candidate_id"], "decision": "approve"} for v in required[:8]]
    first[0] = {**first[0], "decision": "edit", "edited_value": ["地方菜堂食（人审核对）"]}
    first[1]["decision"] = "reject"
    req = progress_request(summary, first)
    result = review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    assert result["status"] == "review_progress_saved" and result["pending_count"] == 2
    assert result["authority"]["fact_review_completed"] is False
    state = review.read_review_progress(directory)
    assert len(state["pending_ids"]) == 2 and not state["complete"]
    assert not (directory / "business_persona_input_v1.json").exists()
    receipt = Path(state["receipts"][0]["path"])
    before = contract.file_sha(receipt)
    assert review.review_customer_facts(request=req, pipeline_root=tmp_path) == result
    assert contract.file_sha(receipt) == before and len(review.read_review_progress(directory)["receipts"]) == 1
    with pytest.raises(review.CustomerFactReviewError, match="Every requires_review"):
        review.review_customer_facts(request={**review_request(summary, candidates), "decisions": first}, pipeline_root=tmp_path)
    with pytest.raises(review.CustomerFactReviewError, match="previously reviewed"):
        review.review_customer_facts(request=progress_request(summary, first, "3" * 32, state["version"]), pipeline_root=tmp_path)
    remaining = [{"candidate_id": v["fact_candidate_id"], "decision": "approve"} for v in required[8:]]
    final = review.review_customer_facts(request=progress_request(summary, remaining, "2" * 32,
        state["version"], actor="fictional_operator_b"), pipeline_root=tmp_path, reviewed_at=STAMP)
    assert final["authority"]["fact_review_completed"] is True and not final["authority"]["persona_approved"]
    state = review.read_review_progress(directory)
    assert state["complete"] and len(state["receipts"]) == 2
    reviewed = review.read_json(Path(final["artifacts"]["reviewed_candidates_v1"]))
    by_id = {v["fact_candidate_id"]: v for v in reviewed["fact_candidates"]}
    assert by_id[first[0]["candidate_id"]]["normalized_value"] == first[0]["edited_value"]
    assert by_id[first[1]["candidate_id"]]["candidate_state"] == "unknown"
    assert by_id[remaining[0]["candidate_id"]]["human_review"]["reviewer"] == "fictional_operator_b"
    assert by_id[first[0]["candidate_id"]]["human_review"]["reviewer"] == "fictional_operator_a"
    assert contract.file_sha(receipt) == before
    assert all(contract.file_sha(p) == h for p, h in originals.items())


def test_progress_constraints_effective_before_complete_and_crash_replay(tmp_path, monkeypatch):
    summary, candidates = seed(tmp_path, ["publication_prohibition", "identity_conflict"])
    directory = Path(summary["artifacts"]["fact_candidates_v1"]).parent
    control = candidates["derived_authority_constraints"][0]
    req = progress_request(summary, [], controls=[{"constraint_id": control["constraint_id"], "decision": "confirm"}])
    review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    effective = contract.collect(tmp_path, summary["business_id"])
    assert effective[0]["human_review"]["reviewer"] == "fictional_operator_a"
    assert contract.policy(effective)["blockers"]
    state = review.read_review_progress(directory)
    finish = progress_request(summary, review_request(summary, candidates)["decisions"], "2" * 32, state["version"],
        [{"constraint_id": candidates["derived_authority_constraints"][1]["constraint_id"], "decision": "defer"}])
    original = review.write_atomic_json
    def fail_derived(path, value):
        if path.name == "customer_fact_review_v1.json":
            raise OSError("fictional injected interruption after durable receipt")
        return original(path, value)
    monkeypatch.setattr(review, "write_atomic_json", fail_derived)
    with pytest.raises(OSError):
        review.review_customer_facts(request=finish, pipeline_root=tmp_path, reviewed_at=STAMP)
    assert len(review.read_review_progress(directory)["receipts"]) == 2
    hashes = {p: contract.file_sha(p) for p in (directory / "review_progress").glob("*.json")}
    monkeypatch.setattr(review, "write_atomic_json", original)
    final = review.review_customer_facts(request=finish, pipeline_root=tmp_path)
    assert final["status"] == "completed_persona_blocked"
    assert len(contract.collect(tmp_path, summary["business_id"])) == 2
    assert all(contract.file_sha(p) == h for p, h in hashes.items())


def test_source_bound_restriction_amendment_consumed_by_policy(tmp_path):
    summary, candidates = seed(tmp_path, ["publication_prohibition"])
    path = Path(summary["artifacts"]["fact_candidates_v1"])
    item = candidates["derived_authority_constraints"][0]
    control = {k: copy.deepcopy(item[k]) for k in contract.CONTROL_FIELDS}
    amendment = {"schema_version": contract.AMENDMENT_VERSION, "original_constraint_sha256": contract.digest(item),
        "candidate_sha256": contract.file_sha(path), "control": control,
        "evidence_quote": item["source"]["evidence_quote"], "reason": "人审核对禁用词及范围", "production_impact": "继续禁用原词，其他业务不受影响"}
    # Expanding the control is supported by the exact raw quote; changes effective fields.
    control["blocked_terms"] = ["绝对最好", "最好"]
    req = progress_request(summary, [], controls=[{"constraint_id": item["constraint_id"], "decision": "confirm", "amendment": amendment}])
    review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    records = contract.collect(tmp_path, summary["business_id"])
    assert contract.policy(records)["blocked_terms"] == ["最好", "绝对最好"]
    assert records[0]["human_review"]["amendment"]["original_control"]["blocked_terms"] == ["绝对最好"]
    assert contract.file_sha(path) == amendment["candidate_sha256"]


@pytest.mark.parametrize("defect", ["no_source", "narrow", "unknown", "wrong_sha", "condition", "identity"])
def test_invalid_restriction_amendment_fails_before_receipt(tmp_path, defect):
    kind = "conditional_fact" if defect == "condition" else "identity_conflict" if defect == "identity" else "publication_prohibition"
    summary, candidates = seed(tmp_path, [kind])
    path = Path(summary["artifacts"]["fact_candidates_v1"])
    item = candidates["derived_authority_constraints"][0]
    amendment = {"schema_version": contract.AMENDMENT_VERSION, "original_constraint_sha256": contract.digest(item),
        "candidate_sha256": contract.file_sha(path), "control": {k: copy.deepcopy(item[k]) for k in contract.CONTROL_FIELDS},
        "evidence_quote": item["source"]["evidence_quote"], "reason": "虚构修订", "production_impact": "虚构影响"}
    if defect == "no_source": amendment["evidence_quote"] = "不存在的原文"
    if defect == "narrow": amendment["control"]["blocked_terms"] = ["最好"]
    if defect == "unknown": amendment["unknown"] = True
    if defect == "wrong_sha": amendment["candidate_sha256"] = "0" * 64
    if defect == "condition": amendment["control"]["condition"] = "无须预约"
    if defect == "identity": amendment["control"]["scope"] = "claim"
    with pytest.raises(RuntimeError):
        review.review_customer_facts(request=progress_request(summary, [], controls=[{
            "constraint_id": item["constraint_id"], "decision": "confirm", "amendment": amendment}]), pipeline_root=tmp_path)
    assert not (path.parent / "review_progress").exists()


def restriction(kind):
    quote = {"publication_prohibition": "不得宣传绝对最好", "unverified_claim": "示例奖项尚未核实",
        "identity_conflict": "经营主体身份冲突需要核实", "conditional_fact": "宴席需要预约"}[kind]
    return {"constraint_type": kind, "scope": "business" if kind == "identity_conflict" else "claim",
        "evidence_quote": quote, "affected_fields": [], "blocked_terms": [] if kind == "identity_conflict" else ["示例奖项" if kind == "unverified_claim" else "绝对最好" if kind == "publication_prohibition" else "宴席"],
        "related_fact_refs": [], "condition": "需要预约" if kind == "conditional_fact" else None}


def output(kinds=()):
    return {"model": "synthetic-contract-only", "facts": [
        {"topic": "primary_service", "value": ["地方菜堂食"], "evidence_quote": "提供地方菜堂食"},
        {"topic": "core_audience", "value": ["附近家庭安排聚餐"], "evidence_quote": "附近家庭安排聚餐"},
        {"topic": "service_process", "value": ["菜单先确认人数和忌口"], "evidence_quote": "菜单先确认人数和忌口"}],
        "constraints": [restriction(kind) for kind in kinds]}


def seed(root, kinds=(), intake_id="intake_0001"):
    summary = analysis.analyze_customer_onboarding(request=request(intake_id), pipeline_root=root,
        extractor=lambda _: output(kinds), speaker_discovery_extractor=lambda _: {"speaker_candidates": []}, created_at=STAMP)
    path = Path(summary["artifacts"]["fact_candidates_v1"])
    return summary, json.loads(path.read_text(encoding="utf-8"))


def review_request(summary, candidates, action="confirm"):
    return {"business_id": summary["business_id"], "intake_id": summary["intake_id"],
        "reviewer": "fictional_authenticated_operator", "note": "Fictional explicit Human decision",
        "decisions": [{"candidate_id": v["fact_candidate_id"], "decision": "approve"} for v in candidates["fact_candidates"] if v["candidate_state"] == "requires_review"],
        "constraint_decisions": [{"constraint_id": v["constraint_id"], "decision": action} for v in candidates["derived_authority_constraints"]]}


@pytest.mark.parametrize("kind", sorted(contract.CONSTRAINT_TYPES))
def test_four_types_have_exact_source_and_independent_human_review(tmp_path, kind):
    summary, candidates = seed(tmp_path, [kind])
    path = Path(summary["artifacts"]["fact_candidates_v1"])
    before = contract.file_sha(path)
    item = candidates["derived_authority_constraints"][0]
    assert item["state"] == "pending_review" and not item.get("human_review")
    assert item["source"]["evidence_quote"] == restriction(kind)["evidence_quote"]
    result = review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    reviewed = json.loads(Path(result["artifacts"]["reviewed_candidates_v1"]).read_text(encoding="utf-8"))
    assert reviewed["derived_authority_constraints"][0]["human_review"]["candidate_sha256"] == before
    assert contract.file_sha(path) == before
    assert all(v.get("normalized_value") != item for v in reviewed["fact_candidates"])
    assert result["authority"]["persona_approved"] is False
    if kind in {"identity_conflict", "unverified_claim"}:
        # A confirmed unverified claim remains non-Truth, but safe exclusion is
        # a separate decision; confirm is restrictive and never approves claim.
        assert all("示例奖项" not in str(v.get("normalized_value")) for v in reviewed["fact_candidates"])


def test_missing_typed_decision_blocks_before_review_is_written(tmp_path):
    summary, candidates = seed(tmp_path, ["publication_prohibition"])
    req = review_request(summary, candidates); req["constraint_decisions"] = []
    with pytest.raises(RuntimeError, match="explicit typed"):
        review.review_customer_facts(request=req, pipeline_root=tmp_path)
    assert not list(tmp_path.rglob("customer_fact_review_v1.json"))


def test_excluded_unverified_claim_allows_independent_business_approval(tmp_path):
    summary, candidates = seed(tmp_path, ["unverified_claim"])
    req = review_request(summary, candidates, "exclude")
    result = review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    path = Path(result["artifacts"]["business_persona_v1"])
    persona, receipt, _ = approve_persona(path, "fictional_authenticated_operator", "Independent explicit approval", STAMP)
    assert receipt["human_gate"] is True
    assert "示例奖项" in requires_review_blocked_terms(persona)
    projected = safe_persona_projection(persona)
    assert "示例奖项" not in json.dumps(projected["facts"], ensure_ascii=False)
    assert contract.assert_production_allowed(persona, path)
    with pytest.raises(RuntimeError, match="CONSUMER_UNSUPPORTED"):
        contract.assert_production_allowed(persona, path, consumer="news")
    sha = contract.file_sha(path)
    assert review.review_customer_facts(request=req, pipeline_root=tmp_path)["review_fingerprint"] == result["review_fingerprint"]
    assert contract.file_sha(path) == sha


def test_pending_r2_conflict_blocks_current_production_without_revoking_r1(tmp_path):
    summary, candidates = seed(tmp_path)
    result = review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    path = Path(result["artifacts"]["business_persona_v1"])
    persona, _, receipt = approve_persona(path, "fictional_authenticated_operator", "Fictional Human approval", STAMP)
    before = (contract.file_sha(path), contract.file_sha(receipt), persona_content_hash(persona))
    seed(tmp_path, ["identity_conflict"], "intake_0002")
    with pytest.raises(RuntimeError, match="CONSTRAINT_BLOCKED"):
        contract.assert_production_allowed(persona, path)
    assert before == (contract.file_sha(path), contract.file_sha(receipt), persona_content_hash(persona))
    from show_customer_status_v1 import resolve_current_persona
    current = resolve_current_persona(tmp_path, persona["persona_id"], "business")
    assert current["revision"] == 1 and current["production_constraints"]["blockers"]


def test_business_shared_validator_checks_critical_and_unknown_control():
    assert validate_required_fact_authority({"facts": {}, "critical_constraints": [{"constraint_id": "critical"}]})
    with pytest.raises(RuntimeError, match="Unknown"):
        contract.validate_control_layer({"persona_control_layer": {"derived_authority_constraints": []}})


def test_task_projection_preserves_business_and_blocks_sensitive_final_prompt():
    privacy = analysis.build_privacy_projection(analysis.validate_request(request(materials=MATERIAL + "\n出生年月：1991年04月\n私人电话：13900000000\n病史：虚构私密病情")), created_at=STAMP)
    prompt = analysis.build_prompt(privacy)
    for token in ["1991", "13900000000", "虚构私密病情"]:
        assert token not in prompt
    for token in ["地方菜堂食", "附近家庭", "菜单先确认", "尚未核实", "需要预约"]:
        assert token in prompt
    assert_safe_for_external_model(prompt)
    with pytest.raises(RuntimeError, match="Egress Gate"):
        assert_safe_for_external_model(prompt + "\n出生年月：1991年04月")


def test_speaker_examples_and_foreign_experiences_are_not_personal():
    from speaker_onboarding_analysis_v1 import personal_quote_has_foreign_owner
    assert personal_quote_has_foreign_owner("公司经营三十年")
    assert personal_quote_has_foreign_owner("同事亲自做过试菜")
    assert not personal_quote_has_foreign_owner("我亲自做过试菜")
    prompt = (Path(__file__).resolve().parents[1] / "speaker_prompt.md").read_text(encoding="utf-8")
    example = prompt[prompt.index('"personal_material_quotes"'):prompt.index('"explicit_forbidden_claims"')]
    assert "经营年限" not in example and "虚构" in example


def test_unknown_constraint_source_quote_and_scope_fail_closed(tmp_path):
    for key, value in [("scope", "unknown"), ("constraint_type", "unknown"), ("evidence_quote", "不存在的来源")]:
        payload = output(["publication_prohibition"]); payload["constraints"][0][key] = value
        with pytest.raises(RuntimeError):
            analysis.analyze_customer_onboarding(request=request(), pipeline_root=tmp_path / key,
                extractor=lambda _: payload, speaker_discovery_extractor=lambda _: {"speaker_candidates": []})


def test_actual_provider_payload_is_task_minimized_without_remote_calls(monkeypatch):
    from types import SimpleNamespace
    captured = []
    def send(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"facts":[],"constraints":[]}'))], usage=None)
    monkeypatch.setattr(analysis, "load_deepseek_runtime_config", lambda: ("fictional-unused-key", "synthetic-offline"))
    monkeypatch.setattr(analysis, "get_client", lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=send))))
    privacy = analysis.build_privacy_projection(analysis.validate_request(request(materials=MATERIAL + "\n出生日期：1991-04-02\n私人电话：13900000000")), created_at=STAMP)
    analysis.extract_remote_facts(privacy)
    payload = json.dumps(captured, ensure_ascii=False)
    assert "13900000000" not in payload and "1991" not in payload
    assert "菜单先确认" in payload and len(captured) == 1
    for message in captured[0]["messages"]:
        assert_safe_for_external_model(message["content"])


def test_exact_human_resolution_preserves_original_conflict_and_decision(tmp_path):
    summary, candidates = seed(tmp_path, ["identity_conflict"])
    blocked = review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    base = Path(summary["artifacts"]["fact_candidates_v1"]).parent
    protected = {p: contract.file_sha(p) for p in base.glob("*.json")}
    later, later_candidates = seed(tmp_path, ["identity_conflict"], "intake_0002")
    intake = json.loads((Path(later["artifacts"]["fact_candidates_v1"]).parent / "customer_intake_v1.json").read_text(encoding="utf-8"))
    answer = next(a for a in intake["raw_answers"] if "新证据明确" in a["answer_text"])
    req = review_request(later, later_candidates, "resolve")
    req["constraint_decisions"][0].update(note="Human checked exact new source",
        evidence=contract.source_ref(intake, answer, "新证据明确经营主体为虚构小馆"),
        resolution_target={"constraint_id": candidates["derived_authority_constraints"][0]["constraint_id"],
            "constraint_sha256": contract.digest(candidates["derived_authority_constraints"][0])})
    result = review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    assert result["status"] == "completed_persona_review_required"
    assert not contract.policy(contract.collect(tmp_path, later["business_id"]))["blockers"]
    assert all(contract.file_sha(p) == value for p, value in protected.items())


def test_unrelated_supplement_known_fact_never_clears_legacy_critical(tmp_path):
    from customer_intake_v1 import build_customer_intake
    raw = build_customer_intake(intake_id="intake_0001", intake_type="initial_onboarding",
        provisional_business_id="fictional_e2_business", business_ref=None,
        input_actor="authorized_business_representative", input_sources=[{"source_type": "fictional", "source_ref": "test"}],
        raw_answers=analysis.build_raw_answers(analysis.validate_request(request())),
        speaker_selection={"speaker_type": "generic", "selection_status": "deferred"}, created_at=STAMP)
    raw["conflicts"] = [{"constraint_id": "legacy_core", "severity": "critical", "resolved": False,
        "question": "核实主体身份", "production_blocked": True}]
    root = tmp_path / "data/customer_intakes/fictional_e2_business"
    for number in (1, 2):
        directory = root / f"intake_{number:04d}"; directory.mkdir(parents=True)
        intake = copy.deepcopy(raw); intake["intake_id"] = directory.name
        if number == 2:
            intake["conflicts"] = []; intake["target_gaps"] = [{"target_gap": "critical_constraints"}]
            (directory / "reviewed_persona_fact_candidates_v1.json").write_text(json.dumps({"fact_candidates": [{"candidate_state": "known_candidate", "human_review": {"decision": "approve"}}]}), encoding="utf-8")
        (directory / "customer_intake_v1.json").write_text(json.dumps(intake), encoding="utf-8")
    assert [v["constraint_id"] for v in review.combined_critical_constraints(tmp_path, "fictional_e2_business")] == ["legacy_core"]


def test_review_source_sha_tamper_fails_closed(tmp_path):
    summary, candidates = seed(tmp_path, ["publication_prohibition"])
    result = review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    path = Path(result["source"]["fact_candidates_path"])
    raw = json.loads(path.read_text(encoding="utf-8")); raw["created_at"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RuntimeError, match="candidate SHA"):
        contract.collect(tmp_path, summary["business_id"])


def test_confirmed_condition_and_prohibition_are_enforced_on_publication(tmp_path):
    summary, candidates = seed(tmp_path, ["conditional_fact", "publication_prohibition"])
    result = review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    path = Path(result["artifacts"]["business_persona_v1"])
    persona, _, _ = approve_persona(path, "fictional_authenticated_operator", "Fictional explicit approval", STAMP)
    contract.assert_publication_allowed(persona, path, ["宴席需要预约。"])
    contract.assert_publication_allowed(persona, path, ["菜单先确认人数。"])
    with pytest.raises(RuntimeError, match="CONDITION_MISSING"):
        contract.assert_publication_allowed(persona, path, ["宴席随时供应。"])
    with pytest.raises(RuntimeError, match="FORBIDDEN_PUBLICATION"):
        contract.assert_publication_allowed(persona, path, ["我们绝对最好。"])


def test_resolving_one_constraint_does_not_resolve_another(tmp_path):
    first = output(["identity_conflict"])
    other = copy.deepcopy(first["constraints"][0]); other["evidence_quote"] = "示例奖项尚未核实"
    first["constraints"].append(other)
    summary = analysis.analyze_customer_onboarding(request=request(), pipeline_root=tmp_path,
        extractor=lambda _: first, speaker_discovery_extractor=lambda _: {"speaker_candidates": []}, created_at=STAMP)
    candidates = json.loads(Path(summary["artifacts"]["fact_candidates_v1"]).read_text(encoding="utf-8"))
    review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    later, records = seed(tmp_path, ["identity_conflict"], "intake_0002")
    intake = contract.read(Path(later["artifacts"]["fact_candidates_v1"]).parent / "customer_intake_v1.json")
    answer = next(a for a in intake["raw_answers"] if "新证据明确" in a["answer_text"])
    req = review_request(later, records, "resolve")
    req["constraint_decisions"][0].update(note="Human reviewed only the specified conflict",
        evidence=contract.source_ref(intake, answer, "新证据明确经营主体为虚构小馆"),
        resolution_target={"constraint_id": candidates["derived_authority_constraints"][0]["constraint_id"],
            "constraint_sha256": contract.digest(candidates["derived_authority_constraints"][0])})
    result = review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    assert result["status"] == "completed_persona_blocked"
    remaining = contract.policy(contract.collect(tmp_path, later["business_id"]))["blockers"]
    assert [v["constraint_id"] for v in remaining] == [candidates["derived_authority_constraints"][1]["constraint_id"]]


def test_legacy_same_id_different_sources_only_exact_target_resolves(tmp_path):
    from customer_intake_v1 import build_customer_intake
    for number in (1, 2):
        identifier = f"intake_{number:04d}"
        raw = build_customer_intake(intake_id=identifier, intake_type="initial_onboarding",
            provisional_business_id="fictional_e2_business", business_ref=None,
            input_actor="authorized_business_representative", input_sources=[{"source_type": "fictional", "source_ref": "test"}],
            raw_answers=analysis.build_raw_answers(analysis.validate_request(request(identifier))),
            speaker_selection={"speaker_type": "generic", "selection_status": "deferred"}, created_at=STAMP)
        raw["conflicts"] = [{"constraint_id": "reused_legacy_id", "severity": "critical", "resolved": False,
            "question": f"核实第{number}个主体", "production_blocked": True}]
        directory = tmp_path / "data/customer_intakes/fictional_e2_business" / identifier
        directory.mkdir(parents=True)
        (directory / "customer_intake_v1.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    second = next(v for v in contract.legacy_critical_constraints(tmp_path, "fictional_e2_business") if v["source_intake_id"] == "intake_0002")
    summary, candidates = seed(tmp_path, ["identity_conflict"], "intake_0003")
    req = review_request(summary, candidates, "resolve")
    req["constraint_decisions"][0].update(note="明确只解决第二个历史来源，不能清除第一个来源",
        resolution_quote="新证据明确经营主体为虚构小馆",
        resolution_target={"constraint_id": second["constraint_id"], "constraint_sha256": contract.digest(second["record"]),
            "source_intake_id": second["source_intake_id"], "raw_answers_sha256": second["raw_answers_sha256"]})
    result = review.review_customer_facts(request=req, pipeline_root=tmp_path, reviewed_at=STAMP)
    assert result["status"] == "completed_persona_blocked"
    remaining = review.combined_critical_constraints(tmp_path, "fictional_e2_business")
    assert [v["question"] for v in remaining] == ["核实第1个主体"]
