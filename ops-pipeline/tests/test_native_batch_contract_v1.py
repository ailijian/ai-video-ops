"""Schema and Quality-unit checks only; these fake refs confer no Native qualification."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from creation_batch_contract_v1 import BatchError, check
from creative_style_v1 import artifact
from human_review_operations_v1 import write_once
from native_batch_v1 import configuration
import content_intent_reservations_v1 as holds


def config(**counts):
    return {'mode': 'free', 'stage': 'launch', 'quantities': {
        k: counts.get(k, 0) for k in ('novel', 'repurpose', 'persona', 'story', 'conversion')},
        'revision': 0, 'repurposeEnabled': bool(counts.get('repurpose')),
        'repurposeSourceIds': [f'original-source-{i}' for i in range(counts.get('repurpose',0))],
        'cycles': 1, 'cyclesConfirmed': False, 'combinedTarget': None, 'previewRevision': None}


def reference(tmp_path):
    path = tmp_path / 'unit-not-native.json'
    write_once(path, {'unit_test_only': True})
    return artifact(path, 'schema-unit-NOT-Native', 'unit', '1')


def test_batch_config_is_bounded_explicit_and_does_not_swap_news_sources():
    result = configuration(config(novel=2, persona=2, repurpose=1))
    assert result['quantities']['novel'] == 2 and result['quantities']['repurpose'] == 1
    assert configuration(config(novel=40))['quantities']['novel'] == 40
    for payload in [config(), config(novel=41), config(persona=True),
                    {**config(persona=2), 'mode': 'stage', 'combinedTarget': 3},
                    {**config(persona=2), 'stage': 'steady', 'mode': 'stage'},
                    {**config(repurpose=1), 'repurposeEnabled': False}]:
        with pytest.raises(BatchError):
            configuration(payload)


def test_policy_two_preserves_exact_legacy_scope_and_caps_explicit_cycles():
    from native_batch_v1 import validate_policy, POLICY, LEGACY_POLICY
    from human_review_operations_v1 import read
    old, new = validate_policy(read(LEGACY_POLICY)), validate_policy(read(POLICY))
    assert old['maximum_logical_slots'] == 5 and new['maximum_logical_slots'] == 40
    for invalid in [{**old, 'maximum_logical_slots': 40}, {**new, 'dispatch_per_business': 2},
                    {**new, 'dispatch_per_business': True},
                    {**new, 'production_qualification_granted': True}]:
        with pytest.raises(BatchError): validate_policy(invalid)
    for cycles in [0, 6, True]:
        with pytest.raises(BatchError):
            configuration({**config(persona=1), 'mode': 'stage', 'stage': 'steady',
                'cycles': cycles, 'cyclesConfirmed': True})
    assert configuration({**config(persona=1), 'mode': 'stage', 'stage': 'steady',
        'cycles': 5, 'cyclesConfirmed': True})['explicit_cycles'] == 5
    legacy={**config(persona=2),'mode':'stage','stage':'steady','cycles':6,'cyclesConfirmed':True}
    assert configuration(legacy,policy=old)['explicit_cycles']==6


def test_pre_v2_snapshot_without_policy_keeps_legacy_no_cycle_cap(tmp_path):
    from native_batch_v1 import batch_policy,directory,configuration
    from human_review_operations_v1 import write_once
    write_once(directory(tmp_path,'batch_unit')/'configuration.json',{'source_snapshot':{'unit_only':True}})
    old=batch_policy(tmp_path,'batch_unit')
    assert old['policy_version']=='1'
    assert configuration({**config(story=2),'mode':'stage','stage':'steady','cycles':6,
        'cyclesConfirmed':True},policy=old)['explicit_cycles']==6


def test_admission_news_uses_null_style_not_fabricated_mix_type(tmp_path):
    ref = reference(tmp_path)
    item = {'schema_version': 'native-batch-admission-v1.1', 'business_id': 'unit',
        'batch_intent_ref': ref, 'native_request_id': 'gen_unit', 'style_ref': None,
        'ordered_slots': ['batch_unit-S001'], 'source_refs': [ref], 'admission_policy_ref': ref,
        'reservation_intent_ref': ref, 'actor_intent': {'actor_id': 'unit', 'permission_snapshot': ref,
            'operation_id': 'unit', 'payload_sha256': '0' * 64}}
    assert check(item, 'C04') == item
    with pytest.raises(BatchError):
        check({**item, 'force': True}, 'C04')


def test_composite_schema_enforces_two_file_bound_even_with_native_validator(tmp_path):
    ref = reference(tmp_path)
    value = {'schema_version': 'creation-composite-delivery-completion-v1.0', 'business_id': 'unit',
        'intent_ref': ref, 'ordered_file_receipt_refs': [ref, ref], 'scope': 'complete_target',
        'delivered_slot_ids': ['unit-S001'], 'semantic_delta': 0, 'exposure_delta': 0,
        'presentation_delta': 0, 'actor_intent': {'actor_id': 'unit', 'permission_snapshot': ref,
            'operation_id': 'unit', 'payload_sha256': '0' * 64}}
    check(value, 'C08')
    with pytest.raises(BatchError):
        check({**value, 'ordered_file_receipt_refs': [ref] * 3}, 'C08')
    with pytest.raises(BatchError):
        check({**value, 'semantic_delta': 1}, 'C08')


def reserve_unit(root, request_id, ref, concept):
    group = {'request_id': request_id, 'operation_id': request_id, 'profile': 'mix', 'source_kind':'novel_content',
             'slots': [{'slot_id': request_id + '-S001'}]}
    reservation = holds.reserve_admission(root, 'unit-business', group, [ref])
    holds.reserve_concepts(root, 'unit-business', request_id, [concept], reservation)


def concept(index):
    topic, claim = {1: ('allergens', '先核对顾客忌口再决定是否可以按单制作'),
                    2: ('traceability', '独立批号标签对应本次餐盒制作记录')}[index]
    return {'concept_id': 'concept-' + topic, 'central_claim': claim,
        'audience_need': 'unit-need-' + topic, 'content_job': 'unit-job-' + topic,
        'primary_topic': topic, 'primary_fact_refs': ['unit-fact-' + topic],
        'primary_fact_atom_refs': ['unit-atom-' + topic],
        'exclusive_anchor': {'kind': 'authorized_customer_fact', 'value': claim}}


def test_pending_intentions_block_cross_request_reuse_without_becoming_ledger(tmp_path):
    ref = reference(tmp_path)
    reserve_unit(tmp_path, 'gen_first', ref, concept(1))
    assert not (tmp_path / 'data/content_ledgers').exists()
    with pytest.raises(BatchError) as error:
        holds.assert_available(tmp_path, 'unit-business', [concept(1)], 'gen_second')
    assert error.value.code == 'CONTENT_INTENT_ALREADY_RESERVED'
    holds.assert_available(tmp_path, 'unit-business', [concept(2)], 'gen_second')
    holds.assert_available(tmp_path, 'unit-business', [concept(1)], 'gen_first')
    holds.assert_available(tmp_path, 'another-business', [concept(1)], 'gen_second')


def test_pending_memory_cannot_be_rebound_by_retry_or_elapsed_time(tmp_path):
    ref = reference(tmp_path)
    reserve_unit(tmp_path, 'gen_first', ref, concept(1))
    ledger = tmp_path / 'data/content_ledgers/unit-business/content_ledger_v1.json'
    write_once(ledger, {'entries': [{'unrelated_native_append': True}]})
    with pytest.raises(BatchError) as error:
        holds.reserve_concepts(tmp_path, 'unit-business', 'gen_first', [concept(1)], ref)
    assert error.value.code == 'CONTENT_RESERVATION_MEMORY_CHANGED'
    assert holds.pending(tmp_path, 'unit-business') == [concept(1)]


def test_zero_selection_keeps_allocation_without_a_semantic_claim(tmp_path):
    ref = reference(tmp_path)
    group = {'request_id': 'gen_empty', 'operation_id': 'empty', 'profile': 'mix', 'source_kind':'novel_content',
             'slots': [{'slot_id': 'batch_empty-S001'}]}
    allocation = holds.reserve_admission(tmp_path, 'unit-business', group, [ref])
    assert holds.reserve_concepts(tmp_path, 'unit-business', 'gen_empty', [], ref) == allocation
    assert holds.pending(tmp_path, 'unit-business') == []
    assert holds.events(tmp_path, 'unit-business', 'gen_empty')[0][1]['semantic_owner_keys'] == ['native-intent:gen_empty']


def test_terminal_label_without_native_settlement_proof_cannot_release_a_hold(tmp_path):
    ref=reference(tmp_path)
    reserve_unit(tmp_path,'gen_fake_terminal',ref,concept(1))
    value=dict(holds.events(tmp_path,'unit-business','gen_fake_terminal')[-1][1])
    value.pop('parent_event_ref',None)
    value['event']='safely_released'
    holds._append(tmp_path,'unit-business','gen_fake_terminal',value)
    with pytest.raises(BatchError) as error:holds.pending(tmp_path,'unit-business')
    assert error.value.code=='CONTENT_SETTLEMENT_INVALID'
    assert not (tmp_path/'data/content_ledgers').exists()


@pytest.mark.parametrize('raw_refs', [None, ['external-provider-invalid-primary-atom']])
def test_nested_material_atoms_cannot_hide_a_cross_request_collision(tmp_path, raw_refs):
    from content_quality_v1 import novelty_evaluation
    ref = reference(tmp_path)
    raw = concept(1)
    atoms = raw.pop('primary_fact_atom_refs')
    raw['material_information_gain_v1_1_1'] = {'primary_fact_atom_refs': atoms}
    if raw_refs is not None:
        raw['primary_fact_atom_refs'] = raw_refs
    raw['primary_fact_refs'] += ['another-approved-value-field']
    reserve_unit(tmp_path, 'gen_nested', ref, raw)
    competing = concept(2)
    competing['primary_fact_atom_refs'] = atoms
    assert not novelty_evaluation(competing, [], [raw])['hard_duplicate']
    with pytest.raises(BatchError) as error:
        holds.assert_available(tmp_path, 'unit-business', [competing], 'gen_competing')
    assert error.value.code == 'CONTENT_INTENT_ALREADY_RESERVED'


def test_normalized_retry_retains_original_claim_bytes_and_reference(tmp_path):
    from creative_style_v1 import digest
    ref = reference(tmp_path)
    group = {'request_id':'gen_old_claim', 'operation_id':'old', 'profile':'mix', 'source_kind':'novel_content',
             'slots':[{'slot_id':'batch_old-S001'}]}
    allocation = holds.reserve_admission(tmp_path, 'unit-business', group, [ref])
    raw = concept(1)
    raw['material_information_gain_v1_1_1'] = {'primary_fact_atom_refs':raw.pop('primary_fact_atom_refs')}
    payload = {'schema_version':'native-quality-pending-concepts-v1.0', 'business_id':'unit-business',
               'native_request_id':'gen_old_claim', 'concepts':[raw]}
    path = holds.directory(tmp_path, 'unit-business', 'gen_old_claim') / 'claims' / (digest(payload)+'.json')
    write_once(path, payload)
    original = artifact(path, 'native-quality-selected-concepts', 'gen_old_claim', payload['schema_version'])
    value = dict(holds.events(tmp_path, 'unit-business', 'gen_old_claim')[0][1])
    value['native_evidence_refs'] = [allocation, original]
    holds._append(tmp_path, 'unit-business', 'gen_old_claim', value)
    before = path.read_bytes()
    assert holds.reserve_concepts(tmp_path, 'unit-business', 'gen_old_claim', [raw], allocation) == original
    assert path.read_bytes() == before
    assert len(holds.events(tmp_path, 'unit-business', 'gen_old_claim')) == 2
    assert list(path.parent.iterdir()) == [path]


def cache_inputs(tmp_path):
    ref = reference(tmp_path)
    return dict(root=tmp_path, batch_id='batch_unit', request_id='gen_unit', business_id='unit-business',
        stage='content_plan', index=1, source_snapshot={'unit_memory': 'original'},
        actor_intent={'actor_id': 'unit', 'permission_snapshot': ref, 'operation_id': 'unit', 'payload_sha256': '0' * 64},
        batch_intent_ref=ref, prompt='synthetic provider boundary', current_snapshot=lambda: {'unit_memory': 'original'})


def test_unknown_provider_result_cannot_automatically_resend(tmp_path):
    from batch_provider_recovery_v1 import _cached_call
    calls = []
    def lost(_):
        calls.append('remote')
        raise TimeoutError('synthetic uncertain transport result')
    kwargs = cache_inputs(tmp_path)
    for _ in range(2):
        with pytest.raises(BatchError) as error:
            _cached_call(**kwargs, transport=lost)
        assert error.value.code == 'CREATION_BATCH_OUTCOME_UNKNOWN'
    assert calls == ['remote']


def test_saved_provider_response_recovers_locally_without_new_dispatch(tmp_path):
    from batch_provider_recovery_v1 import _cached_call
    calls = []
    def remote(_):
        calls.append('remote')
        return {'payload': {'unit_result': 'received'}}
    kwargs = cache_inputs(tmp_path)
    first = _cached_call(**kwargs, transport=remote)
    assert _cached_call(**kwargs, transport=remote) == first
    assert calls == ['remote']
    with pytest.raises(BatchError) as error:
        _cached_call(**{**kwargs, 'prompt': 'another prompt'}, transport=remote)
    assert error.value.code == 'CREATION_BATCH_SOURCE_CHANGED' and calls == ['remote']


def test_saved_response_cannot_rebind_a_changed_memory(tmp_path):
    from batch_provider_recovery_v1 import _cached_call
    calls = []
    current = {'unit_memory': 'original'}
    def remote(_):
        calls.append('remote')
        current['unit_memory'] = 'changed-by-another-native-owner'
        return {'payload': {'unit_result': 'received'}}
    kwargs = {**cache_inputs(tmp_path), 'current_snapshot': lambda: dict(current)}
    with pytest.raises(BatchError) as error:
        _cached_call(**kwargs, transport=remote)
    assert error.value.code == 'CREATION_BATCH_SOURCE_CHANGED'
    assert list(tmp_path.glob('data/creation_batches/*/provider_stages/*/*/*/response.json'))
    with pytest.raises(BatchError):
        _cached_call(**kwargs, transport=remote)
    assert calls == ['remote']
