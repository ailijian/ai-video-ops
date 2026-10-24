"""Derived capacity explanation. Never an Admission, approval or Ledger writer.

The original readers own every eligibility decision. Shadow research is not
imported here. Counts apply only to the named Native scope, never all creativity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from human_review_operations_v1 import io_path
from show_customer_status_v1 import resolve_current_persona, resolve_speaker_persona, load_content_ledger
from novel_news_opportunity_v1 import project_novel_news_opportunities
from content_intent_reservations_v1 import pending
from news_delivery_v1 import preview_news_delivery, pending_source_ids
from news_slot_recommendation_v1 import build_recommendation
from creative_style_v1 import catalog_snapshot, validate_style_facts, definition
from news_runtime_v1_2 import current
from profile_compatibility_release_v1_1 import CONFIG

SCHEMA = 'creative-capacity-read-projection-v1.0'


class CapacityReadError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(io_path(path).read_bytes()).hexdigest()


def attempt(function):
    try:
        return function(), None
    except (RuntimeError, ValueError, OSError) as exc:
        return None, getattr(exc, 'code', 'NATIVE_READER_UNAVAILABLE')


def reference(owner, identifier, path, version):
    # Public projection intentionally contains neither paths nor raw fact values.
    return {'owner': owner, 'id': identifier, 'version': str(version), 'sha256': file_sha(path)}


def basis(root, business_id, speaker_id):
    business = resolve_current_persona(root, business_id, 'business')
    speaker = resolve_speaker_persona(root, business, speaker_id)
    ledger_path = root / 'data/content_ledgers' / business_id / 'content_ledger_v1.json'
    if io_path(ledger_path).is_file():
        ledger = load_content_ledger(root, business_id)['artifact']
        ledger_sha = file_sha(ledger_path)
    else:
        from content_creation_entry_v1 import has_ledger_worthy_historical_exposure
        if has_ledger_worthy_historical_exposure(root, business_id):
            raise CapacityReadError('CONTENT_HISTORY_WITHOUT_LEDGER')
        ledger, ledger_sha = {'business_id': business_id, 'entries': []}, None
    held = pending(root, business_id)
    qualified, news_error = attempt(lambda: current(root))
    style, style_error = attempt(lambda: catalog_snapshot(root, publish=False))
    news_binding = qualified[1] if qualified else None
    style_ref, catalog = style if style else (None, None)
    state = {
        'business': reference('native-business', business_id, business['path'], business['revision']),
        'speaker': reference('native-speaker', speaker_id, speaker['path'], speaker['revision']),
        'ledger_sha256': ledger_sha, 'pending_sha256': digest(held),
        'news_binding_sha256': digest(news_binding), 'news_error': news_error,
        'style_catalog_sha256': digest(catalog), 'style_error': style_error,
        'runtime_config_sha256': file_sha(root / CONFIG) if io_path(root / CONFIG).is_file() else None,
        'reader_source_sha256': {name: file_sha(Path(__file__).with_name(name)) for name in (
            'creative_capacity_read_v1.py', 'novel_news_opportunity_v1.py', 'content_quality_v1.py',
            'news_delivery_v1.py', 'news_slot_recommendation_v1.py', 'content_intent_reservations_v1.py',
            'creative_style_v1.py', 'news_runtime_v1_2.py')},
    }
    return state, business, speaker, ledger, held, news_binding, catalog


def read_inventory(*, pipeline_root, business_id, speaker_id, novel_target=10, authorization_scope_sha256):
    from native_batch_v1 import identifier
    identifier(business_id); identifier(speaker_id)
    if type(novel_target) is not int or not 0 <= novel_target <= 40:
        raise CapacityReadError('CAPACITY_READ_TARGET_INVALID')
    if (not isinstance(authorization_scope_sha256, str) or len(authorization_scope_sha256) != 64
            or any(c not in '0123456789abcdef' for c in authorization_scope_sha256)):
        raise CapacityReadError('CAPACITY_READ_AUTH_SCOPE_REQUIRED')
    root = Path(pipeline_root).resolve()
    state, business, speaker, ledger, held, binding, catalog = basis(root, business_id, speaker_id)
    novel, novel_error = attempt(lambda: project_novel_news_opportunities(
        pipeline_root=root, business_id=business_id, speaker_id=speaker_id))
    repurpose, repurpose_error = attempt(lambda: preview_news_delivery(
        pipeline_root=root, business_id=business_id, speaker_id=speaker_id))
    for value, version in [(novel, 'novel-news-opportunity-projection-v1.0'), (repurpose, 'news-delivery-preview-v1.0')]:
        if value is not None and (value.get('schema_version') != version
                or value.get('business_id') != business_id or value.get('speaker_id') != speaker_id):
            raise CapacityReadError('CAPACITY_READ_NATIVE_SCOPE_OR_VERSION_INVALID')
    opportunities = []
    for item in (novel or {}).get('opportunities', []):
        feasibility = item.get('production_feasibility') or {}
        opportunities.append({'concept_id': item['concept_id'],
            'fact_atom_refs': list(item.get('fact_atom_refs') or []),
            'novelty_status': item['novelty_status'], 'qualification': feasibility.get('status', 'unknown'),
            'blocker_code': feasibility.get('blocker_type'), 'pattern_id': item.get('applicable_pattern_id')})
    qualified_count = sum(i['novelty_status'] == 'novel' and i['qualification'] == 'supported' for i in opportunities) if novel else None
    eligible = {i['source_content_id'] for i in (repurpose or {}).get('eligible_sources', [])}
    presented = {i['source_content_id']: i['presentation_count'] for i in (repurpose or {}).get('already_presented_sources', [])}
    reserved_sources, reserved_error = attempt(lambda: pending_source_ids(root, business_id))
    sources = []
    for entry in ledger.get('entries', []):
        if entry.get('status') not in {'approved', 'exported', 'published'}:
            continue
        if entry.get('business_id') != business_id:
            raise CapacityReadError('CAPACITY_READ_LEDGER_SCOPE_INVALID')
        cid = entry['content_id']
        recommendation, error = attempt(lambda: build_recommendation(ledger=ledger, business_id=business_id, content_id=cid))
        if repurpose_error or reserved_error:
            status, reason = 'unknown', repurpose_error or reserved_error
        elif cid in eligible:
            status, reason = 'eligible', None
        elif cid in presented:
            status, reason = 'already_presented', 'ALREADY_EXPORTED_SAME_NEWS_PATTERN'
        elif cid in (reserved_sources or set()):
            status, reason = 'reserved', 'SOURCE_PENDING_NATIVE_REQUEST'
        else:
            status, reason = 'blocked', error or (recommendation or {}).get('status', 'NATIVE_SOURCE_NOT_ELIGIBLE')
            if reason == 'supported':
                reason = 'NATIVE_SOURCE_NOT_ELIGIBLE'
        sources.append({'source_content_id': cid, 'title': entry.get('title') or cid,
            'source_profile': entry.get('production_profile'), 'source_status': entry['status'],
            'eligibility': status, 'blocker_code': reason, 'presentation_count': presented.get(cid, 0),
            'native_information_segment_count': (recommendation or {}).get('recommended_slot_count')})
    structures = [{'type_id': 'news', 'production_profile': 'news',
        'structure_status': 'qualified' if binding else 'blocked', 'blocker_code': state['news_error'],
        'scope': 'price_offer_led_only' if binding else None,
        'pattern_count': 1 if binding else None,
        'structural_case_count': len(binding.get('structural_sources', [])) if binding else None,
        'production_eligibility_granted': False}]
    for name in ('persona', 'story', 'conversion'):
        rule = next((s for s in (catalog or {}).get('styles', []) if s['style_id'] == name), None)
        _, fact_error = attempt(lambda: validate_style_facts(name, definition(name), business['artifact'], speaker['artifact']))
        structures.append({'type_id': name, 'production_profile': 'mix',
            'structure_status': 'qualified' if rule else 'blocked', 'blocker_code': state['style_error'] if not rule else None,
            'fact_speaker_status': 'blocked' if fact_error else 'supported', 'fact_speaker_blocker': fact_error,
            'style_version': rule.get('style_version') if rule else None,
            'pattern_count': len(rule.get('pattern_scope_refs', [])) if rule else None,
            'pattern_scope_sha256': digest(rule.get('pattern_scope_refs', [])) if rule else None,
            'compatibility_scope_sha256': digest(rule.get('compatibility_scope_refs', [])) if rule else None,
            'release_sha256': rule.get('release_ref', {}).get('sha256') if rule else None,
            'qualified_topic_count': None, 'production_eligibility_granted': False})
    reasons = []
    if novel_error:
        reasons.append({'code': novel_error, 'kind': 'native_reader_blocked', 'count': None})
    else:
        for status, code in [('already_communicated', 'HISTORICAL_CORE_EXPLICIT'), ('reserved', 'PENDING_NATIVE_RESERVATION'), ('uncertain', 'NOVELTY_UNCERTAIN')]:
            count = sum(i['novelty_status'] == status for i in opportunities)
            if count: reasons.append({'code': code, 'kind': status, 'count': count})
        for code in sorted({i['blocker_code'] for i in opportunities if i['novelty_status'] == 'novel' and i['qualification'] != 'supported' and i['blocker_code']}):
            reasons.append({'code': code, 'kind': 'qualification_or_structure_blocked', 'count': sum(i['blocker_code'] == code for i in opportunities)})
        if novel_target > len(opportunities):
            reasons.append({'code': 'NO_ADDITIONAL_APPROVED_OPPORTUNITY_IN_CURRENT_PRICE_SCOPE',
                'kind': 'insufficient_current_sources', 'count': novel_target - len(opportunities)})
    after, *_ = basis(root, business_id, speaker_id)
    if state != after:
        raise CapacityReadError('CAPACITY_READ_SOURCE_CHANGED')
    if reserved_error:
        repurpose_error = reserved_error
    return {'schema_version': SCHEMA, 'business_id': business_id, 'speaker_id': speaker_id,
        'snapshot_sha256': digest({'sources': state, 'authorization': authorization_scope_sha256, 'target': novel_target}),
        'source_snapshot': state, 'new_semantic_inventory': {
            'scope': 'current_native_news_price_opportunities_only', 'status': 'blocked' if novel_error else 'read',
            'qualified_count': qualified_count, 'enumerated_count': len(opportunities) if novel else None,
            'pending_native_concept_count': len(held), 'opportunities': opportunities, 'reader_error': novel_error},
        'new_expression_inventory': {'scope': 'current_native_news_price_repurpose_only',
            'status': 'blocked' if repurpose_error else 'read', 'qualified_source_count': len(eligible) if repurpose and not repurpose_error else None,
            'sources': sources, 'reader_error': repurpose_error}, 'structure_qualification': structures,
        'target_gap': {'news_novel_target': novel_target, 'qualified_novel': qualified_count,
            'novel_shortfall': max(0, novel_target-qualified_count) if qualified_count is not None else None,
            'repurpose_automatically_substituted': False, 'diagnostic_reasons': reasons,
            'reasons_are_inventory_explanations_not_cross_type_delivery_arithmetic': True},
        'authority': {'derived_only': True, 'authorizes_execution': False, 'business_writes': False,
            'new_novelty_approval': False, 'reservation_released': False, 'shadow_policy_used': False,
            'actual_deliverable_total': None, 'fresh_native_admission_still_required': True}}
