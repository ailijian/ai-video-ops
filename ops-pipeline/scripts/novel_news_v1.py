"""Canonical Novel News beat generation and Human Review.

Repurpose News remains owned by news_delivery_v1.py. This operation consumes
an immutable Generation Request with one selected, novel opportunity and the
shared deterministic Generation Source Plan.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from close_generation_export_v1 import _empty_ledger, _build_fact_atoms
from content_quality_v1 import (
    LEDGER_SCHEMA_VERSION, STRONG_MEMORY_STATUSES,
    build_exported_semantic_ledger_update, canonical_sha256,
    replace_ledger_after_export,
)
from generate_mix_scripts_v1 import default_transport, safe_persona_projection, safe_speaker_projection
from privacy_projection_v1 import assert_safe_for_external_model, project_value
from news_delivery_v1 import (
    NewsDeliveryError, _append_presentation_history, _validate_title_against_fact,
    export_dynamic_news_xlsx,
)
from profile_compatibility_decisions_v1_1 import file_sha as sha256_file
from human_review_operations_v1 import io_path
from profile_compatibility_consumers_v1_1 import guarded as compatibility_guarded

SCHEMA = "novel-news-beat-plan-v1.0"
REVIEW_SCHEMA = "novel-news-human-review-v1.0"
PRICE_PATTERN = "pcv1_news_price_offer_led_micro_information"
SCENE_PATTERN = "pcv1_news_scene_contrast"
MIN_BEATS = 4
MAX_BEATS = 8
GENERATOR_SOURCE_SHA256 = sha256_file(Path(__file__))


class NovelNewsError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(io_path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NovelNewsError("NEWS_NOVEL_ARTIFACT_INVALID", f"Cannot read {path}") from exc
    if not isinstance(value, dict):
        raise NovelNewsError("NEWS_NOVEL_ARTIFACT_INVALID", f"Not a JSON object: {path}")
    return value


def _write_new(path: Path, value: dict[str, Any]) -> None:
    if value.get('schema_version') in {'novel-news-excel-export-receipt-v1.1',
        'novel-news-export-closure-v1.1', 'content-ledger-v1.0'}:
        from profile_compatibility_decisions_v1_1 import write_once
        write_once(path,value)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _paths(root: Path, request_id: str) -> dict[str, Path]:
    if not request_id.startswith("gen_") or not request_id[4:].isalnum():
        raise NovelNewsError("NEWS_NOVEL_REQUEST_ID_INVALID", "Invalid Generation Request ID.")
    return {
        "request": root / "data/generation_requests" / request_id / "generation_request_v1.json",
        "source_plan": root / "data/production_plans" / request_id / "generation_source_plan_v1.json",
        "plan": root / "data/generation_batches" / request_id / "novel_news_beat_plan_v1.json",
        "review": root / "data/generation_batches" / request_id / "novel_news_human_review_v1.json",
        "approved": root / "data/generation_batches" / request_id / "approved_novel_news_v1.json",
        "receipt": root / "data/generation_batches" / request_id / "novel_news_export_receipt_v1.json",
        "closure": root / "data/generation_batches" / request_id / "novel_news_export_closure_v1.json",
    }


def _structural_source_projection(
    root: Path, pattern_ref: dict[str, Any], case_refs: list[dict[str, Any]], source_plan=None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pattern_id = str(pattern_ref.get("pattern_id") or "")
    if not re.fullmatch(r"[a-z0-9_]+", pattern_id):
        raise NovelNewsError("NEWS_NOVEL_PATTERN_LINEAGE_INVALID", "Selected Pattern ID is invalid.")
    from news_runtime_v1_2 import configured,sources
    released=sources(root,source_plan) if configured(root) else None
    pattern_path = released[1] if released else root / "data/patterns/approved" / pattern_id / "pattern_v1.json"
    if not io_path(pattern_path).is_file() or sha256_file(pattern_path) != pattern_ref.get("approved_pattern_sha"):
        raise NovelNewsError("NEWS_NOVEL_PATTERN_LINEAGE_INVALID", "Selected Approved Pattern changed after source planning.")
    pattern = _read(pattern_path)
    if pattern.get("pattern_id") != pattern_id or pattern.get("status") != "approved":
        raise NovelNewsError("NEWS_NOVEL_PATTERN_LINEAGE_INVALID", "Selected Pattern is not Approved.")
    definition = pattern.get("definition") or {}
    pattern_projection = {
        "pattern_id": pattern_id,
        "invariants": definition.get("invariants") or [],
        "semantic_relation_guard": definition.get("semantic_relation_guard") or {},
        "scope_limitation": (pattern.get("scope") or {}).get("scope_limitation"),
    }
    supported_ids = set((pattern.get("scope") or {}).get("supported_case_ids") or [])
    case_projections: list[dict[str, Any]] = []
    for case_ref in case_refs:
        case_id = str(case_ref.get("case_id") or "")
        if not re.fullmatch(r"[0-9]+", case_id) or case_id not in supported_ids:
            raise NovelNewsError("NEWS_NOVEL_CASE_LINEAGE_INVALID", "Case is outside Approved Pattern support.")
        fingerprint_path = released[2].get(case_id) if released else root / "data/fingerprints" / case_id / "case_fingerprint_v1.json"
        if fingerprint_path is None:raise NovelNewsError('NEWS_NOVEL_CASE_LINEAGE_INVALID','Case is outside the exact active release')
        if not fingerprint_path.is_file() or sha256_file(fingerprint_path) != case_ref.get("fingerprint_sha"):
            raise NovelNewsError("NEWS_NOVEL_CASE_LINEAGE_INVALID", "Selected Case Fingerprint changed after source planning.")
        fingerprint = _read(fingerprint_path)
        if (
            fingerprint.get("case_id") != case_id
            or fingerprint.get("fingerprint_scope") != "case_structural_evidence_only"
            or (fingerprint.get("authority") or {}).get("case_specific_facts_transferred") is not False
            or fingerprint.get("source_case_sha256") != case_ref.get("approved_case_sha")
        ):
            raise NovelNewsError("NEWS_NOVEL_CASE_LINEAGE_INVALID", "Selected Fingerprint is not valid structural evidence.")
        carrier = fingerprint.get("semantic_carrier_features") or {}
        visual = fingerprint.get("visual_state_features") or {}
        case_projections.append({
            "case_id": case_id,
            "semantic_carrier_type": carrier.get("carrier_type"),
            "continuous_narration_required": carrier.get("continuous_narration_required"),
            "observed_micro_beat_count": carrier.get("micro_beat_count"),
            "observed_visual_state_count": visual.get("ordered_state_count"),
            "text_visual_relationship": visual.get("text_visual_relationship"),
        })
    return pattern_projection, case_projections


def _source_context(root: Path, request_id: str) -> dict[str, Any]:
    paths = _paths(root, request_id)
    request = _read(paths["request"])
    source_plan = _read(paths["source_plan"])
    if source_plan.get('profile_compatibility_v1_2')!=request.get('profile_compatibility_v1_2'):
        raise NovelNewsError('NEWS_NOVEL_SOURCE_BINDING_INVALID','Request and native Source Plan use different News versions')
    selected = request.get("selected_content") or {}
    pattern_refs = source_plan.get("selected_patterns") or []
    case_refs = source_plan.get("eligible_case_pool") or []
    if (
        request.get("target_profile") != "news"
        or request.get("reuse_intent") != "novel_content"
        or request.get("quantity") != 1
        or not selected.get("concept_id")
        or source_plan.get("request_id") != request_id
        or (source_plan.get("request") or {}).get("request_sha") != sha256_file(paths["request"])
        or (source_plan.get("coverage") or {}).get("status") != "supported"
        or len(pattern_refs) != 1
        or not case_refs
    ):
        raise NovelNewsError("NEWS_NOVEL_SOURCE_COVERAGE_UNSUPPORTED", "Approved Novel News source coverage is required.")
    pattern_id = pattern_refs[0]["pattern_id"]
    if pattern_id == SCENE_PATTERN:
        validation_path = paths["request"].with_name("scene_contrast_real_validation_approval_v1.json")
        validation = _read(validation_path) if validation_path.is_file() else {}
        if not (
            request.get("controlled_scene_validation") is True
            and validation.get("schema_version") == "scene-contrast-real-validation-approval-v1.0"
            and validation.get("request_id") == request_id
            and validation.get("request_sha256") == sha256_file(paths["request"])
            and validation.get("human_gate") is True
            and validation.get("correspondence_confirmed") is True
        ):
            raise NovelNewsError("NEWS_SCENE_PRODUCTION_VALIDATION_REQUIRED", "Scene Contrast requires a separate Human-authorized controlled validation.")
    elif pattern_id != PRICE_PATTERN or "pricing_facts" not in selected.get("primary_fact_refs", []):
        raise NovelNewsError("NEWS_NOVEL_PATTERN_SCOPE_INVALID", "Price / Offer must be the primary semantic anchor.")
    lineage = request.get("lineage") or {}
    persona_ref = lineage.get("business_persona_ref") or {}
    speaker_ref = lineage.get("speaker_persona_ref") or {}
    persona_path = Path(str(persona_ref.get("path") or ""))
    speaker_path = Path(str(speaker_ref.get("path") or ""))
    for ref, path in ((persona_ref, persona_path), (speaker_ref, speaker_path)):
        if not path.is_file() or sha256_file(path) != ref.get("file_sha256"):
            raise NovelNewsError("NEWS_NOVEL_PERSONA_LINEAGE_INVALID", "Approved Persona changed after Request creation.")
    persona = _read(persona_path)
    from news_runtime_v1_2 import configured,validate_request_personas
    if configured(root):validate_request_personas(root,request)
    from customer_constraints_v1 import assert_production_allowed
    assert_production_allowed(persona, persona_path, consumer="novel_news")
    speaker = _read(speaker_path)
    safe_business = safe_persona_projection(persona)
    safe_speaker = safe_speaker_projection(speaker)
    atoms = _build_fact_atoms(persona, sha256_file(persona_path), speaker, sha256_file(speaker_path))
    safe_fields = set(safe_business["facts"])
    allowed_fields = set(selected.get("primary_fact_refs") or []) | set(selected.get("supporting_fact_refs") or [])
    usable_atoms = {
        item["fact_atom_id"]: {
            **item,
            "original_known_fact": str(project_value(item["original_known_fact"], "safe_verbatim")),
        } for item in atoms
        if item.get("field") in (safe_fields & allowed_fields)
    }
    primary_atoms = set(selected.get("primary_fact_atom_refs") or [])
    if pattern_id == PRICE_PATTERN and (not primary_atoms or not primary_atoms <= set(usable_atoms)):
        raise NovelNewsError("NEWS_NOVEL_PRICE_AUTHORITY_INVALID", "Primary price Fact Atom is not Approved and privacy-safe.")
    state_a_atoms = set(selected.get("state_a_fact_atom_refs") or [])
    state_b_atoms = set(selected.get("state_b_fact_atom_refs") or [])
    if pattern_id == SCENE_PATTERN and (
        not state_a_atoms or not state_b_atoms or state_a_atoms & state_b_atoms
        or not state_a_atoms <= set(usable_atoms) or not state_b_atoms <= set(usable_atoms)
        or not selected.get("approved_state_correspondence_refs")
    ):
        raise NovelNewsError("NEWS_SCENE_CORRESPONDENCE_INVALID", "State A/B must cite distinct Approved Customer Fact Atoms.")
    pattern_structure, case_structures = _structural_source_projection(root, pattern_refs[0], case_refs,source_plan)
    return {
        "paths": paths, "request": request, "source_plan": source_plan,
        "selected": selected, "pattern_id": pattern_id,
        "persona": persona, "speaker": speaker,
        "safe_business": safe_business, "safe_speaker": safe_speaker,
        "usable_atoms": usable_atoms, "primary_atoms": primary_atoms,
        "state_a_atoms": state_a_atoms, "state_b_atoms": state_b_atoms,
        "all_atoms": atoms,
        "pattern_structure": pattern_structure, "case_structures": case_structures,
    }


def _normalize_beats(raw: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not MIN_BEATS <= len(raw) <= MAX_BEATS:
        raise NovelNewsError("NEWS_NOVEL_BEAT_COUNT_INVALID", "One News video requires 4–8 ordered beats.")
    atoms = context["usable_atoms"]
    normalized: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    for order, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise NovelNewsError("NEWS_NOVEL_BEAT_INVALID", "Beat must be an object.")
        text = str(item.get("text") or "").strip()
        role = str(item.get("semantic_role") or "").strip()
        visual = str(item.get("visual_anchor") or "").strip()
        duration = str(item.get("duration_guidance") or "").strip()
        refs = item.get("source_fact_refs") or []
        if not text or not role or not visual or not duration or not isinstance(refs, list) or len(refs) != 1:
            raise NovelNewsError("NEWS_NOVEL_BEAT_INVALID", "Beat requires role, text, visual anchor, duration and one Fact Atom ref.")
        atom_id = str(refs[0])
        atom = atoms.get(atom_id)
        if atom is None:
            raise NovelNewsError("NEWS_NOVEL_UNSUPPORTED_FACT", "Beat refers to a Fact Atom outside Approved Customer Truth.")
        if text in seen_text:
            raise NovelNewsError("NEWS_NOVEL_PADDING", "Duplicate micro-information beat is not allowed.")
        try:
            _validate_title_against_fact(text, str(atom["original_known_fact"]))
        except NewsDeliveryError as exc:
            raise NovelNewsError("NEWS_NOVEL_UNGROUNDED_BEAT", str(exc)) from exc
        source_compact = re.sub(r"[\W_]+", "", str(atom["original_known_fact"]))
        text_compact = re.sub(r"[\W_]+", "", text)
        if not text_compact or text_compact not in source_compact:
            raise NovelNewsError(
                "NEWS_NOVEL_UNGROUNDED_BEAT",
                "Beat wording must be an exact grounded excerpt of its approved Fact Atom.",
            )
        if context["pattern_id"] == PRICE_PATTERN and order == 1 and (atom_id not in context["primary_atoms"] or role != "price_offer_first_semantic_anchor"):
            raise NovelNewsError("NEWS_NOVEL_PATTERN_INVARIANT", "First beat must retain the selected Price / Offer anchor.")
        if context["pattern_id"] == SCENE_PATTERN and (
            (order == 1 and (role != "state_a" or atom_id not in context["state_a_atoms"]))
            or (order == len(raw) and (role != "state_b" or atom_id not in context["state_b_atoms"]))
        ):
            raise NovelNewsError("NEWS_SCENE_PATTERN_INVARIANT", "First and last beats must preserve approved State A → State B correspondence.")
        seen_text.add(text)
        normalized.append({
            "beat_id": f"B{order:03d}", "order": order,
            "semantic_role": role, "text": text,
            "visual_anchor": visual, "duration_guidance": duration,
            "source_fact_refs": [atom_id],
            "evidence_lineage": [{
                "fact_atom_id": atom_id,
                "source_field": atom["field"],
                "approved_persona_sha256": atom["persona_sha256"],
                "source_refs": atom.get("source_refs") or [],
            }],
        })
    return normalized


def _generation_prompt(context):
    pattern_instruction = (
        "First beat must be the selected price/offer anchor; preserve qualifiers such as 通常/约/左右/免费."
        if context["pattern_id"] == PRICE_PATTERN else
        "First beat must cite an approved State A atom with role state_a. Last beat must cite a distinct approved State B atom with role state_b. Do not invent an A/B relationship."
    )
    # Internal Case IDs, atom digests and source lineage have no linguistic
    # purpose in an external prompt. Use request-local opaque aliases and map
    # them back before the unchanged Native grounding validator.
    aliases={atom_id:'FACT_'+chr(65+i//26)+chr(65+i%26)
        for i,atom_id in enumerate(sorted(context['usable_atoms']))}
    reverse_aliases={alias:atom_id for atom_id,alias in aliases.items()}
    prompt = json.dumps({
        "task": "Produce exactly 4–8 ordered Chinese News micro-information beats as JSON. Each text must quote its approved Fact Atom verbatim or use a contiguous excerpt; never add or rearrange factual words. Do not create any new Customer Fact. Do not import Case facts. " + pattern_instruction + " Every beat cites exactly one allowed Fact Atom ID. Return {\"beats\":[{\"semantic_role\":...,\"text\":...,\"visual_anchor\":...,\"duration_guidance\":...,\"source_fact_refs\":[atom_id]}]}.",
        "selected_opportunity": {key:context['selected'].get(key) for key in (
            'content_job','audience_need','primary_topic','central_claim','why_publish')},
        "approved_business_facts": context["safe_business"],
        "approved_speaker_facts": context["safe_speaker"],
        "approved_pattern_structure_only": project_value(context["pattern_structure"],'safe_semantic'),
        "eligible_case_fingerprint_structure_only": [
            {key:value for key,value in item.items() if key!='case_id'} for item in context["case_structures"]],
        "allowed_fact_atoms": [
            {"fact_atom_id": aliases[atom_id], "field": atom["field"], "fact": atom["original_known_fact"]}
            for atom_id, atom in context["usable_atoms"].items()
        ],
    }, ensure_ascii=False)
    assert_safe_for_external_model(prompt)
    return prompt, reverse_aliases


def _response_beats(response, context):
    if not isinstance(response, dict):
        raise NovelNewsError('NEWS_NOVEL_RESPONSE_INVALID', 'Model response must be an object.')
    _, reverse_aliases = _generation_prompt(context)
    payload = response.get("payload") or response
    if not isinstance(payload, dict):
        raise NovelNewsError('NEWS_NOVEL_RESPONSE_INVALID', 'Model payload must be an object.')
    raw=payload.get('beats')
    if isinstance(raw,list):
        raw=[{**item,'source_fact_refs':[reverse_aliases.get(v,v) for v in item.get('source_fact_refs',[])]}
            if isinstance(item,dict) else item for item in raw]
    return _normalize_beats(raw, context)


def _validated_plan(context, plan):
    if (plan.get('schema_version') != SCHEMA or plan.get('status') != 'review_required'
            or plan.get('request_sha256') != sha256_file(context['paths']['request'])
            or plan.get('source_plan_sha256') != sha256_file(context['paths']['source_plan'])
            or plan.get('selected_concept_id') != context['selected']['concept_id']
            or plan.get('selected_pattern_id') != context['pattern_id']
            or _normalize_beats(plan.get('micro_information_beats'), context) != plan.get('micro_information_beats')):
        raise NovelNewsError('NEWS_NOVEL_PLAN_LINEAGE_CONFLICT', 'Plan must pass the original Native validation.')
    return plan


def _generation_plan(context, response, attempt, response_sha, created_at):
    from novel_news_generation_recovery_v1 import directory
    task_binding = directory(context['paths']['request'].parents[3], context['request']['request_id'],
                             attempt['operation_id']) / 'task.json'
    return {
        "schema_version": SCHEMA, "request_id": context['request']['request_id'],
        "created_at": created_at, "status": "review_required",
        "generated_by": 'console-principal:' + attempt['intent']['actor']['namespace'] + ':' + str(attempt['intent']['actor']['user_id']),
        "request_sha256": sha256_file(context["paths"]["request"]),
        "source_plan_sha256": sha256_file(context["paths"]["source_plan"]),
        "selected_concept_id": context["selected"]["concept_id"],
        "selected_pattern_id": context["pattern_id"],
        "micro_information_beats": _response_beats(response, context),
        "authority": {"human_review_required": True, "case_facts_transferred": False, "business_facts_copied_to_speaker": False},
        "model_call": {"remote": response['transport_mode'] == 'native-remote', "response_sha256": response.get("response_sha256"), "usage": response.get("usage") or {}},
        "generation_attempt": {'operation_id': attempt['operation_id'], 'intent_sha256': attempt['sha256'],
                               'prepared_response_sha256': response_sha,
                               'task_binding_sha256': sha256_file(task_binding) if task_binding.is_file() else None},
    }


def _generation_parameters():
    import os
    return {'prompt_version': 'novel-news-grounded-atoms-v1.1', 'model': os.getenv('DEEPSEEK_MODEL') or 'deepseek-chat',
            'transport': 'deepseek-json-0.7-10000-v1', 'generator_owner_sha256': GENERATOR_SOURCE_SHA256,
            'transport_owner_sha256': sha256_file(Path(default_transport.__code__.co_filename)),
            'minimum_beats': MIN_BEATS, 'maximum_beats': MAX_BEATS}


def prepare_novel_news_generation(*, pipeline_root, request_id, authorization_context, expected_parent=None):
    from novel_news_generation_recovery_v1 import append, commit_lock, head, snapshot, task_running, GenerationError, mutation_fence
    from news_export_recovery_v1 import current_authority
    from news_qualification_v1_2 import prohibit_write
    root = Path(pipeline_root).resolve()
    prohibit_write(root)
    context = _source_context(root, request_id)
    with mutation_fence(root), current_authority(root, context['request'].get('profile_compatibility_v1_2')), commit_lock(root, request_id):
        context = _source_context(root, request_id)
        prompt, _ = _generation_prompt(context)
        latest = head(root, request_id)
        if context['paths']['plan'].exists():
            raise GenerationError('ALREADY_GENERATED')
        if expected_parent and latest and latest['sha256'] == expected_parent:
            state = novel_generation_state(root, request_id, context=context)
            if state['recovery_state'] not in {'dispatched_outcome_unknown', 'confirmed_failure'}:
                raise GenerationError('RETRY_NOT_ALLOWED')
            db = authorization_context['authorization']['database_path']
            if task_running(db, latest['intent']['task_operation_identity']):
                raise GenerationError('EXECUTOR_ACTIVE')
        return append(root, request_id, source=snapshot(root, context), prompt=prompt,
                      parameters=_generation_parameters(), authorization_context=authorization_context,
                      expected_parent=expected_parent)


def novel_generation_state(root, request_id, *, context=None, completed=False):
    from novel_news_generation_recovery_v1 import head, evidence, snapshot, directory, GenerationError
    context = context or _source_context(root, request_id)
    attempt = head(root, request_id)
    plan_path = context['paths']['plan']
    state = {'artifact_present': plan_path.is_file(), 'ready_for_human_review': False,
             'recovery_state': 'not_admitted', 'operation_id': None, 'intent_sha256': None}
    if not attempt:
        if plan_path.is_file():
            if not completed:
                raise GenerationError('LEGACY_UNBOUND_PLAN', '旧版生成缺少可信尝试记录，需要核对原操作。')
            _validated_plan(context, _read(plan_path))
            state.update(ready_for_human_review=True, recovery_state='review_required', legacy_completed=True)
        return state
    state.update(operation_id=attempt['operation_id'], intent_sha256=attempt['sha256'])
    state['recovery_state'] = 'not_dispatched'
    if not completed and attempt['intent']['parameters'] != _generation_parameters():
        raise GenerationError('OPERATION_CONFLICT')
    current_snapshot = snapshot(root, context)
    if completed:
        # Native export validation below proves the immutable completed Ledger
        # event. Later legal appends cannot rewrite this historical result.
        current_snapshot['memory_sha256'] = attempt['intent']['snapshot']['memory_sha256']
    if current_snapshot != attempt['intent']['snapshot']:
        raise GenerationError('SOURCE_CHANGED')
    dispatched = evidence(root, request_id, attempt, 'dispatch')
    response = evidence(root, request_id, attempt, 'response')
    result = evidence(root, request_id, attempt, 'result')
    task_binding = evidence(root, request_id, attempt, 'task')
    if task_binding and task_binding['task_operation_identity'] != attempt['intent']['task_operation_identity']:
        raise GenerationError('EVIDENCE_INVALID')
    if response and not dispatched or result and not response:
        raise GenerationError('EVIDENCE_INVALID')
    if plan_path.is_file():
        if not response:
            raise GenerationError('EVIDENCE_INVALID')
        plan = _validated_plan(context, _read(plan_path))
        response_sha = sha256_file(directory(root, request_id, attempt['operation_id']) / 'response.json')
        expected = _generation_plan(context, response['response'], attempt, response_sha, response['received_at'])
        if plan != expected or (result and (result.get('plan_sha256') != sha256_file(plan_path)
                or result.get('prepared_response_sha256') != response_sha)):
            raise GenerationError('EVIDENCE_INVALID')
        state.update(ready_for_human_review=True, recovery_state='review_required',
                     plan_sha256=sha256_file(plan_path), result_present=bool(result))
    elif response:
        try:
            _response_beats(response['response'], context)
            state['recovery_state'] = 'validated_result_unpublished'
        except NovelNewsError:
            state['recovery_state'] = 'confirmed_failure'
    elif dispatched:
        state['recovery_state'] = 'dispatched_outcome_unknown'
    return state


def generate_novel_news_plan(*, pipeline_root: Path, request_id: str,
    transport: Callable[[str], dict[str, Any]] | None = None, generated_by=None,
    authorization_context=None, operation_id=None, intent_sha256=None, task_id=None):
    from novel_news_generation_recovery_v1 import (head, directory, commit_lock, snapshot,
        assert_current, record, evidence, GenerationError, mutation_fence)
    from operation_lock_v1 import operation_lock
    from profile_compatibility_decisions_v1_1 import write_once
    from news_export_recovery_v1 import current_authority
    root = Path(pipeline_root).resolve()
    # Missing protocol is never permission to redispatch an old Task. Only the
    # authenticated admission route (or explicit offline prepare) creates it.
    from news_qualification_v1_2 import prohibit_write
    prohibit_write(root)
    attempt = head(root, request_id)
    if not attempt or operation_id != attempt['operation_id'] or intent_sha256 != attempt['sha256']:
        raise GenerationError('OPERATION_REQUIRED')
    binding = evidence(root, request_id, attempt, 'task')
    if binding and binding['task_operation_identity'] != attempt['intent']['task_operation_identity']:
        raise GenerationError('OPERATION_CONFLICT')
    if task_id:
        if not binding:
            raise GenerationError('TASK_BINDING_PENDING')
        if binding['task_id'] != task_id or binding['task_operation_identity'] != attempt['intent']['task_operation_identity']:
            raise GenerationError('OPERATION_CONFLICT')
    with operation_lock(root, 'novel-news-generation-executor:' + operation_id, timeout_seconds=0):
        context = _source_context(root, request_id)
        source = snapshot(root, context)
        assert_current(root, request_id, attempt, source, authorization_context)
        prompt, _ = _generation_prompt(context)
        import hashlib
        if (hashlib.sha256(prompt.encode()).hexdigest() != attempt['intent']['prompt_sha256']
                or _generation_parameters() != attempt['intent']['parameters']):
            raise GenerationError('OPERATION_CONFLICT')
        response = evidence(root, request_id, attempt, 'response')
        if response is None:
            with mutation_fence(root), current_authority(root, context['request'].get('profile_compatibility_v1_2')), commit_lock(root, request_id):
                assert_current(root, request_id, attempt, snapshot(root, _source_context(root, request_id)), authorization_context)
                if evidence(root, request_id, attempt, 'dispatch'):
                    raise GenerationError('OUTCOME_UNKNOWN', '本次模型执行结果无法确认，系统不会自动重复生成。')
                record(root, request_id, attempt, 'dispatch', dispatched_at=_now())
            if transport is None:
                transport = default_transport(_generation_parameters()['model'])
                transport_mode = 'native-remote'
            else:
                transport_mode = 'explicit-transport-boundary'
            received = transport(prompt)
            # Keep only replay inputs and non-secret usage metadata in private
            # metrics. Never project an unvalidated response into the Console.
            saved = {'payload': received.get('payload') or received,
                     'response_sha256': received.get('response_sha256'), 'usage': received.get('usage') or {},
                     'transport_mode': transport_mode}
            if len(json.dumps(saved, ensure_ascii=False).encode()) > 2_000_000:
                raise GenerationError('RESPONSE_TOO_LARGE')
            with mutation_fence(root):
                response = record(root, request_id, attempt, 'response', received_at=_now(), response=saved)
        response_path = directory(root, request_id, operation_id) / 'response.json'
        plan = _generation_plan(context, response['response'], attempt, sha256_file(response_path), response['received_at'])
        with mutation_fence(root), current_authority(root, context['request'].get('profile_compatibility_v1_2')), commit_lock(root, request_id):
            # The old executor may still return after its Task lease expires.
            # Only the current immutable head can publish into the original path.
            current_context = _source_context(root, request_id)
            assert_current(root, request_id, attempt, snapshot(root, current_context), authorization_context)
            _validated_plan(current_context, plan)
            write_once(context['paths']['plan'], plan)
            record(root, request_id, attempt, 'result', outcome='review_required',
                   plan_sha256=sha256_file(context['paths']['plan']), prepared_response_sha256=sha256_file(response_path))
        return plan


@compatibility_guarded
def review_novel_news_plan(
    *, pipeline_root: Path, request_id: str,
    decisions: list[dict[str, Any]], reviewer: str,
) -> dict[str, Any]:
    context = _source_context(pipeline_root.expanduser().resolve(), request_id)
    if not novel_generation_state(pipeline_root.expanduser().resolve(), request_id, context=context)['ready_for_human_review']:
        raise NovelNewsError('NEWS_NOVEL_PLAN_NOT_READY', 'Generation has no validated current result.')
    paths = context["paths"]
    plan = _read(paths["plan"])
    if plan.get("schema_version") != SCHEMA or plan.get("request_sha256") != sha256_file(paths["request"]):
        raise NovelNewsError("NEWS_NOVEL_PLAN_INVALID", "Plan lineage is invalid.")
    if paths["approved"].is_file():
        raise NovelNewsError("NEWS_NOVEL_ALREADY_APPROVED", "Human Review is immutable; do not submit it twice.")
    original = plan["micro_information_beats"]
    by_id = {str(item.get("beat_id")): item for item in decisions}
    if len(by_id) != len(original) or set(by_id) != {item["beat_id"] for item in original}:
        raise NovelNewsError("NEWS_NOVEL_REVIEW_INCOMPLETE", "Every beat requires one Human decision.")
    selected: list[dict[str, Any]] = []
    for beat in original:
        decision = by_id[beat["beat_id"]]
        action = decision.get("decision")
        if action not in {"approved", "revised", "rejected"}:
            raise NovelNewsError("NEWS_NOVEL_REVIEW_INVALID", "Unknown Human decision.")
        if action == "rejected":
            continue
        revised = dict(beat)
        if action == "revised":
            revised["text"] = str(decision.get("revised_text") or "").strip()
        selected.append(revised)
    if not MIN_BEATS <= len(selected) <= MAX_BEATS:
        raise NovelNewsError("NEWS_NOVEL_REVIEW_BEAT_COUNT", "Approved video still requires 4–8 beats.")
    approved_beats = _normalize_beats(selected, context)
    approved = {
        "schema_version": "approved-novel-news-v1.0", "request_id": request_id,
        "status": "approved_for_export", "reviewed_at": _now(),
        "reviewed_by": reviewer, "human_gate": True,
        "plan_sha256": sha256_file(paths["plan"]),
        "micro_information_beats": approved_beats,
        "selected_pattern_id": context["pattern_id"],
        "selected_concept_id": context["selected"]["concept_id"],
    }
    review_artifact = {"schema_version": REVIEW_SCHEMA, "request_id": request_id, "reviewed_by": reviewer, "reviewed_at": approved["reviewed_at"], "decisions": decisions}
    if paths["review"].is_file():
        prior = _read(paths["review"])
        if any(prior.get(key) != review_artifact[key] for key in ("schema_version", "request_id", "reviewed_by", "decisions")):
            raise NovelNewsError("NEWS_NOVEL_REVIEW_CONFLICT", "Existing Human Review has different decisions.")
        approved["reviewed_at"] = prior.get("reviewed_at") or approved["reviewed_at"]
    else:
        _write_new(paths["review"], review_artifact)
    _write_new(paths["approved"], approved)
    return approved


def _template(root: Path) -> Path:
    from news_runtime_v1_2 import configured,current
    from profile_compatibility_decisions_v1_1 import resolve_ref
    if configured(root):
        active,binding=current(root)
        profile=_read(resolve_ref(active['bundle_root'],binding['profile_ref']))
        return resolve_ref(active['bundle_root'],profile['export_contract']['template_ref'])
    registry = _read(root / "data/production_profiles/production_profile_registry_v1.json")
    contract = ((registry.get("profiles") or {}).get("news") or {}).get("export_contract") or {}
    recorded = Path(str(contract.get("template_path") or ""))
    candidate = recorded if recorded.is_file() else root / "output" / recorded.name
    if not candidate.is_file() or sha256_file(candidate) != contract.get("template_sha256"):
        raise NovelNewsError("NEWS_NOVEL_TEMPLATE_LINEAGE_INVALID", "Registered News Excel template is missing or changed.")
    return candidate


def export_novel_news(*, pipeline_root: Path, request_id: str, exported_by: str = "",
                      export_context: dict | None = None) -> dict[str, Any]:
    from news_export_recovery_v1 import native_operation, current_authority
    root = pipeline_root.expanduser().resolve()
    request = _read(_paths(root, request_id)["request"])
    source = _read(_paths(root, request_id)["source_plan"])
    binding = source.get("profile_compatibility_v1_2") or source.get("profile_compatibility_v1_1")
    with native_operation(root, str(request["persona_id"])), current_authority(root, binding):
        return _export_novel_news_native(pipeline_root=root, request_id=request_id,
            exported_by=exported_by, export_context=export_context)


def _export_novel_news_native(
    *, pipeline_root: Path, request_id: str, exported_by: str, export_context: dict | None,
) -> dict[str, Any]:
    root = pipeline_root.expanduser().resolve()
    context = _source_context(root, request_id)
    paths = context["paths"]
    approved = _read(paths["approved"])
    if (
        approved.get("schema_version") != "approved-novel-news-v1.0"
        or approved.get("status") != "approved_for_export"
        or approved.get("human_gate") is not True
        or approved.get("plan_sha256") != sha256_file(paths["plan"])
    ):
        raise NovelNewsError("NEWS_NOVEL_REVIEW_AUTHORITY_INVALID", "Human-approved News beats are required for export.")
    from news_export_recovery_v1 import verify_native_human_bundle
    verify_native_human_bundle(root, request=paths['request'], plan=paths['plan'], review=paths['review'],
        approved=paths['approved'], kind='novel')
    beats = _normalize_beats(approved.get("micro_information_beats"), context)
    business_id = str(context["request"]["persona_id"])
    ledger_path = root / "data/content_ledgers" / business_id / "content_ledger_v1.json"
    content_id = request_id + "-N001"
    if ledger_path.is_file():
        current_ledger = _read(ledger_path)
        if current_ledger.get("schema_version") != LEDGER_SCHEMA_VERSION or current_ledger.get("business_id") != business_id:
            raise NovelNewsError("NEWS_NOVEL_LEDGER_INVALID", "Canonical business Content Ledger is invalid.")
        if not any(item.get("content_id") == content_id for item in current_ledger.get("entries") or []):
            if context["pattern_id"] == PRICE_PATTERN:
                from novel_news_opportunity_v1 import price_novelty_status
                primary_atom = context["usable_atoms"][next(iter(context["primary_atoms"]))]
                still_novel = price_novelty_status(primary_atom, context["selected"], current_ledger) == "novel"
            else:
                from content_quality_v1 import novelty_evaluation
                still_novel = not novelty_evaluation(context["selected"], list(current_ledger.get("entries") or [])).get("hard_duplicate")
            if not still_novel:
                raise NovelNewsError(
                    "NEWS_NOVEL_OPPORTUNITY_NO_LONGER_NOVEL",
                    "Another approved content export has already communicated this selected opportunity.",
                )
    template = _template(root)
    output_path = root / "output" / f"News新内容_{request_id}.xlsx"
    titles = [item["text"] for item in beats]
    from news_export_recovery_v1 import (
        NOVEL_RECEIPT, NOVEL_CLOSURE, NewsExportError, source_snapshot, prepare_publication,
        receipt_publication, validate_receipt_publication, ledger_prefix, validate_ledger_prefix,
    )
    directory = paths["approved"].parent
    if paths["receipt"].is_file() and paths["closure"].is_file():
        validate_novel_news_export(pipeline_root=root, request_id=request_id)
        return {"request_id": request_id, "output_path": str(output_path), "output_name": output_path.name,
            "content_id": content_id, "presentation_id": request_id + "-P001",
            "new_semantic_content_count_delta": 1, "remote_model_called": False, "recovered": True}
    lineage = context["request"]["lineage"]
    from news_runtime_v1_2 import configured,sources as released_sources
    if configured(root):
        released=released_sources(root,context['source_plan'])
        structural=[paths['source_plan'],released[1],*released[2].values()]
    else:
        structural = [paths["source_plan"], root / "data/patterns/approved" / context["pattern_id"] / "pattern_v1.json"]
        structural.extend(root / "data/fingerprints" / c["case_id"] / "case_fingerprint_v1.json"
                          for c in context["source_plan"]["eligible_case_pool"])
    sources = source_snapshot(root, request=paths["request"], plan=paths["plan"], review=paths["review"],
        approved=paths["approved"], business=Path(lineage["business_persona_ref"]["path"]),
        speaker=Path(lineage["speaker_persona_ref"]["path"]), structural=structural,
        semantic_source=context["selected"], binding=context["source_plan"].get("profile_compatibility_v1_2") or
        context["source_plan"].get("profile_compatibility_v1_1"), consumer="novel_news")
    intent, prepared = prepare_publication(root, directory, request_id=request_id, request_type="novel_content",
        business_id=business_id, speaker_id=context["request"]["speaker_persona"], sources=sources,
        template=template, output=output_path, titles=titles, context=export_context, renderer=export_dynamic_news_xlsx)
    if not paths["receipt"].is_file():
        _write_new(paths["receipt"], {
            "schema_version": NOVEL_RECEIPT, "request_id": request_id, "reuse_intent": "novel_content",
            "created_at": intent["created_at"], "output_path": str(output_path),
            "output_sha256": sha256_file(output_path), "publication": receipt_publication(root, directory),
            "approved_ref": {"path": str(paths["approved"]), "sha256": sha256_file(paths["approved"])},
            "validation_passed": True, "actor": intent["actor"],
        })
    receipt = _read(paths["receipt"])
    if receipt.get("schema_version") != NOVEL_RECEIPT or receipt.get("approved_ref", {}).get("sha256") != sha256_file(paths["approved"]):
        raise NewsExportError("NEWS_EXPORT_RECEIPT_CONFLICT")
    validate_receipt_publication(root, directory, receipt, output=output_path, template=template, titles=titles)
    exported_at = intent["created_at"]
    entry = {
        "content_id": content_id, "concept_ref": context["selected"]["concept_id"],
        "business_id": business_id, "speaker_id": context["request"]["speaker_persona"],
        "production_profile": "news", "profile": "news", "reuse_intent": "novel_content",
        "batch_ref": request_id, "status": "exported",
        "semantic_signature": context["selected"]["semantic_signature"],
        "central_claim": context["selected"]["central_claim"],
        "title": titles[0], "narration": "。".join(titles),
        "primary_fact_refs": context["selected"]["primary_fact_refs"],
        "supporting_fact_refs": context["selected"]["supporting_fact_refs"],
        "primary_fact_atom_refs": context["selected"]["primary_fact_atom_refs"],
        "fact_atom_refs": sorted({ref for beat in beats for ref in beat["source_fact_refs"]}),
        "approved_at": approved["reviewed_at"], "exported_at": exported_at,
        "new_semantic_content_count_delta": 1,
        "micro_information_beats": beats,
        "source_request_ref": {"path": str(paths["request"]), "sha256": sha256_file(paths["request"])},
        "approved_review_ref": {"path": str(paths["approved"]), "sha256": sha256_file(paths["approved"])},
        "export_receipt_ref": {"path": str(paths["receipt"]), "sha256": sha256_file(paths["receipt"])},
    }
    ledger_existed = ledger_path.is_file()
    ledger = _read(ledger_path) if ledger_existed else _empty_ledger(business_id=business_id, created_at=context["request"]["created_at"])
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION or ledger.get("business_id") != business_id:
        raise NovelNewsError("NEWS_NOVEL_LEDGER_INVALID", "Canonical business Content Ledger is invalid.")
    existing = [item for item in ledger.get("entries") or [] if item.get("content_id") == content_id]
    if existing:
        if len(existing) != 1 or any(existing[0].get(k) != entry.get(k) for k in
            ("source_request_ref", "approved_review_ref", "export_receipt_ref", "title", "narration", "semantic_signature", "business_id")):
            raise NovelNewsError("NEWS_NOVEL_LEDGER_CONFLICT", "Existing semantic entry has different Request lineage.")
    else:
        if context["pattern_id"] == PRICE_PATTERN:
            from novel_news_opportunity_v1 import price_novelty_status
            primary_atom = context["usable_atoms"][next(iter(context["primary_atoms"]))]
            still_novel = price_novelty_status(primary_atom, context["selected"], ledger) == "novel"
        else:
            from content_quality_v1 import novelty_evaluation
            still_novel = not novelty_evaluation(context["selected"], list(ledger.get("entries") or [])).get("hard_duplicate")
        if not still_novel:
            raise NovelNewsError(
                "NEWS_NOVEL_OPPORTUNITY_NO_LONGER_NOVEL",
                "Another approved content export has already communicated this selected opportunity.",
            )
        updated = build_exported_semantic_ledger_update(
            ledger, [entry], context["all_atoms"], exported_at=exported_at
        )
        updated["validation"] = {
            "passed": True, "entry_count": len(updated["entries"]),
            "strong_memory_count": sum(item.get("status") in STRONG_MEMORY_STATUSES for item in updated["entries"]),
            "latest_export_request_id": request_id,
        }
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if ledger_existed:
            replace_ledger_after_export(ledger_path, ledger, updated,
                news_export_intent_ref=receipt_publication(root,directory)['intent_ref'])
        else:
            _write_new(ledger_path, updated)
    presentation_id = request_id + "-P001"
    presentation = {
        "export_intent_ref": receipt_publication(root,directory)['intent_ref'],
        "presentation_id": presentation_id, "business_id": business_id,
        "speaker_id": context["request"]["speaker_persona"], "request_id": request_id,
        "production_profile": "news", "reuse_intent": "novel_content",
        "semantic_novelty": False, "semantic_content_created_separately": True,
        "source_content_ref": content_id, "selected_pattern_ref": context["pattern_id"],
        "status": "exported", "approved_at": approved["reviewed_at"], "exported_at": exported_at,
        "new_semantic_content_count_delta": 0, "novel_capacity_delta": 0,
        "communicated_information_units_created": False,
        "approved_titles": titles,
        "approval_ref": {"path": str(paths["approved"]), "sha256": sha256_file(paths["approved"])},
        "export_ref": {"path": str(output_path), "sha256": sha256_file(output_path)},
    }
    _append_presentation_history(ledger_path=ledger_path, source_content_id=content_id, entry=presentation)
    if not paths["closure"].is_file():
        _write_new(paths["closure"], {
            "schema_version": NOVEL_CLOSURE, "request_id": request_id,
            "receipt_ref": {"path": str(paths["receipt"]), "sha256": sha256_file(paths["receipt"])},
            "ledger_prefix": ledger_prefix(_read(ledger_path)),
            "content_id": content_id, "presentation_id": presentation_id,
            "semantic_entry_count_delta": 1, "presentation_semantic_entry_count_delta": 0,
            "approved_sha256": sha256_file(paths["approved"]),
            "output_sha256": sha256_file(output_path),
            "ledger_sha256_after": sha256_file(ledger_path),
            "validation": {"passed": True, "case_fact_transfer": False},
        })
    validate_novel_news_export(pipeline_root=root, request_id=request_id)
    closure = _read(paths["closure"])
    if closure.get("output_sha256") != sha256_file(output_path) or closure.get("semantic_entry_count_delta") != 1:
        raise NovelNewsError("NEWS_NOVEL_CLOSURE_INVALID", "Novel News export closure is invalid.")
    return {"request_id": request_id, "output_path": str(output_path), "output_name": output_path.name,
            "content_id": content_id, "presentation_id": presentation_id,
            "new_semantic_content_count_delta": 1, "remote_model_called": False}



def validate_novel_news_export(*, pipeline_root: Path, request_id: str) -> dict:
    """Strict native terminal reader, including legacy complete history."""
    from news_export_recovery_v1 import (NOVEL_RECEIPT, NOVEL_CLOSURE, NewsExportError,
        validate_workbook, validate_receipt_publication, validate_ledger_prefix)
    root = Path(pipeline_root).resolve()
    paths = _paths(root, request_id)
    context = _source_context(root, request_id)
    approved = _read(paths["approved"])
    from news_export_recovery_v1 import verify_native_human_bundle
    verify_native_human_bundle(root, request=paths['request'], plan=paths['plan'], review=paths['review'],
        approved=paths['approved'], kind='novel')
    receipt, closure = _read(paths["receipt"]), _read(paths["closure"])
    output = root / "output" / f"News新内容_{request_id}.xlsx"
    titles = [beat["text"] for beat in _normalize_beats(approved["micro_information_beats"], context)]
    if (approved.get("human_gate") is not True or approved.get("plan_sha256") != sha256_file(paths["plan"])
        or receipt.get("request_id") != request_id or receipt.get("validation_passed") is not True
        or receipt.get("output_path") != str(output) or receipt.get("output_sha256") != sha256_file(output)
        or receipt.get("approved_ref", {}).get("sha256") != sha256_file(paths["approved"])
        or closure.get("request_id") != request_id or closure.get("output_sha256") != sha256_file(output)
        or closure.get("approved_sha256") != sha256_file(paths["approved"])
        or closure.get("semantic_entry_count_delta") != 1):
        raise NewsExportError("NEWS_EXPORT_COMPLETION_INVALID", "导出结果需要重新核对。")
    validate_workbook(output, _template(root), titles)
    ledger = _read(root / "data/content_ledgers" / context["request"]["persona_id"] / "content_ledger_v1.json")
    entries = [x for x in ledger.get("entries", []) if x.get("content_id") == request_id + "-N001"]
    presentations = [x for x in ledger.get("extensions", {}).get("presentation_history_v1", {}).get("entries", [])
        if x.get("presentation_id") == request_id + "-P001"]
    if (len(entries) != 1 or len(presentations) != 1 or presentations[0].get("approved_titles") != titles
        or entries[0].get("export_receipt_ref", {}).get("sha256") != sha256_file(paths["receipt"])
        or presentations[0].get("export_ref", {}).get("sha256") != sha256_file(output)):
        raise NewsExportError("NEWS_EXPORT_LEDGER_HISTORY_CONFLICT")
    if receipt.get("schema_version") == NOVEL_RECEIPT:
        from news_export_recovery_v1 import check
        check(closure, NOVEL_CLOSURE)
        if closure.get("schema_version") != NOVEL_CLOSURE or closure.get("receipt_ref", {}).get("sha256") != sha256_file(paths["receipt"]):
            raise NewsExportError("NEWS_EXPORT_COMPLETION_INVALID")
        validate_receipt_publication(root, paths["approved"].parent, receipt, output=output, template=_template(root), titles=titles)
        validate_ledger_prefix(ledger, closure["ledger_prefix"])
    elif receipt.get("schema_version") != "novel-news-excel-export-receipt-v1.0" or closure.get("schema_version") != "novel-news-export-closure-v1.0":
        raise NewsExportError("NEWS_EXPORT_CONTRACT_INVALID")
    return receipt


def novel_news_status(*, pipeline_root: Path, request_id: str) -> dict[str, Any]:
    paths = _paths(pipeline_root.expanduser().resolve(), request_id)
    request = _read(paths["request"])
    if request.get("target_profile") != "news" or not request.get("selected_content"):
        raise NovelNewsError("NEWS_NOVEL_REQUEST_INVALID", "Not a Novel News Request.")
    source = _read(paths["source_plan"]) if paths["source_plan"].is_file() else None
    coverage = (source or {}).get("coverage") or {}
    context = None
    context_conflict = None
    if coverage.get('status') == 'supported':
        try:
            context = _source_context(pipeline_root.expanduser().resolve(), request_id)
        except RuntimeError as exc:
            context_conflict = getattr(exc, 'code', 'NEWS_GENERATION_SOURCE_CHANGED')
    stage = "source_plan" if not paths["source_plan"].is_file() else "generation"
    if source and coverage.get("status") != "supported":
        stage = "blocked"
    generation = {'artifact_present': False, 'ready_for_human_review': False, 'recovery_state': 'not_dispatched'}
    if context_conflict:
        generation.update(artifact_present=paths['plan'].is_file(), recovery_state='source_or_authorization_conflict',
                          native_code=context_conflict)
        stage = 'blocked'
    if context:
        from novel_news_generation_recovery_v1 import GenerationError
        try:
            generation = novel_generation_state(pipeline_root.expanduser().resolve(), request_id,
                context=context, completed=paths['closure'].is_file())
        except (GenerationError, NovelNewsError) as exc:
            if exc.code == 'NEWS_GENERATION_LEGACY_UNBOUND_PLAN':
                generation.update(artifact_present=True, recovery_state='dispatched_outcome_unknown',
                    legacy_unbound=True, native_code=exc.code)
            else:
                generation.update(recovery_state='source_or_authorization_conflict', native_code=exc.code)
                stage = 'blocked'
    if generation['ready_for_human_review']:
        stage = "review"
    if paths["approved"].is_file() and generation['recovery_state'] != 'source_or_authorization_conflict':
        stage = "export"
    export_recovery_state = "xlsx_not_generated"
    if paths["approved"].is_file():
        from news_export_recovery_v1 import partial_state, NewsExportError
        output = pipeline_root / "output" / f"News新内容_{request_id}.xlsx"
        export_recovery_state = partial_state(pipeline_root, paths["approved"].parent, output=output,
            receipt=paths["receipt"], closure=paths["closure"])
        if paths["closure"].is_file():
            validate_novel_news_export(pipeline_root=pipeline_root, request_id=request_id)
            stage, export_recovery_state = "completed", "completed"
        elif export_recovery_state == "legacy_unbound_orphan":
            stage = "blocked"
    return {
        "request_id": request_id, "mode": "novel_content", "stage": stage,
        "export_recovery_state": export_recovery_state,
        'generation': generation,
        "business_id": request.get("persona_id"), "speaker_id": request.get("speaker_persona"),
        "selected_content": request["selected_content"],
        "source_coverage": coverage if source else None,
        "beats": (_read(paths["plan"]).get("micro_information_beats") or []) if generation['ready_for_human_review'] else [],
        "approved_beats": (_read(paths["approved"]).get("micro_information_beats") or []) if paths["approved"].is_file() else [],
        "source_facts": {
            atom_id: atom["original_known_fact"]
            for atom_id, atom in (context["usable_atoms"] if context else {}).items()
        },
        "export": _read(paths["receipt"]) if paths["receipt"].is_file() else None,
        "created_by_user_id": request.get("created_by_user_id"),
        "created_by_phone": request.get("created_by_phone"),
    }


if __name__ == "__main__":
    import argparse
    import sys
    from news_export_recovery_v1 import NewsExportError
    from novel_news_generation_recovery_v1 import GenerationError
    from profile_compatibility_contract_v1_1 import CompatibilityError
    from operation_lock_v1 import OperationLockTimeout

    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("status", "generate", "review", "export"))
    parser.add_argument("--pipeline-root", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--actor")
    args = parser.parse_args()
    try:
        if args.operation == "status":
            result = novel_news_status(pipeline_root=args.pipeline_root, request_id=args.request_id)
        elif args.operation == "generate":
            incoming = json.loads(sys.stdin.read() or '{}')
            result = generate_novel_news_plan(pipeline_root=args.pipeline_root, request_id=args.request_id,
                generated_by=args.actor, **incoming)
        elif args.operation == "review":
            incoming = json.load(sys.stdin)
            result = review_novel_news_plan(
                pipeline_root=args.pipeline_root, request_id=args.request_id,
                decisions=incoming["decisions"], reviewer=str(args.actor or ""),
            )
        else:
            incoming = json.loads(sys.stdin.read() or '{}')
            result = export_novel_news(pipeline_root=args.pipeline_root, request_id=args.request_id,
                export_context=incoming.get("export_context"))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    except (NovelNewsError, NewsDeliveryError, NewsExportError, GenerationError, CompatibilityError,
            OperationLockTimeout, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "code": getattr(exc, "code", "NEWS_NOVEL_OPERATION_FAILED"), "message": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
