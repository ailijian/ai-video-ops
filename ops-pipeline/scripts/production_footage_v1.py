from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "production-footage-planning-v1.0"
ASSET_SCHEMA_VERSION = "production-asset-v1.0"
REQUIREMENT_SCHEMA_VERSION = "shot-requirement-plan-v1.0"
MATCH_SCHEMA_VERSION = "production-asset-match-v1.0"
COVERAGE_SCHEMA_VERSION = "storyboard-coverage-v1.0"

ALLOWED_SOURCE_TYPES = {
    "customer_existing",
    "customer_new_capture",
    "operator_capture",
    "licensed_source",
    "other_review_required",
}
ALLOWED_MEDIA_USE_STATUSES = {
    "authorized",
    "not_established",
    "blocked",
    "review_required",
}
ALLOWED_EVENT_RELATIONSHIPS = {
    "exact_event_footage",
    "actual_current_operation",
    "illustrative_same_process",
    "generic_context",
}
CAPTURE_PHRASE_ZH = {
    "same-frame ingredients": "把三只梭子蟹和年糕拍在同一画面里",
    "process sequence": "连续拍下食材、加工和完成状态",
    "packed finished dish": "拍打包好的梭子蟹加年糕",
    "generic crab dish without three-crab or rice-cake context": "只有普通螃蟹菜，看不出三只梭子蟹和年糕",
    "unauthorized customer photo or video": "使用未经允许的顾客照片或视频",
    "overhead ingredient shot": "从上方拍清三只梭子蟹",
    "hands presenting three crabs": "只露手，把三只梭子蟹摆清楚",
    "one generic crab": "只拍一只普通螃蟹",
    "unidentifiable seafood montage": "看不清食材和数量的海鲜拼接画面",
    "cutting or seasoning": "拍处理或调味的实际动作",
    "wok cooking": "拍锅中真实烹饪过程",
    "packing preparation": "拍出锅后的打包准备",
    "unrelated busy kitchen": "只有忙碌厨房但看不到这道菜",
    "Case Library footage": "使用案例库里的参考视频",
    "rice cake added to wok": "拍年糕加入锅中的动作",
    "finished crab and rice cake close-up": "近距离拍完成后的梭子蟹和年糕",
    "generic rice cake dish": "只拍普通年糕菜",
    "container packing": "拍菜品装盒过程",
    "completed dish before handoff": "拍交付前的完整成品",
    "customer-held historical media without authorization": "使用未经允许的顾客历史照片或视频",
    "clam inspection": "拍花蛤送来后的检查动作",
    "soaking preparation": "拍准备容器、加水等处理前动作",
    "staff explaining before work": "拍工作人员开工前说明情况，可只露手或背影",
    "only a finished clam dish": "只有花蛤成品，看不到检查和等待语境",
    "visual claim of fully sand-free result": "用画面暗示一定已经完全无沙",
    "container inspection": "拍容器里的花蛤及检查动作",
    "rinsing preparation": "拍冲洗或处理前准备",
    "generic seafood montage": "与本次花蛤处理无关的海鲜拼接画面",
    "preparation container": "拍泡水或处理准备使用的容器",
    "non-identifying explanation": "拍不露正脸的现场说明",
    "waiting marker without personal data": "拍不含个人信息的等待提示",
    "finished result presented as guaranteed sand removal": "把最终成品拍成保证完全吐净沙的证明",
    "board close-up": "近距离拍清白板上的排单或等待信息",
    "window and board together": "把服务窗口和白板拍在同一画面里",
    "staff checking or updating board": "拍工作人员查看或更新白板",
    "busy kitchen without board": "只有忙碌厨房，没有白板",
    "board exposing customer identity or order data": "白板暴露顾客身份或订单信息",
    "wide shot without customer faces": "从稍远位置拍窗口与白板，并避开顾客正脸",
    "staff-side angle": "从工作人员一侧拍窗口和白板",
    "unrelated kitchen work": "与白板机制无关的厨房操作",
    "sanitized close-up": "先去除个人信息，再近距离拍白板",
    "demonstration board using non-personal labels": "用不含姓名、电话和订单号的演示内容拍白板",
    "name phone order-id visible": "拍到姓名、电话或订单号",
    "claim of reduced anxiety or improved efficiency": "用画面声称焦虑下降或效率提升",
    "authorized speaker operation": "确认林东方同意本次出镜后，拍本人实际检查",
    "hands-only sequence": "只拍手、鱼腹、鱼鳃和连续检查动作",
    "POV inspection": "用第一视角拍检查过程，不露可识别人脸",
    "generic fish beauty shot": "只有鱼的展示镜头，没有检查动作",
    "identifiable speaker without authorization": "未确认授权就拍到可识别的林东方",
    "hands receiving fish": "只拍双手接鱼和放到操作台的过程",
    "fish on workbench": "拍鱼放在操作台等待检查",
    "unrelated cooked fish": "只有已经做好的鱼",
    "hands indicate area requiring work": "只拍手指出需要进一步处理的位置",
    "universal scientific test claim": "把个人操作拍成普适科学判断",
    "industry-standard claim": "把个人习惯拍成行业标准",
}
CASE_RESEARCH_ROOT_NAMES = {
    "cases",
    "sources",
    "visual",
    "storyboards",
    "shots",
    "fingerprints",
    "case_acquisition",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def production_asset_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": ASSET_SCHEMA_VERSION,
        "authority": (
            "Production media eligibility only; never Customer Truth, Case, "
            "Pattern, or Proof authority."
        ),
        "required_fields": [
            "asset_id",
            "business_id",
            "source_type",
            "source_ref",
            "file_ref",
            "checksum",
            "captured_at",
            "uploaded_at",
            "media_type",
            "duration",
            "orientation",
            "observable_content",
            "people_present",
            "identifiable_people",
            "speaker_present",
            "ownership_basis",
            "media_use_status",
            "privacy_status",
            "subject_release_status",
            "customer_story_scope_ref",
            "event_relationship",
            "production_eligibility",
            "eligible_profiles",
            "analysis_version",
        ],
        "enums": {
            "source_type": sorted(ALLOWED_SOURCE_TYPES),
            "media_use_status": sorted(ALLOWED_MEDIA_USE_STATUSES),
            "event_relationship": sorted(ALLOWED_EVENT_RELATIONSHIPS),
        },
        "boundaries": {
            "case_library_is_production_asset_source": False,
            "ownership_alone_establishes_eligibility": False,
            "speaker_persona_implies_media_authorization": False,
            "customer_story_authorization_equals_media_rights": False,
            "visual_match_upgrades_content_claim_authority": False,
        },
        "analysis_contract": {
            "reusable_local_components": [
                "extract_visual_evidence.py",
                "analyze_visual_timeline_v1.py",
                "privacy_projection_v1.py",
            ],
            "case_lifecycle_reused": False,
            "pattern_lifecycle_reused": False,
            "remote_model_requires_privacy_projection_and_safe_assertion": True,
            "analysis_may_describe_observable_content_only": True,
            "analysis_may_assert_customer_fact_truth": False,
            "observable_content_fields": [
                "observable_scenes",
                "visible_objects",
                "visible_text",
                "speaker_and_people_presence",
                "shot_boundaries_if_useful",
                "orientation",
                "duration",
                "privacy_indicators",
                "candidate_visual_roles",
            ],
        },
    }


def _pattern_and_cases(content: dict[str, Any]) -> tuple[str | None, list[str]]:
    pattern = content.get("pattern_ref") or {}
    case = content.get("case_reference") or {}
    return pattern.get("pattern_id"), [case["case_id"]] if case.get("case_id") else []


def _requirement(
    *,
    content: dict[str, Any],
    ordinal: int,
    role: str,
    semantic_role: str,
    goal: str,
    visible_state: str,
    observables: list[str],
    acceptable_forms: list[str],
    misleading_forms: list[str],
    speaker_presence: dict[str, Any],
    subject_presence: dict[str, Any],
    privacy_constraints: list[str],
    event_relationship: dict[str, Any],
    minimum_coverage: str,
    guidance: dict[str, Any],
    content_truth_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pattern_ref, case_refs = _pattern_and_cases(content)
    return {
        "requirement_id": f"{content['content_id']}-R{ordinal:02d}",
        "content_id": content["content_id"],
        "concept_ref": content["concept_ref"],
        "requirement_role": role,
        "semantic_role": semantic_role,
        "visual_information_goal": goal,
        "required_visible_state": visible_state,
        "required_observables": observables,
        "acceptable_asset_forms": acceptable_forms,
        "unacceptable_or_misleading_forms": misleading_forms,
        "speaker_presence": speaker_presence,
        "subject_presence": subject_presence,
        "privacy_constraints": privacy_constraints,
        "event_relationship_requirement": event_relationship,
        "minimum_semantic_coverage": minimum_coverage,
        "optional_capture_guidance": guidance,
        "content_truth_context": content_truth_context,
        "pattern_ref": pattern_ref,
        "case_structural_refs": case_refs,
        "case_media_allowed_for_production": False,
    }


def _common_presence() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "required": False,
            "preferred_speaker_id": None,
            "media_authorization_status": "not_applicable",
            "alternatives": ["hands_only", "pov", "non_identifying_operation"],
        },
        {
            "identifiable_customer_required": False,
            "default": "avoid_identifiable_customers",
        },
    )


def _real_content_requirements(content: dict[str, Any]) -> list[dict[str, Any]]:
    concept_ref = content["concept_ref"]
    speaker, subject = _common_presence()
    common_privacy = [
        "avoid_identifiable_customer_faces",
        "avoid_phone_order_or_identity_information",
    ]
    common_guidance = {
        "capture_style": "ordinary_phone_natural_operation",
        "duration_guidance": "hold_each_required_state_long_enough_to_read",
        "complex_camera_movement_required": False,
    }

    if concept_ref == "REV2-CONCEPT-010":
        specifications = [
            (
                "hero",
                "specific_service_scene",
                "让观众看懂三只梭子蟹加年糕这一具体服务场景",
                "三只梭子蟹与年糕在同一次可辨识的加工或完成场景中",
                ["three_swimming_crabs", "rice_cake", "same_service_scene"],
                ["same-frame ingredients", "process sequence", "packed finished dish"],
                ["generic crab dish without three-crab or rice-cake context", "unauthorized customer photo or video"],
            ),
            (
                "supporting",
                "ingredient_identity",
                "明确展示三只梭子蟹",
                "三只梭子蟹数量可辨识",
                ["three_swimming_crabs"],
                ["overhead ingredient shot", "hands presenting three crabs"],
                ["one generic crab", "unidentifiable seafood montage"],
            ),
            (
                "supporting",
                "process_illustration",
                "说明这是实际加工过程而非成品摆拍",
                "梭子蟹正在被门店真实处理或烹饪",
                ["crab", "actual_processing"],
                ["cutting or seasoning", "wok cooking", "packing preparation"],
                ["unrelated busy kitchen", "Case Library footage"],
            ),
            (
                "supporting",
                "ingredient_pairing",
                "展示年糕确实参与这道菜",
                "年糕与梭子蟹同场或加入加工过程",
                ["rice_cake", "crab"],
                ["rice cake added to wok", "finished crab and rice cake close-up"],
                ["generic rice cake dish"],
            ),
            (
                "supporting",
                "service_result",
                "展示完成与打包状态",
                "梭子蟹加年糕完成并进入打包或交付前状态",
                ["crab_rice_cake_result", "packing_or_completed_state"],
                ["container packing", "completed dish before handoff"],
                ["customer-held historical media without authorization"],
            ),
        ]
        result = []
        for index, spec in enumerate(specifications, 1):
            result.append(
                _requirement(
                    content=content,
                    ordinal=index,
                    role=spec[0],
                    semantic_role=spec[1],
                    goal=spec[2],
                    visible_state=spec[3],
                    observables=spec[4],
                    acceptable_forms=spec[5],
                    misleading_forms=spec[6],
                    speaker_presence=deepcopy(speaker),
                    subject_presence=deepcopy(subject),
                    privacy_constraints=common_privacy + ["small_sun_customer_media_is_not_authorized"],
                    event_relationship={
                        "preferred": "exact_event_footage",
                        "accepted": ["exact_event_footage", "illustrative_same_process"],
                        "illustrative_must_be_disclosed_as_original_event": False,
                        "illustrative_cannot_prove_observed_duration": True,
                    },
                    minimum_coverage="full" if spec[0] == "hero" else "partial_allowed",
                    guidance={
                        **common_guidance,
                        "event_note": "If captured later, record it as a same-process illustration, not the original order.",
                    },
                )
            )
        return result

    if concept_ref == "REV2-CONCEPT-001":
        specifications = [
            (
                "hero",
                "service_boundary_explanation",
                "让观众看到花蛤到窗口后的检查，以及进入临时处理准备、等待确认的现场状态",
                "花蛤在窗口被检查，随后出现处理准备、泡水准备、等待或确认语境",
                ["clams_at_service_window", "inspection_or_soaking_preparation", "waiting_or_confirmation_context"],
                ["clam inspection", "soaking preparation", "staff explaining before work"],
                ["only a finished clam dish", "visual claim of fully sand-free result"],
            ),
            (
                "supporting",
                "ingredient_state",
                "交代花蛤到达窗口后正在接受现场检查",
                "花蛤在窗口或操作台等待检查，检查动作可见",
                ["clams_at_service_window", "inspection"],
                ["container inspection", "rinsing preparation"],
                ["generic seafood montage"],
            ),
            (
                "supporting",
                "waiting_boundary",
                "表达需要等待和先确认，而不是承诺处理结果",
                "准备泡水、计时或工作人员先说明的等待语境",
                ["waiting_or_confirmation_context"],
                ["preparation container", "non-identifying explanation", "waiting marker without personal data"],
                ["finished result presented as guaranteed sand removal"],
            ),
        ]
        return [
            _requirement(
                content=content,
                ordinal=index,
                role=spec[0],
                semantic_role=spec[1],
                goal=spec[2],
                visible_state=spec[3],
                observables=spec[4],
                acceptable_forms=spec[5],
                misleading_forms=spec[6],
                speaker_presence=deepcopy(speaker),
                subject_presence=deepcopy(subject),
                privacy_constraints=common_privacy,
                event_relationship={
                    "preferred": "actual_current_operation",
                    "accepted": ["actual_current_operation", "illustrative_same_process"],
                    "result_cannot_imply_guaranteed_sand_removal": True,
                },
                minimum_coverage="full" if spec[0] == "hero" else "partial_allowed",
                guidance=common_guidance,
                content_truth_context=(
                    {
                        "approved_customer_truth": "该次场景中的花蛤未提前吐沙",
                        "visual_asset_can_independently_prove_prior_sand_purge_state": False,
                        "claim_authority": "approved_content_truth_not_visual_inference",
                    }
                    if index == 1
                    else None
                ),
            )
            for index, spec in enumerate(specifications, 1)
        ]

    if concept_ref == "REV2-CONCEPT-004":
        specifications = [
            (
                "hero",
                "queue_mechanism",
                "直接解释窗口如何展示排单顺序或预计等待",
                "窗口旁白板中可辨认排单顺序或预计等待信息",
                ["queue_board", "queue_order_or_estimated_wait"],
                ["board close-up", "window and board together", "staff checking or updating board"],
                ["busy kitchen without board", "board exposing customer identity or order data"],
            ),
            (
                "supporting",
                "service_location",
                "交代白板位于服务窗口旁并供顾客查看",
                "窗口与白板空间关系清楚",
                ["service_window", "queue_board"],
                ["wide shot without customer faces", "staff-side angle"],
                ["unrelated kitchen work"],
            ),
            (
                "supporting",
                "current_information_state",
                "展示白板承载当前排单或预计等待信息",
                "白板上的有效信息可读但没有个人敏感信息",
                ["queue_order_or_estimated_wait", "privacy_safe_board_text"],
                ["sanitized close-up", "demonstration board using non-personal labels"],
                ["name phone order-id visible", "claim of reduced anxiety or improved efficiency"],
            ),
        ]
        return [
            _requirement(
                content=content,
                ordinal=index,
                role=spec[0],
                semantic_role=spec[1],
                goal=spec[2],
                visible_state=spec[3],
                observables=spec[4],
                acceptable_forms=spec[5],
                misleading_forms=spec[6],
                speaker_presence=deepcopy(speaker),
                subject_presence=deepcopy(subject),
                privacy_constraints=common_privacy
                + ["board_must_not_show_name_phone_order_id_or_customer_identity"],
                event_relationship=(
                    {
                        "preferred": "actual_current_operation",
                        "accepted": ["actual_current_operation"],
                        "generic_busy_context_is_not_substitute": True,
                        "staged_demo_can_satisfy_hero": False,
                    }
                    if spec[0] == "hero"
                    else {
                        "preferred": "actual_current_operation",
                        "accepted": [
                            "actual_current_operation",
                            "illustrative_same_process",
                        ],
                        "staged_demo_is_supporting_illustration_only": True,
                    }
                ),
                minimum_coverage="full" if spec[0] == "hero" else "partial_allowed",
                guidance=common_guidance,
            )
            for index, spec in enumerate(specifications, 1)
        ]

    if concept_ref == "REV2-CONCEPT-006":
        speaker_presence = {
            "required": False,
            "preferred_speaker_id": "lin_dongfang_frontline_chef",
            "media_authorization_status": "review_required",
            "persona_approval_implies_media_authorization": False,
            "alternatives": ["hands_only", "pov", "non_identifying_operation"],
        }
        specifications = [
            (
                "hero",
                "speaker_specific_inspection_practice",
                "完整表达接鱼后按鱼腹并查看鱼鳃的检查动作",
                "同一次接鱼检查中依次出现按鱼腹与查看鱼鳃",
                ["fish", "press_fish_belly", "inspect_gills", "same_inspection_sequence"],
                ["authorized speaker operation", "hands-only sequence", "POV inspection"],
                ["generic fish beauty shot", "identifiable speaker without authorization"],
            ),
            (
                "supporting",
                "fish_receipt_state",
                "交代这是接到食材后的现场检查",
                "鱼在接收或操作台上等待检查",
                ["fish", "receiving_or_workbench_context"],
                ["hands receiving fish", "fish on workbench"],
                ["unrelated cooked fish"],
            ),
            (
                "supporting",
                "inspection_changes_advice",
                "表达检查后会按现场状态调整处理建议",
                "检查动作完成后出现说明或不同处理准备",
                ["inspection", "adjusted_handling_context"],
                ["hands indicate area requiring work", "non-identifying explanation"],
                ["universal scientific test claim", "industry-standard claim"],
            ),
        ]
        return [
            _requirement(
                content=content,
                ordinal=index,
                role=spec[0],
                semantic_role=spec[1],
                goal=spec[2],
                visible_state=spec[3],
                observables=spec[4],
                acceptable_forms=spec[5],
                misleading_forms=spec[6],
                speaker_presence=deepcopy(speaker_presence),
                subject_presence=deepcopy(subject),
                privacy_constraints=common_privacy
                + ["confirm_speaker_media_authorization_before_showing_identifiable_face"],
                event_relationship={
                    "preferred": "actual_current_operation",
                    "accepted": ["actual_current_operation", "illustrative_same_process"],
                    "visual_does_not_make_practice_universal": True,
                },
                minimum_coverage="full" if spec[0] == "hero" else "partial_allowed",
                guidance={
                    **common_guidance,
                    "authorization_paths": [
                        "confirm_lin_dongfang_identifiable_media_authorization",
                        "capture_hands_fish_and_actions_without_identifiable_face",
                    ],
                },
            )
            for index, spec in enumerate(specifications, 1)
        ]

    raise ValueError(f"No approved V1 footage mapping for concept: {concept_ref}")


def build_shot_requirement_plan_v1(
    approved_batch: dict[str, Any],
    *,
    batch_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if approved_batch.get("status") != "approved":
        raise ValueError("Shot requirements require an approved generation batch")
    contents = approved_batch.get("contents") or []
    if not contents:
        raise ValueError("Approved generation batch contains no content")
    requirements: list[dict[str, Any]] = []
    content_records: list[dict[str, Any]] = []
    for content in contents:
        content_requirements = _real_content_requirements(content)
        requirements.extend(content_requirements)
        content_records.append(
            {
                "content_id": content["content_id"],
                "concept_ref": content["concept_ref"],
                "title": content["title"],
                "approved_script_sha256": canonical_sha256(
                    {"title": content["title"], "narration": content["narration"]}
                ),
                "hero_requirement_count": sum(
                    item["requirement_role"] == "hero" for item in content_requirements
                ),
                "supporting_requirement_count": sum(
                    item["requirement_role"] == "supporting"
                    for item in content_requirements
                ),
            }
        )
    return {
        "schema_version": REQUIREMENT_SCHEMA_VERSION,
        "created_at": created_at or utc_now(),
        "request_id": approved_batch["request_id"],
        "business_id": "shufang_zhiyuan_community_canteen",
        "production_profile": approved_batch.get("profile", "mix"),
        "status": "review_required",
        "content_count": len(contents),
        "fixed_shot_count_required": False,
        "contents": content_records,
        "requirements": requirements,
        "lineage": {
            "approved_batch_path": str(batch_path.resolve()) if batch_path else None,
            "approved_batch_file_sha256": sha256_file(batch_path) if batch_path else None,
        },
        "authority": {
            "requirements_are_semantic_visual_goals": True,
            "requirements_are_specific_camera_shots": False,
            "case_refs_are_structural_only": True,
            "case_media_allowed_for_production": False,
            "script_authority_modified": False,
        },
    }


def _flatten_observables(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            if item is True:
                result.add(str(key).strip().lower())
            result |= _flatten_observables(item)
        return result
    if isinstance(value, Iterable):
        result: set[str] = set()
        for item in value:
            result |= _flatten_observables(item)
        return result
    return {str(value).strip().lower()}


def evaluate_production_asset_eligibility(
    asset: dict[str, Any],
    *,
    target_profile: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    review_reasons: list[str] = []
    source_type = asset.get("source_type")
    if source_type not in ALLOWED_SOURCE_TYPES:
        reasons.append("source_type_not_allowed_case_library_is_never_production_source")
    elif source_type == "other_review_required":
        review_reasons.append("source_type_requires_review")
    media_status = asset.get("media_use_status")
    if media_status == "blocked":
        reasons.append("media_use_blocked")
    elif media_status != "authorized":
        review_reasons.append("media_use_not_authorized")
    privacy_status = asset.get("privacy_status")
    if privacy_status == "blocked":
        reasons.append("privacy_blocked")
    elif privacy_status != "passed":
        review_reasons.append("privacy_not_passed")
    identifiable = bool(asset.get("identifiable_people"))
    release = asset.get("subject_release_status")
    if identifiable and release == "blocked":
        reasons.append("identifiable_subject_release_blocked")
    elif identifiable and release != "authorized":
        review_reasons.append("identifiable_subject_release_not_authorized")
    story_scope = asset.get("customer_story_scope_ref")
    if story_scope:
        story_media = asset.get("customer_story_media_authorization") or {}
        media_type = asset.get("media_type")
        if media_type in {"image", "video"} and not story_media.get(
            f"{media_type}_authorized", False
        ):
            reasons.append("customer_story_media_not_authorized")
    profiles = set(asset.get("eligible_profiles") or [])
    if target_profile not in profiles:
        review_reasons.append("target_profile_not_eligible")
    if not asset.get("file_ref") or not asset.get("checksum"):
        review_reasons.append("file_identity_incomplete")
    if asset.get("event_relationship") not in ALLOWED_EVENT_RELATIONSHIPS:
        review_reasons.append("event_relationship_unresolved")

    if reasons:
        status = "blocked"
    elif review_reasons:
        status = "review_required"
    else:
        status = "eligible"
    return {
        "status": status,
        "eligible": status == "eligible",
        "blocking_reasons": reasons,
        "review_reasons": review_reasons,
        "ownership_alone_used": False,
        "claim_or_proof_authority_granted": False,
    }


def audit_production_asset_inventory_v1(
    *,
    business_id: str,
    workspace_root: Path,
    target_profile: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    canonical_roots = [
        workspace_root / "data" / "production_assets" / business_id,
        workspace_root / "data" / "customer_assets" / business_id,
    ]
    assets: list[dict[str, Any]] = []
    unregistered_media: list[str] = []
    for root in canonical_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".json":
                try:
                    record = load_json(path)
                except (ValueError, json.JSONDecodeError):
                    continue
                if record.get("schema_version") != ASSET_SCHEMA_VERSION:
                    continue
                record = deepcopy(record)
                record["inventory_source_ref"] = str(path.resolve())
                record["production_eligibility"] = evaluate_production_asset_eligibility(
                    record, target_profile=target_profile
                )
                assets.append(record)
            elif path.suffix.lower() in {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png"}:
                unregistered_media.append(str(path.resolve()))
    eligible = [item for item in assets if item["production_eligibility"]["eligible"]]
    return {
        "schema_version": "production-asset-inventory-v1.0",
        "asset_contract": production_asset_contract_v1(),
        "created_at": created_at or utc_now(),
        "business_id": business_id,
        "target_profile": target_profile,
        "assets": assets,
        "asset_count": len(assets),
        "eligible_asset_count": len(eligible),
        "unregistered_media_files": unregistered_media,
        "scanned_roots": [
            {"path": str(path.resolve()), "exists": path.exists()}
            for path in canonical_roots
        ],
        "excluded_case_research_roots": [
            str((workspace_root / "data" / name).resolve())
            for name in sorted(CASE_RESEARCH_ROOT_NAMES)
        ],
        "audit_result": "no_registered_production_assets" if not assets else "assets_found",
        "authority": {
            "case_media_ingested": False,
            "case_library_is_production_asset_source": False,
            "inventory_grants_customer_truth": False,
            "inventory_grants_proof": False,
        },
    }


def _semantic_fit(requirement: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    required = set(requirement.get("required_observables") or [])
    observed = _flatten_observables(asset.get("observable_content"))
    matched = required & observed
    ratio = len(matched) / len(required) if required else 0.0
    if required and matched == required:
        level = "full"
    elif matched:
        level = "partial"
    else:
        level = "none"
    return {
        "level": level,
        "coverage_ratio": round(ratio, 4),
        "matched_observables": sorted(matched),
        "missing_observables": sorted(required - observed),
    }


def _event_fit(requirement: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    relationship = asset.get("event_relationship")
    rule = requirement.get("event_relationship_requirement") or {}
    accepted = set(rule.get("accepted") or [])
    if relationship not in accepted:
        return {"level": "none", "reason": "event_relationship_not_accepted"}
    preferred = rule.get("preferred")
    if relationship == preferred:
        return {"level": "full", "reason": "preferred_event_relationship"}
    return {
        "level": "partial",
        "reason": "illustrative_or_nonpreferred_relationship_only",
        "cannot_prove_original_event": relationship == "illustrative_same_process",
    }


def match_production_assets_v1(
    requirement_plan: dict[str, Any],
    inventory: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    target_profile = requirement_plan["production_profile"]
    matches: list[dict[str, Any]] = []
    for requirement in requirement_plan["requirements"]:
        candidates: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for asset in inventory.get("assets") or []:
            eligibility = evaluate_production_asset_eligibility(
                asset, target_profile=target_profile
            )
            semantic = _semantic_fit(requirement, asset)
            event = _event_fit(requirement, asset)
            candidate = {
                "asset_id": asset.get("asset_id"),
                "semantic_fit": semantic,
                "rights_fit": {
                    "status": "passed" if eligibility["eligible"] else eligibility["status"],
                    "reasons": eligibility["blocking_reasons"] + eligibility["review_reasons"],
                },
                "privacy_fit": {
                    "status": "passed"
                    if asset.get("privacy_status") == "passed"
                    else asset.get("privacy_status", "review_required")
                },
                "event_relationship_fit": event,
                "visual_truth_boundary": {
                    "claim_authority_upgraded": False,
                    "proof_authority_upgraded": False,
                    "illustrative_is_exact_event": False,
                },
            }
            if (
                not eligibility["eligible"]
                and semantic["level"] != "none"
                and event["level"] != "none"
            ):
                blocked.append(candidate)
            elif semantic["level"] != "none" and event["level"] != "none":
                candidates.append(candidate)
        full = [
            item
            for item in candidates
            if item["semantic_fit"]["level"] == "full"
            and item["event_relationship_fit"]["level"] == "full"
        ]
        partial = [item for item in candidates if item not in full]
        if full:
            decision = "matched"
            selected = full
        elif partial:
            decision = "partial"
            selected = partial
        elif blocked:
            decision = "blocked"
            selected = []
        else:
            decision = "gap"
            selected = []
        matches.append(
            {
                "requirement_id": requirement["requirement_id"],
                "content_id": requirement["content_id"],
                "requirement_role": requirement["requirement_role"],
                "matched_asset_ids": [item["asset_id"] for item in selected],
                "match_role": requirement["semantic_role"],
                "semantic_fit": [item["semantic_fit"] for item in selected],
                "rights_fit": [item["rights_fit"] for item in selected],
                "privacy_fit": [item["privacy_fit"] for item in selected],
                "event_relationship_fit": [
                    item["event_relationship_fit"] for item in selected
                ],
                "match_decision": decision,
                "candidate_details": selected,
                "blocked_candidate_details": blocked,
            }
        )
    return {
        "schema_version": MATCH_SCHEMA_VERSION,
        "created_at": created_at or utc_now(),
        "request_id": requirement_plan["request_id"],
        "production_profile": target_profile,
        "matches": matches,
        "summary": {
            key: sum(item["match_decision"] == key for item in matches)
            for key in ("matched", "partial", "gap", "blocked")
        },
        "authority": {
            "visual_match_upgrades_claim_authority": False,
            "visual_match_upgrades_proof_authority": False,
            "embedding_only_matching_used": False,
        },
    }


def build_storyboard_coverage_v1(
    requirement_plan: dict[str, Any],
    asset_matches: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    match_by_id = {
        item["requirement_id"]: item for item in asset_matches.get("matches") or []
    }
    requirement_by_id = {
        item["requirement_id"]: item for item in requirement_plan["requirements"]
    }
    content_coverage: list[dict[str, Any]] = []
    all_gaps: list[dict[str, Any]] = []
    for content in requirement_plan["contents"]:
        requirements = [
            item
            for item in requirement_plan["requirements"]
            if item["content_id"] == content["content_id"]
        ]
        hero_matches = [
            match_by_id[item["requirement_id"]]
            for item in requirements
            if item["requirement_role"] == "hero"
        ]
        supporting_matches = [
            match_by_id[item["requirement_id"]]
            for item in requirements
            if item["requirement_role"] == "supporting"
        ]
        gaps: list[dict[str, Any]] = []
        for requirement in requirements:
            match = match_by_id[requirement["requirement_id"]]
            if match["match_decision"] == "matched":
                continue
            gap = {
                "requirement_id": requirement["requirement_id"],
                "semantic_goal": requirement["visual_information_goal"],
                "why_needed": requirement["required_visible_state"],
                "missing_state": requirement["required_visible_state"],
                "capture_priority": (
                    "critical" if requirement["requirement_role"] == "hero" else "high"
                ),
                "privacy_notes": requirement["privacy_constraints"],
                "rights_notes": [
                    "use_only_registered_production_assets",
                    "case_library_media_is_not_allowed",
                ],
                "acceptable_alternatives": requirement["acceptable_asset_forms"],
                "current_match_decision": match["match_decision"],
            }
            gaps.append(gap)
            all_gaps.append(gap)
        hero_decisions = {item["match_decision"] for item in hero_matches}
        all_decisions = {
            match_by_id[item["requirement_id"]]["match_decision"]
            for item in requirements
        }
        if all_decisions == {"matched"}:
            overall = "covered"
        elif "blocked" in hero_decisions:
            overall = "blocked"
        elif "matched" in all_decisions or "partial" in all_decisions:
            overall = "partially_covered"
        else:
            overall = "capture_required"
        content_coverage.append(
            {
                "content_id": content["content_id"],
                "concept_ref": content["concept_ref"],
                "title": content["title"],
                "hero_coverage": [
                    {
                        "requirement_id": item["requirement_id"],
                        "decision": item["match_decision"],
                        "matched_asset_ids": item["matched_asset_ids"],
                    }
                    for item in hero_matches
                ],
                "supporting_coverage": [
                    {
                        "requirement_id": item["requirement_id"],
                        "decision": item["match_decision"],
                        "matched_asset_ids": item["matched_asset_ids"],
                    }
                    for item in supporting_matches
                ],
                "blocked_requirements": [
                    item["requirement_id"]
                    for item in hero_matches + supporting_matches
                    if item["match_decision"] == "blocked"
                ],
                "capture_gaps": gaps,
                "overall_status": overall,
            }
        )
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "created_at": created_at or utc_now(),
        "request_id": requirement_plan["request_id"],
        "content_coverage": content_coverage,
        "capture_gaps": all_gaps,
        "summary": {
            "content_count": len(content_coverage),
            "covered": sum(item["overall_status"] == "covered" for item in content_coverage),
            "partially_covered": sum(
                item["overall_status"] == "partially_covered" for item in content_coverage
            ),
            "capture_required": sum(
                item["overall_status"] == "capture_required" for item in content_coverage
            ),
            "blocked": sum(item["overall_status"] == "blocked" for item in content_coverage),
        },
        "authority": {
            "script_authority_modified": False,
            "visual_truth_or_proof_authority_created": False,
            "content_ledger_write_performed": False,
        },
    }


def build_customer_capture_missions_v1(
    requirement_plan: dict[str, Any],
    *,
    status: str = "review_required",
    created_at: str | None = None,
) -> dict[str, Any]:
    if status not in {"review_required", "ready_to_send"}:
        raise ValueError(f"Unsupported capture mission status: {status}")
    requirements_by_content: dict[str, list[dict[str, Any]]] = {}
    for requirement in requirement_plan["requirements"]:
        requirements_by_content.setdefault(requirement["content_id"], []).append(
            requirement
        )
    contents = {item["concept_ref"]: item for item in requirement_plan["contents"]}
    specs = {
        "REV2-CONCEPT-010": {
            "mission_id": "MISSION-001",
            "capture_goal": "用一段连续素材说明三只梭子蟹加年糕的食材、加工与完成状态",
            "must_capture": [
                "三只梭子蟹的数量清楚可见",
                "年糕与梭子蟹在同一加工流程中",
                "真实加工动作",
                "完成或打包状态",
            ],
            "nice_to_have": ["一段完整流程", "必要时补一段成品特写"],
            "avoid": [
                "小孙或其他顾客出镜",
                "使用小孙历史照片或视频",
                "把现在补拍说成原来那一单现场",
                "用补拍素材证明当时约15分钟",
            ],
            "alternative_capture": [
                "现在按同类真实流程补拍，明确记录为同类流程说明素材"
            ],
            "event_relationship_instruction": {
                "preferred": "exact_event_footage_if_authorized_and_available",
                "current_new_capture_label": "illustrative_same_process",
                "customer_wording": "现在补拍属于同类流程说明，不能当成原来那一单的现场画面。",
                "cannot_prove": ["original_event", "observed_15_minute_duration"],
            },
            "subject_authorization_requirement": {
                "identifiable_customer_required": False,
                "small_sun_media_allowed": False,
            },
        },
        "REV2-CONCEPT-001": {
            "mission_id": "MISSION-002",
            "capture_goal": "拍清花蛤到窗口后的检查、处理准备以及等待确认语境",
            "must_capture": [
                "花蛤到窗口后的检查",
                "处理或泡水准备",
                "等待或先确认的现场语境",
            ],
            "nice_to_have": ["同一段素材连续包含检查、准备和确认过程"],
            "avoid": [
                "要求画面证明花蛤此前没有吐沙",
                "用最终成品证明完全无沙",
                "把处理准备拍成保证结果",
            ],
            "alternative_capture": [
                "只拍花蛤、手部检查、容器准备和不露脸的说明动作"
            ],
            "event_relationship_instruction": {
                "preferred": "actual_current_operation",
                "allowed_alternative": "illustrative_same_process",
                "customer_wording": "画面只说明现场检查与处理准备，不能单独证明此前是否吐过沙。",
                "visual_cannot_prove": ["prior_sand_purge_state", "guaranteed_sand_free_result"],
            },
            "subject_authorization_requirement": {
                "identifiable_customer_required": False,
                "identifiable_staff_required": False,
            },
        },
        "REV2-CONCEPT-004": {
            "mission_id": "MISSION-003",
            "capture_goal": "用真实窗口与当前白板说明排单和预计等待机制",
            "must_capture": [
                "真实窗口与白板的空间关系",
                "真实白板上的排单结构或预计等待结构",
                "姓名、电话、订单号和顾客身份均不可见",
            ],
            "nice_to_have": ["一段窗口与白板同框", "一段排单或预计等待特写"],
            "avoid": [
                "用忙碌厨房替代白板机制",
                "拍到顾客身份或订单信息",
                "把完全虚构的演示白板当成当前真实使用状态",
            ],
            "alternative_capture": [
                "如只能拍演示白板，必须标为同类说明素材，只能补充说明，真实白板 Hero 仍保持缺口"
            ],
            "event_relationship_instruction": {
                "hero_required": "actual_current_operation",
                "staged_demo_label": "illustrative_same_process",
                "staged_demo_can_fully_cover_hero": False,
                "customer_wording": "主画面必须是真实正在使用的白板；演示白板只能作为补充。",
            },
            "subject_authorization_requirement": {
                "identifiable_customer_required": False,
                "board_privacy_review_required": True,
            },
        },
        "REV2-CONCEPT-006": {
            "mission_id": "MISSION-004",
            "capture_goal": "用一段连续动作说明接鱼后按鱼腹、看鱼鳃和继续处理准备",
            "must_capture": [
                "接鱼或把鱼放到操作台",
                "按鱼腹",
                "查看鱼鳃",
                "检查后的进一步处理准备",
            ],
            "nice_to_have": ["一段不剪断的完整检查动作"],
            "avoid": [
                "包装成行业教程或科学判断标准",
                "未确认授权就拍到林东方可识别正脸",
                "只有鱼的展示镜头而没有检查动作",
            ],
            "alternative_capture": [
                "未确认或不愿清晰出镜时，只拍手部、鱼、第一视角或背影"
            ],
            "event_relationship_instruction": {
                "preferred": "actual_current_operation",
                "recreated_capture_label": "illustrative_same_process",
                "customer_wording": "优先拍真实接鱼检查；专门复现时标为同类动作说明。",
                "visual_does_not_create_universal_rule": True,
            },
            "subject_authorization_requirement": {
                "subject_ref": "lin_dongfang_frontline_chef",
                "identifiable_face_status": "review_required",
                "authorized_path": "save_scope_bound_subject_media_confirmation",
                "non_identifying_path": ["hands_only", "pov", "back_view", "non_identifying_operation"],
            },
        },
    }
    common_guidance = {
        "orientation": "portrait_9_16_preferred",
        "device": "ordinary_phone_is_sufficient",
        "continuous_action_duration_guidance_seconds": "8_to_12",
        "head_and_tail_margin": "leave_a_little_before_and_after_action",
        "camera_movement": "not_required",
        "filter": "not_required",
        "digital_zoom": "avoid",
        "onsite_narration": "not_required",
        "source_clip_handling": "do_not_precut_original_material",
        "guidance_is_configurable_not_frozen_contract": True,
    }
    missions: list[dict[str, Any]] = []
    for concept_ref, spec in specs.items():
        content = contents[concept_ref]
        covered = requirements_by_content[content["content_id"]]
        mission = {
            **spec,
            "content_ref": {
                "content_id": content["content_id"],
                "concept_ref": concept_ref,
                "title": content["title"],
            },
            "covers_requirement_ids": [item["requirement_id"] for item in covered],
            "batch_specific_capture_guidance": deepcopy(common_guidance),
        }
        missions.append(mission)
    return {
        "schema_version": "customer-capture-missions-v1.0",
        "created_at": created_at or utc_now(),
        "request_id": requirement_plan["request_id"],
        "status": status,
        "mission_count": len(missions),
        "internal_requirement_count": len(requirement_plan["requirements"]),
        "mapping_cardinality": "one_mission_may_cover_many_requirements",
        "missions": missions,
        "authority": {
            "derived_from_shot_requirements": True,
            "new_customer_truth_or_proof_authority": False,
            "shot_requirements_deleted_or_replaced": False,
            "one_requirement_requires_one_file": False,
            "guidance_is_configurable": True,
        },
    }


def subject_media_use_confirmation_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": "subject-media-use-confirmation-v1.0",
        "required_fields": [
            "confirmation_id",
            "subject_ref",
            "subject_display_name",
            "business_id",
            "scope_refs",
            "identifiable_face_allowed",
            "voice_allowed",
            "allowed_media_types",
            "use_scope",
            "confirmed_by",
            "confirmed_at",
            "status",
        ],
        "allowed_statuses": ["authorized", "declined", "review_required"],
        "scope_rule": "authorization_is_never_inferred_beyond_explicit_scope_refs",
        "authority": "subject_media_use_only_not_speaker_persona_or_content_truth",
    }


def build_subject_media_use_confirmation_v1(
    *,
    status: str = "review_required",
    identifiable_face_allowed: bool | None = None,
    voice_allowed: bool | None = None,
    allowed_media_types: list[str] | None = None,
    confirmed_by: str | None = None,
    confirmed_at: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if status not in {"authorized", "declined", "review_required"}:
        raise ValueError(f"Unsupported subject confirmation status: {status}")
    if status == "authorized":
        if identifiable_face_allowed is not True or not confirmed_by or not confirmed_at:
            raise ValueError("Authorized identifiable media requires explicit confirmation")
    if status == "declined":
        identifiable_face_allowed = False
        voice_allowed = False
        allowed_media_types = []
    return {
        "schema_version": "subject-media-use-confirmation-v1.0",
        "contract": subject_media_use_confirmation_contract_v1(),
        "confirmation_id": "SMUC-real_shufang_mix_003-lin_dongfang-001",
        "subject_ref": "lin_dongfang_frontline_chef",
        "subject_display_name": "林东方",
        "business_id": "shufang_zhiyuan_community_canteen",
        "scope_refs": ["real_shufang_mix_003"],
        "identifiable_face_allowed": identifiable_face_allowed,
        "voice_allowed": voice_allowed,
        "allowed_media_types": allowed_media_types or [],
        "use_scope": "current_batch_only",
        "confirmed_by": confirmed_by,
        "confirmed_at": confirmed_at,
        "status": status,
        "created_at": created_at or utc_now(),
        "future_use_requires_recheck": True,
        "persona_approval_used_as_media_authorization": False,
        "capture_execution_paths": {
            "identifiable": {
                "allowed_only_when_status_authorized": True,
                "confirmation_must_be_saved": True,
            },
            "non_identifying": {
                "allowed_while_review_required_or_declined": True,
                "forms": [
                    "hands_only",
                    "pov",
                    "back_view",
                    "non_identifying_operation",
                ],
            },
        },
    }


def subject_capture_paths(
    confirmation: dict[str, Any],
) -> dict[str, Any]:
    identifiable_allowed = bool(
        confirmation.get("status") == "authorized"
        and confirmation.get("identifiable_face_allowed") is True
        and "video" in set(confirmation.get("allowed_media_types") or [])
    )
    return {
        "identifiable_subject_capture_allowed": identifiable_allowed,
        "non_identifying_capture_allowed": True,
        "non_identifying_options": [
            "hands_only",
            "pov",
            "back_view",
            "non_identifying_operation",
        ],
        "declining_identifiable_use_blocks_capture_mission": False,
    }


def build_production_footage_planning_human_approval_v1(
    *,
    reviewer: str,
    approved_at: str,
    requirement_plan_path: Path,
    missions_path: Path,
    inventory_path: Path,
    coverage_path: Path,
    subject_confirmation_path: Path,
    capture_pack_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "production-footage-planning-human-approval-v1.0",
        "reviewer": reviewer,
        "approved_at": approved_at,
        "decision": "approved_after_minor_normalization",
        "request_id": "real_shufang_mix_003",
        "approved_components": {
            "shot_requirement_architecture": True,
            "production_asset_architecture": True,
            "asset_eligibility": True,
            "visual_truth_boundary": True,
            "c002_observable_state_correction": True,
            "c003_actual_vs_demo_correction": True,
            "capture_mission_simplification": True,
            "speaker_media_authorization_required": True,
        },
        "source_artifacts": {
            "shot_requirement_plan": {
                "path": str(requirement_plan_path.resolve()),
                "file_sha256": sha256_file(requirement_plan_path),
            },
            "customer_capture_missions": {
                "path": str(missions_path.resolve()),
                "file_sha256": sha256_file(missions_path),
            },
            "production_asset_inventory": {
                "path": str(inventory_path.resolve()),
                "file_sha256": sha256_file(inventory_path),
            },
            "storyboard_coverage": {
                "path": str(coverage_path.resolve()),
                "file_sha256": sha256_file(coverage_path),
            },
            "subject_media_use_confirmation": {
                "path": str(subject_confirmation_path.resolve()),
                "file_sha256": sha256_file(subject_confirmation_path),
                "authorization_status": "review_required",
            },
            "customer_capture_pack": {
                "path": str(capture_pack_path.resolve()),
                "file_sha256": sha256_file(capture_pack_path),
                "status": "ready_to_send",
                "sent": False,
            },
        },
        "capture_pack_status": "ready_to_send",
        "capture_pack_sent": False,
        "asset_intake_started": False,
        "editing_or_rendering_started": False,
        "authority": {
            "subject_media_authorization_fabricated": False,
            "content_or_script_authority_changed": False,
            "proof_authority_created": False,
        },
    }


def render_customer_capture_pack_v1(
    requirement_plan: dict[str, Any],
    coverage: dict[str, Any],
    missions: dict[str, Any] | None = None,
    *,
    status: str = "review_required",
) -> str:
    missions = missions or build_customer_capture_missions_v1(
        requirement_plan, status=status
    )
    lines = [
        "# 林东方｜本轮视频补拍清单",
        "",
        f"状态：{'可以发送，尚未发送' if status == 'ready_to_send' else '等待内部确认'}",
        "",
        "这次一共拍 4 组素材。每组尽量用一段连续素材覆盖完整动作，不需要为每个小画面单独拍一个文件。",
        "",
        "## 本批统一拍摄建议",
        "",
        "- 优先竖屏 9:16，普通手机即可。",
        "- 每个完整动作建议连续拍约 8–12 秒，动作前后稍微多留一点。",
        "- 不需要运镜、滤镜、数字变焦或现场口播。",
        "- 请保留原始完整素材，不要提前剪碎。",
        "- 不拍顾客正脸、姓名、电话、订单号或其他身份信息。",
        "- 拍真实白板时，可以先擦除、遮挡或避开个人信息，但请保留真实排单结构、等待时间结构和窗口关系。",
        "- 如果林东方本人清晰出镜，请先确认本人同意本次视频使用；未确认时只拍手部、食材和操作动作。",
        "- 不要使用之前顾客提供的照片或视频。本轮需要的是门店自有或新补拍素材。",
        "",
    ]
    for index, mission in enumerate(missions["missions"], 1):
        lines.extend(
            [
                f"## {index}. {mission['content_ref']['title']}",
                "",
                f"**拍什么：** {mission['capture_goal']}。",
                "",
                "**一定要拍到：**",
                "",
                *[f"- {item}" for item in mission["must_capture"]],
                "",
                "**不要拍什么：**",
                "",
                *[f"- {item}" for item in mission["avoid"]],
                "",
                "**替代方式：**",
                "",
                *[f"- {item}" for item in mission["alternative_capture"]],
                "",
                f"> {mission['event_relationship_instruction']['customer_wording']}",
                "",
            ]
        )
        if mission["nice_to_have"]:
            lines.extend(
                [
                    "有余力可以再拍：" + "；".join(mission["nice_to_have"]) + "。",
                    "",
                ]
            )
        if mission["mission_id"] == "MISSION-004":
            lines.extend(
                [
                    "人物出镜有两种执行方式：",
                    "",
                    "- A：林东方确认同意本批视频清晰出镜后拍摄，并保存本批授权确认。",
                    "- B：没有确认或不愿清晰出镜时，只拍手部、第一视角、背影或其他不可识别的操作。",
                    "",
                ]
            )
    lines.extend(
        [
            "## 提交素材时请补充",
            "",
            "请说明素材是谁拍的、何时拍的、是否允许用于本次视频；如画面中有人脸，也请说明相关人员是否同意使用。素材提交后仍需做隐私与使用范围检查。",
            "",
            "当前状态：可以发送，但尚未自动发送，也没有模拟客户已经收到。",
            "",
        ]
    )
    return "\n".join(lines)


def render_human_review_pack_v1(
    requirement_plan: dict[str, Any],
    inventory: dict[str, Any],
    matches: dict[str, Any],
    coverage: dict[str, Any],
    capture_pack_preview: str,
    *,
    missions: dict[str, Any] | None = None,
    subject_confirmation: dict[str, Any] | None = None,
    human_approval: dict[str, Any] | None = None,
) -> str:
    missions = missions or build_customer_capture_missions_v1(requirement_plan)
    subject_confirmation = subject_confirmation or build_subject_media_use_confirmation_v1()
    approval_decision = (
        human_approval["decision"] if human_approval else "review_required"
    )
    match_by_id = {item["requirement_id"]: item for item in matches["matches"]}
    content_by_id = {item["content_id"]: item for item in requirement_plan["contents"]}
    lines = [
        "# Production Footage Planning V1｜Human Review Pack",
        "",
        f"Status: `{approval_decision}`",
        "",
        "## Executive Summary",
        "",
        f"- Approved contents: {requirement_plan['content_count']}",
        f"- Internal semantic shot requirements: {len(requirement_plan['requirements'])}",
        f"- Customer capture missions: {missions['mission_count']}",
        f"- Registered production assets: {inventory['asset_count']}",
        f"- Eligible production assets: {inventory['eligible_asset_count']}",
        f"- Contents requiring capture: {coverage['summary']['capture_required']}",
        "- Case Library media included in Production Asset Pool: no",
        "- Customer Capture Pack sent automatically: no",
        "- Editing or rendering started: no",
        "",
        "## Rights / Privacy / Visual Truth",
        "",
        "- Speaker Persona approval does not authorize identifiable speaker media.",
        f"- 林东方 identifiable media status: `{subject_confirmation['status']}`.",
        f"- Subject-media use scope: `{subject_confirmation['use_scope']}`; future use requires recheck.",
        "- 小孙 customer image/video remains blocked and is not requested or matched.",
        "- Ownership alone cannot pass privacy or subject-release checks.",
        "- Same-process illustration is never exact-event footage and cannot prove the original event, duration, result, or customer story.",
        "- A visual match cannot upgrade Customer Truth or Proof Authority.",
        "",
        "## Existing Production Asset Inventory",
        "",
        f"Audit result: `{inventory['audit_result']}`. Eligible inventory is {inventory['eligible_asset_count']}.",
        "",
        "Excluded research areas: Case sources, Case visual evidence, Case storyboards, Case shots, fingerprints, and acquisition history.",
        "",
        "## Customer Capture Missions",
        "",
        "Four customer-facing missions preserve all internal requirements. One mission may cover multiple requirements and does not require one file per requirement.",
        "",
    ]
    for mission in missions["missions"]:
        lines.extend(
            [
                f"- `{mission['mission_id']}` — {mission['capture_goal']} "
                f"(covers {len(mission['covers_requirement_ids'])} requirements)",
            ]
        )
    lines.append("")
    for index, content_coverage in enumerate(coverage["content_coverage"], 1):
        content = content_by_id[content_coverage["content_id"]]
        lines.extend(
            [
                f"## {index}. {content['content_id']}｜{content['title']}",
                "",
                f"Overall coverage: `{content_coverage['overall_status']}`",
                "",
            ]
        )
        requirements = [
            item
            for item in requirement_plan["requirements"]
            if item["content_id"] == content["content_id"]
        ]
        for requirement in requirements:
            match = match_by_id[requirement["requirement_id"]]
            lines.extend(
                [
                    f"### {requirement['requirement_id']}｜{requirement['requirement_role']}",
                    "",
                    f"- Semantic role: `{requirement['semantic_role']}`",
                    f"- Visual goal: {requirement['visual_information_goal']}",
                    f"- Required state: {requirement['required_visible_state']}",
                    f"- Match: `{match['match_decision']}`",
                    f"- Matched assets: {', '.join(match['matched_asset_ids']) or 'none'}",
                    f"- Privacy constraints: {', '.join(requirement['privacy_constraints'])}",
                    f"- Event relationship: preferred `{requirement['event_relationship_requirement']['preferred']}`; accepted {requirement['event_relationship_requirement']['accepted']}",
                    "",
                ]
            )
        lines.extend(["Capture gaps:", ""])
        for gap in content_coverage["capture_gaps"]:
            lines.append(
                f"- `{gap['capture_priority']}` — {gap['missing_state']}"
            )
        lines.append("")
    lines.extend(
        [
            "## Customer Capture Pack Preview",
            "",
            capture_pack_preview,
            "",
            "## Human Approval",
            "",
            (
                "李健 approved the architecture after the C002 observable-state and C003 "
                "actual-vs-demo normalizations."
                if human_approval
                else "Awaiting human decision."
            ),
            "",
            "The final customer pack is ready to send but has not been sent. No asset intake, editing, or rendering has started.",
            "",
        ]
    )
    return "\n".join(lines)


def run_real_validation(
    *,
    approved_batch_path: Path,
    output_dir: Path,
    workspace_root: Path,
    created_at: str | None = None,
    human_review_closure: bool = False,
    reviewer: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or utc_now()
    if human_review_closure and not reviewer:
        raise ValueError("Human review closure requires a reviewer")
    approved_sha_before = sha256_file(approved_batch_path)
    ledger_path = (
        workspace_root
        / "data"
        / "content_ledgers"
        / "shufang_zhiyuan_community_canteen"
        / "content_ledger_v1.json"
    )
    ledger_sha_before = sha256_file(ledger_path)
    approved_batch = load_json(approved_batch_path)
    requirement_plan = build_shot_requirement_plan_v1(
        approved_batch,
        batch_path=approved_batch_path,
        created_at=created_at,
    )
    if human_review_closure:
        requirement_plan["status"] = "approved_after_minor_normalization"
        requirement_plan["human_review_normalizations"] = {
            "c002_visual_truth": (
                "prior sand-purge state remains Approved Customer Truth context and "
                "is not a required visible state"
            ),
            "c003_event_relationship": (
                "only privacy-safe actual current board operation can fully satisfy "
                "the hero; staged demonstration is supporting illustration only"
            ),
        }
    inventory = audit_production_asset_inventory_v1(
        business_id="shufang_zhiyuan_community_canteen",
        workspace_root=workspace_root,
        target_profile="mix",
        created_at=created_at,
    )
    matches = match_production_assets_v1(
        requirement_plan, inventory, created_at=created_at
    )
    coverage = build_storyboard_coverage_v1(
        requirement_plan, matches, created_at=created_at
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "shot_requirement_plan": output_dir / "shot_requirement_plan_v1.json",
        "production_asset_inventory": output_dir / "production_asset_inventory_v1.json",
        "asset_matches": output_dir / "production_asset_match_v1.json",
        "storyboard_coverage": output_dir / "storyboard_coverage_v1.json",
        "customer_capture_missions": output_dir / "customer_capture_missions_v1.json",
        "subject_media_use_confirmation": output_dir / "subject_media_use_confirmation_v1.json",
        "human_approval": output_dir / "production_footage_planning_human_approval_v1.json",
        "customer_capture_pack": output_dir / "customer_capture_pack_v1.md",
        "human_review_pack": output_dir / "production_footage_planning_review_pack_v1.md",
        "summary": output_dir / "production_footage_planning_summary_v1.json",
    }
    capture_status = "ready_to_send" if human_review_closure else "review_required"
    missions = build_customer_capture_missions_v1(
        requirement_plan, status=capture_status, created_at=created_at
    )
    subject_confirmation = build_subject_media_use_confirmation_v1(
        status="review_required", created_at=created_at
    )
    artifact_shas = {
        "shot_requirement_plan": write_json(paths["shot_requirement_plan"], requirement_plan),
        "production_asset_inventory": write_json(
            paths["production_asset_inventory"], inventory
        ),
        "asset_matches": write_json(paths["asset_matches"], matches),
        "storyboard_coverage": write_json(paths["storyboard_coverage"], coverage),
        "customer_capture_missions": write_json(
            paths["customer_capture_missions"], missions
        ),
        "subject_media_use_confirmation": write_json(
            paths["subject_media_use_confirmation"], subject_confirmation
        ),
    }
    capture_markdown = render_customer_capture_pack_v1(
        requirement_plan, coverage, missions, status=capture_status
    )
    paths["customer_capture_pack"].write_text(
        capture_markdown + "\n", encoding="utf-8"
    )
    artifact_shas["customer_capture_pack"] = sha256_file(paths["customer_capture_pack"])

    human_approval = None
    if human_review_closure:
        human_approval = build_production_footage_planning_human_approval_v1(
            reviewer=reviewer or "",
            approved_at=created_at,
            requirement_plan_path=paths["shot_requirement_plan"],
            missions_path=paths["customer_capture_missions"],
            inventory_path=paths["production_asset_inventory"],
            coverage_path=paths["storyboard_coverage"],
            subject_confirmation_path=paths["subject_media_use_confirmation"],
            capture_pack_path=paths["customer_capture_pack"],
        )
        artifact_shas["human_approval"] = write_json(
            paths["human_approval"], human_approval
        )

    review_markdown = render_human_review_pack_v1(
        requirement_plan,
        inventory,
        matches,
        coverage,
        capture_markdown,
        missions=missions,
        subject_confirmation=subject_confirmation,
        human_approval=human_approval,
    )
    paths["human_review_pack"].write_text(review_markdown + "\n", encoding="utf-8")
    artifact_shas["human_review_pack"] = sha256_file(paths["human_review_pack"])

    approved_sha_after = sha256_file(approved_batch_path)
    ledger_sha_after = sha256_file(ledger_path)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "request_id": approved_batch["request_id"],
        "status": (
            "production_footage_planning_approved_capture_pack_ready_to_send"
            if human_review_closure
            else "production_footage_planning_human_review_gate"
        ),
        "content_count": requirement_plan["content_count"],
        "requirement_count": len(requirement_plan["requirements"]),
        "capture_mission_count": missions["mission_count"],
        "production_asset_count": inventory["asset_count"],
        "eligible_asset_count": inventory["eligible_asset_count"],
        "coverage_summary": coverage["summary"],
        "speaker_media_authorization": subject_confirmation,
        "human_approval": (
            {
                "reviewer": reviewer,
                "decision": human_approval["decision"],
                "artifact_path": str(paths["human_approval"].resolve()),
            }
            if human_approval
            else None
        ),
        "remote_model_calls": 0,
        "local_model_calls": 0,
        "customer_capture_pack_status": capture_status,
        "customer_capture_pack_sent": False,
        "asset_intake_started": False,
        "editing_started": False,
        "rendering_started": False,
        "content_ledger_write_performed": False,
        "artifacts": {
            key: {"path": str(paths[key].resolve()), "file_sha256": artifact_shas[key]}
            for key in artifact_shas
        },
        "immutability": {
            "approved_batch_sha256_before": approved_sha_before,
            "approved_batch_sha256_after": approved_sha_after,
            "approved_batch_unchanged": approved_sha_before == approved_sha_after,
            "content_ledger_sha256_before": ledger_sha_before,
            "content_ledger_sha256_after": ledger_sha_after,
            "content_ledger_unchanged": ledger_sha_before == ledger_sha_after,
        },
        "authority": {
            "case_media_used": False,
            "script_regenerated": False,
            "content_claim_authority_changed": False,
            "proof_authority_created": False,
            "persona_modified": False,
            "pattern_or_case_lifecycle_modified": False,
        },
        "validation": {
            "approved_batch_required": approved_batch.get("status") == "approved",
            "all_four_contents_planned": requirement_plan["content_count"] == 4,
            "all_four_capture_missions_planned": missions["mission_count"] == 4,
            "all_fourteen_internal_requirements_preserved": len(requirement_plan["requirements"]) == 14,
            "all_requirements_mapped_once_to_capture_missions": sorted(
                requirement_id
                for mission in missions["missions"]
                for requirement_id in mission["covers_requirement_ids"]
            )
            == sorted(item["requirement_id"] for item in requirement_plan["requirements"]),
            "each_content_has_one_hero": all(
                item["hero_requirement_count"] == 1
                for item in requirement_plan["contents"]
            ),
            "fixed_shot_count_not_required": not requirement_plan["fixed_shot_count_required"],
            "case_media_excluded": not inventory["authority"]["case_media_ingested"],
            "zero_inventory_valid": inventory["asset_count"] == 0,
            "all_four_capture_required": coverage["summary"]["capture_required"] == 4,
            "approved_batch_unchanged": approved_sha_before == approved_sha_after,
            "content_ledger_unchanged": ledger_sha_before == ledger_sha_after,
            "human_approval_persisted": bool(
                not human_review_closure
                or (
                    human_approval
                    and human_approval["decision"]
                    == "approved_after_minor_normalization"
                )
            ),
            "passed": all(
                [
                    approved_batch.get("status") == "approved",
                    requirement_plan["content_count"] == 4,
                    missions["mission_count"] == 4,
                    len(requirement_plan["requirements"]) == 14,
                    sorted(
                        requirement_id
                        for mission in missions["missions"]
                        for requirement_id in mission["covers_requirement_ids"]
                    )
                    == sorted(
                        item["requirement_id"]
                        for item in requirement_plan["requirements"]
                    ),
                    all(
                        item["hero_requirement_count"] == 1
                        for item in requirement_plan["contents"]
                    ),
                    not requirement_plan["fixed_shot_count_required"],
                    not inventory["authority"]["case_media_ingested"],
                    coverage["summary"]["capture_required"] == 4,
                    approved_sha_before == approved_sha_after,
                    ledger_sha_before == ledger_sha_after,
                    not human_review_closure
                    or bool(
                        human_approval
                        and human_approval["decision"]
                        == "approved_after_minor_normalization"
                    ),
                ]
            ),
        },
    }
    summary_sha = write_json(paths["summary"], summary)
    return {**summary, "summary_path": str(paths["summary"].resolve()), "summary_sha256": summary_sha}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Production Footage Planning & Capture V1 artifacts."
    )
    parser.add_argument("--approved-batch", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workspace-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--human-review-closure", action="store_true")
    parser.add_argument("--reviewer")
    args = parser.parse_args()
    result = run_real_validation(
        approved_batch_path=Path(args.approved_batch),
        output_dir=Path(args.output_dir),
        workspace_root=Path(args.workspace_root),
        human_review_closure=args.human_review_closure,
        reviewer=args.reviewer,
    )
    if not result["validation"]["passed"]:
        raise SystemExit("Production Footage Planning V1 validation failed")
    print(
        "PRODUCTION FOOTAGE PLANNING V1 APPROVED"
        if args.human_review_closure
        else "PRODUCTION FOOTAGE PLANNING V1 HUMAN REVIEW READY"
    )
    print(f"Contents: {result['content_count']}")
    print(f"Internal requirements: {result['requirement_count']}")
    print(f"Customer capture missions: {result['capture_mission_count']}")
    print(f"Eligible assets: {result['eligible_asset_count']}")
    print(f"Capture required: {result['coverage_summary']['capture_required']}")
    print("Remote model calls: 0")
    print("Local model calls: 0")
    print(f"Summary: {result['summary_path']}")


if __name__ == "__main__":
    main()
