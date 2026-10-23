"""C06 transport evidence for Native Mix phases that lacked response recovery.

Only the external boundary is wrapped. Native planning/generation still
validate and publish their own results. A dispatch without a saved response is
unknown, including after process loss; it is never an automatic retry permit.
"""
from pathlib import Path
import hashlib
from contextlib import contextmanager

from creation_batch_contract_v1 import BatchError, check
from creative_style_v1 import artifact, digest, file_sha
from human_review_operations_v1 import io_path, read, write_once
from operation_lock_v1 import operation_lock
import native_batch_v1 as batch


def snapshot(root, request):
    from show_customer_status_v1 import resolve_current_persona, resolve_speaker_persona
    from content_intent_reservations_v1 import memory
    root = Path(root)
    active = batch.policy_qualification(root)
    business = resolve_current_persona(root, request['persona_id'], 'business')
    speaker = resolve_speaker_persona(root, business, request['speaker_persona'])
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    confirmed = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])
    original = read(batch.directory(root, confirmed['batch_id']) / 'configuration.json')['source_snapshot']
    if memory(root, request['persona_id']) != original['memory']:
        raise BatchError('CREATION_BATCH_MEMORY_CHANGED', 'An open batch generation cannot rebind its confirmed memory')
    if active['binding'] != original['qualification']:
        raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Confirmed batch qualification changed')
    expected = {r['owner']:r for r in confirmed['context_refs'] if r['owner'] in ('native-business', 'native-speaker')}
    if file_sha(business['path']) != expected['native-business']['sha256'] or file_sha(speaker['path']) != expected['native-speaker']['sha256']:
        raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Confirmed Business/Speaker changed before generation')
    request_path = root / 'data/generation_requests' / request['request_id'] / 'generation_request_v1.json'
    source_path = root / 'data/production_plans' / request['request_id'] / 'generation_source_plan_v1.json'
    return {'request_sha256': file_sha(request_path), 'source_plan_sha256': file_sha(source_path),
            'business_sha256': file_sha(business['path']), 'speaker_sha256': file_sha(speaker['path']),
            'memory': memory(root, request['persona_id']), 'qualification_sha256': digest(active['binding'])}


def phase_directory(root, batch_id, request_id, stage):
    if stage not in ('content_plan', 'script_generation'):
        raise BatchError('CREATION_BATCH_PHASE_UNSUPPORTED', 'Unknown Native provider stage')
    return batch.directory(root, batch_id) / 'provider_stages' / batch.identifier(request_id) / stage


def effective_phase(root, request, stage):
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    confirmed = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])
    phase = phase_directory(root, confirmed['batch_id'], request['request_id'], stage)
    if stage == 'script_generation':
        import generation_recovery_v1 as recovery
        graph = recovery.graph(Path(root), request['request_id'])
        reference = ((graph['result'] or {}).get('intent_ref'))
        if graph['pending']:
            reference = recovery.ref(root, recovery.operation_root(root, request['request_id'], graph['pending']['operation_id'])/'intent.json')
        if reference:
            intent = recovery.check(read(recovery.resolve_ref(root, reference)), recovery.INTENT)
            phase /= 'recovery_' + intent['operation_id']
    return phase


def _cached_call(root, batch_id, request_id, business_id, stage, index, source_snapshot,
                 actor_intent, batch_intent_ref, transport, prompt, current_snapshot, parameters=None):
    base = phase_directory(root, batch_id, request_id, stage)
    recovery_ref = (parameters or {}).get('native_recovery_ref')
    if recovery_ref:
        import generation_recovery_v1 as recovery
        intent = recovery.check(read(recovery.resolve_ref(root, recovery_ref)), recovery.INTENT)
        if intent['request_id'] != request_id or stage != 'script_generation':
            raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Recovery provider scope differs from its Native Request')
        base /= 'recovery_' + intent['operation_id']
    base /= f'{index:03d}'
    intent_path, dispatch_path, response_path = (base / n for n in ('intent.json', 'dispatch.json', 'response.json'))
    expected = {'schema_version': 'native-batch-provider-intent-v1.0', 'request_id': request_id,
        'batch_id': batch_id, 'stage': stage, 'call_index': index, 'source_snapshot': source_snapshot,
        'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(), 'actor_intent': actor_intent, 'parameters': parameters or {}}
    from novel_news_generation_recovery_v1 import mutation_fence
    with mutation_fence(root), operation_lock(root, 'creation-batch-provider:' + business_id):
        from content_intent_reservations_v1 import assert_executable
        assert_executable(root,business_id,request_id)
        if io_path(intent_path).is_file():
            if read(intent_path) != expected:
                raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Original provider operation, prompt or source changed')
        else:
            if not batch.running(root, batch_id):
                raise BatchError('CREATION_BATCH_PAUSED', 'No new dispatch after pause/end')
            write_once(intent_path, expected)
        attempt = artifact(intent_path, 'native-provider-stage', request_id, expected['schema_version'])
        if io_path(response_path).is_file():
            response = read(response_path)
            if response.get('intent_ref') != attempt or not valid_response(response):
                raise BatchError('CREATION_BATCH_RESPONSE_INVALID', 'Saved response differs from original operation')
            if current_snapshot() != source_snapshot:
                raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Saved response cannot rebind source or memory')
            # A process may stop after the response is durable but before its
            # projection is published. Rebuild only that derived evidence; an
            # existing conflicting projection must still fail closed.
            _evidence(root, base, business_id, request_id, stage, batch_intent_ref, actor_intent, 'response_saved',
                      [attempt, artifact(response_path, 'native-provider-stage', request_id, response['schema_version'])])
            if response['schema_version'] == 'native-batch-provider-response-error-v1.0':
                from generate_mix_scripts_v1 import RemoteAttemptError
                raise RemoteAttemptError(response['error']['message'], response['error']['telemetry'])
            return response['response']
        if io_path(dispatch_path).is_file():
            raise BatchError('CREATION_BATCH_OUTCOME_UNKNOWN', 'External result is unknown; automatic resend is prohibited')
        if not batch.running(root, batch_id):
            raise BatchError('CREATION_BATCH_PAUSED', 'No new dispatch after pause/end')
        if current_snapshot() != source_snapshot:
            raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Source changed before external dispatch')
        write_once(dispatch_path, {'schema_version': 'native-batch-provider-dispatch-v1.0', 'intent_ref': attempt})
        _evidence(root, base, business_id, request_id, stage, batch_intent_ref, actor_intent, 'in_flight', [attempt, artifact(dispatch_path, 'native-provider-stage', request_id, '1')])
    # No Business/Batch/provider lock is held across the external model call.
    try:
        response = transport(prompt)
    except Exception as exc:
        from generate_mix_scripts_v1 import RemoteAttemptError
        telemetry = getattr(exc, 'telemetry', {})
        if isinstance(exc, RemoteAttemptError) and telemetry.get('error_type') in (
                'empty_response', 'json_parse_failed', 'truncated_json_response'):
            error = {'message': str(exc), 'telemetry': telemetry}
            value = {'schema_version':'native-batch-provider-response-error-v1.0',
                     'intent_ref':attempt, 'error':error, 'payload_sha256':digest(error)}
            with mutation_fence(root):
                write_once(response_path, value)
                _evidence(root, base, business_id, request_id, stage, batch_intent_ref, actor_intent, 'response_saved',
                          [attempt, artifact(response_path, 'native-provider-stage', request_id, value['schema_version'])])
            # The original generator classifies this known invalid response and
            # can publish its original C3-05 zero-output failure. Network loss
            # and provider_call_failed remain unknown and cannot gain this path.
            raise
        raise BatchError('CREATION_BATCH_OUTCOME_UNKNOWN', 'External dispatch failed without a durable response; retain its original identity') from exc
    value = {'schema_version': 'native-batch-provider-response-v1.0', 'intent_ref': attempt,
             'response': response, 'payload_sha256': digest(response)}
    with mutation_fence(root):
        write_once(response_path, value)
        _evidence(root, base, business_id, request_id, stage, batch_intent_ref, actor_intent, 'response_saved',
                  [attempt, artifact(response_path, 'native-provider-stage', request_id, value['schema_version'])])
    if current_snapshot() != source_snapshot:
        raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Source changed; received response is retained for original local recovery')
    return response


def valid_response(saved):
    version = saved.get('schema_version')
    if version == 'native-batch-provider-response-error-v1.0':
        error = saved.get('error')
        return bool(isinstance(error, dict) and set(error) == {'message', 'telemetry'}
            and isinstance(error['message'], str) and isinstance(error['telemetry'], dict)
            and error['telemetry'].get('error_type') in ('empty_response', 'json_parse_failed', 'truncated_json_response')
            and saved.get('payload_sha256') == digest(error))
    return version == 'native-batch-provider-response-v1.0' and saved.get('payload_sha256') == digest(saved.get('response'))


def _evidence(root, base, business_id, request_id, stage, batch_ref, actor, projection, refs):
    value = check({'schema_version': 'native-batch-phase-evidence-v1.0', 'business_id': business_id,
        'batch_intent_ref': batch_ref, 'native_request_id': request_id, 'provider_stage': stage,
        'native_attempt_ref': refs[0], 'native_evidence_refs': refs, 'projection': projection,
        'actor_intent': actor}, 'C06')
    write_once(base / (projection + '.json'), value)


def wrap(context, stage, transport, *, model):
    request = context['request']
    if not request.get('batch_admission_ref'):
        return transport
    root = Path(context['paths']['request']).parents[3]
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    confirmed = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])
    batch_id = confirmed['batch_id']
    original_snapshot = snapshot(root, request)
    index = 0
    parameters = {'model': model, 'stage_owner_sha256': file_sha(Path(__file__).with_name(
        'resolve_generation_content_plan_v1.py' if stage == 'content_plan' else 'resolve_generation_batch_v1.py'))}
    if stage == 'script_generation':
        import generation_recovery_v1 as recovery
        pending = recovery.graph(Path(root), request['request_id'])['pending']
        if pending:
            recovery.verify_authorization(pending)
            if str(pending['actor']['user_id']) != admission['actor_intent']['actor_id']:
                raise BatchError('CREATION_BATCH_ACTOR_CONFLICT', 'Native retry belongs to another Batch actor')
            parameters['native_recovery_ref'] = recovery.ref(root,
                recovery.operation_root(root, request['request_id'], pending['operation_id'])/'intent.json')

    def call(prompt):
        nonlocal index
        index += 1
        batch.current_context(root, batch_id)  # Current Session/grant, stable original principal.
        batch.policy_qualification(root)
        return _cached_call(root, batch_id, request['request_id'], request['persona_id'], stage, index,
            original_snapshot, admission['actor_intent'], admission['batch_intent_ref'], transport, prompt,
            lambda: snapshot(root, request), parameters=parameters)
    return call


def dispatch_count(root, request, stage):
    if not request.get('batch_admission_ref'):
        return 0
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    batch_id = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])['batch_id']
    return len(list(phase_directory(root, batch_id, request['request_id'], stage).rglob('dispatch.json')))


def assert_current(root, request, stage):
    if not request.get('batch_admission_ref'):
        return
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    batch_id = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])['batch_id']
    batch.current_context(root, batch_id)
    batch.policy_qualification(root)
    from content_intent_reservations_v1 import assert_executable
    assert_executable(root, request['persona_id'], request['request_id'])
    for path in phase_directory(root, batch_id, request['request_id'], stage).rglob('intent.json'):
        if read(path)['source_snapshot'] != snapshot(root, request):
            raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Native publication cannot rebind the original generation source/memory')


@contextmanager
def publication_fence(root, request, stage):
    """Local Native publication only; never held by the external transport."""
    if not request.get('batch_admission_ref'):
        yield
        return
    from novel_news_generation_recovery_v1 import mutation_fence
    from generation_request_handoff_v1 import _business_generation_lock
    with mutation_fence(root), _business_generation_lock(root, request['persona_id']):
        assert_current(root, request, stage)
        yield


def phase_state(root, request):
    """Integrity-checked provider evidence, never a generated/approved verdict."""
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    confirmed = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])
    return read_phase_evidence(root, request, admission, confirmed)


def read_phase_evidence(root, request, admission, confirmed):
    """Original C06 reader, reusable without entering the C05 event reader.

    Its C05 settlement caller supplies already pinned canonical admission and
    Batch sources; public phase_state still performs full Native admission.
    """
    result = {'dispatches': 0, 'responses': 0, 'unknown': False, 'stages': {}}
    for stage in ('content_plan', 'script_generation'):
        value = {'dispatches': 0, 'responses': 0}
        for path in phase_directory(root, confirmed['batch_id'], request['request_id'], stage).rglob('intent.json'):
            intent = read(path)
            if (intent.get('schema_version') != 'native-batch-provider-intent-v1.0'
                    or intent.get('request_id') != request['request_id'] or intent.get('batch_id') != confirmed['batch_id']
                    or intent.get('stage') != stage or intent.get('actor_intent') != admission['actor_intent']
                    or intent.get('source_snapshot', {}).get('request_sha256') != file_sha(Path(root) / 'data/generation_requests' / request['request_id'] / 'generation_request_v1.json')):
                raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Provider evidence belongs to another Native operation')
            reference = artifact(path, 'native-provider-stage', request['request_id'], intent['schema_version'])
            dispatch = path.with_name('dispatch.json')
            response = path.with_name('response.json')
            if io_path(dispatch).is_file():
                if read(dispatch) != {'schema_version': 'native-batch-provider-dispatch-v1.0', 'intent_ref': reference}:
                    raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Provider dispatch differs from its original intent')
                value['dispatches'] += 1
            if io_path(response).is_file():
                saved = read(response)
                if (not io_path(dispatch).is_file() or saved.get('intent_ref') != reference or not valid_response(saved)):
                    raise BatchError('CREATION_BATCH_RESPONSE_INVALID', 'Saved provider response does not bind this dispatch')
                value['responses'] += 1
        result['stages'][stage] = value
        result['dispatches'] += value['dispatches']
        result['responses'] += value['responses']
    result['unknown'] = result['dispatches'] > result['responses']
    return result


def validated_local_outcome(root, request):
    """Read original Native results; a received response alone proves no output.

    Zero quality capacity and accepted/rejected subsets are local, known
    outcomes. They permit other legal groups, never automatic refill/retry.
    """
    evidence = phase_state(root, request)
    if evidence['unknown']:
        return None
    import generation_recovery_v1 as recovery
    graph = recovery.graph(Path(root), request['request_id'])
    if graph['pending'] or (graph['result'] or {}).get('outcome') in ('outcome_unknown', 'blocked'):
        return None
    source_plan = Path(root)/'data/production_plans'/request['request_id']/'generation_source_plan_v1.json'
    if not io_path(source_plan).is_file():
        if evidence['dispatches'] or io_path(graph['batch']).is_file():
            raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'An executed Native phase lost its original source plan')
        return None  # Admission may legally precede local Source Plan creation.
    for stage in ('script_generation', 'content_plan'):
        recorded = read_native_result(root, request, stage)
        if recorded is not None:
            return recorded
    import resolve_generation_batch_v1 as owner
    try:
        inputs = owner.generation_inputs(Path(root), request['request_id'])
    except owner.GenerationBatchResolutionError as exc:
        if exc.code == 'FINAL_CONTENT_PLAN_EMPTY' and evidence['stages']['content_plan']['responses']:
            return {'kind':'quality_capacity_zero', 'generated_count':0, 'review_ready':False}
        if exc.code == 'FINAL_CONTENT_PLAN_REQUIRED':
            return None
        raise
    path = graph['batch']
    if not io_path(path).is_file() or not evidence['stages']['script_generation']['responses']:
        return None
    value = read(path)
    owner.validate_existing_batch(batch=value, batch_path=path, request=request,
        final_plan_path=inputs['final_plan_path'], final_plan=inputs['final_plan'],
        projection=inputs['projection'], closure_memory=inputs['closure_memory'])
    if value.get('status') not in ('review_required', 'generation_incomplete'):
        return None
    count = len(value.get('contents') or [])
    return {'kind':'generated' if value['status']=='review_required' else 'partial_generated' if count else 'generation_rejected',
            'generated_count':count, 'review_ready':recovery.ready_for_review(value, inputs['selected_concept_ids'])}


def record_native_result(root, request, stage, path):
    """C06 projection of a result JUST validated/published by its Native owner.

    No generated text or approval is copied here. The canonical Native file and
    graph remain the result truth; this records that local processing finished
    before another legal closure later changes planning memory.
    Caller holds publication_fence, so there is no nested mutation lock.
    """
    if not request.get('batch_admission_ref'):
        return
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    confirmed = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])
    phase = effective_phase(root, request, stage)
    intents = sorted(phase.glob('*/intent.json'))
    if not intents:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native batch result lacks its provider intent')
    intent_path = intents[-1]
    response_path = intent_path.with_name('response.json')
    if not io_path(response_path).is_file():
        raise BatchError('CREATION_BATCH_OUTCOME_UNKNOWN', 'A Native result cannot hide a missing provider response')
    value = read(path)
    count = len((value.get('selected_concepts') if stage == 'content_plan' else value.get('contents')) or [])
    refs = [artifact(intent_path, 'native-provider-stage', request['request_id'], read(intent_path)['schema_version']),
            artifact(response_path, 'native-provider-stage', request['request_id'], read(response_path)['schema_version']),
            artifact(path, 'native-content-plan' if stage == 'content_plan' else 'native-generation-result',
                     request['request_id'], value['schema_version'])]
    _evidence(root, phase / 'native_result', request['persona_id'], request['request_id'], stage,
              admission['batch_intent_ref'], admission['actor_intent'], 'generated' if count else 'explicit_failure', refs)


def read_native_result(root, request, stage):
    admission = batch.validate_admission(request['batch_admission_ref'], root=root, request=request)
    confirmed = __import__('creative_style_v1').pinned(admission['batch_intent_ref'])
    phase = effective_phase(root, request, stage)
    paths = list((phase / 'native_result').glob('*.json'))
    if not paths:
        return None
    if len(paths) != 1:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native result projection has conflicting records')
    value = check(read(paths[0]), 'C06')
    if (value['business_id'] != request['persona_id'] or value['native_request_id'] != request['request_id']
            or value['batch_intent_ref'] != admission['batch_intent_ref'] or value['actor_intent'] != admission['actor_intent']
            or value['provider_stage'] != stage or value['projection'] not in ('generated', 'explicit_failure')):
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native result projection belongs to another operation')
    pinned = __import__('creative_style_v1').pinned
    for reference in value['native_evidence_refs']:
        pinned(reference)
    owner = 'native-content-plan' if stage == 'content_plan' else 'native-generation-result'
    references = [r for r in value['native_evidence_refs'] if r['owner'] == owner]
    if len(references) != 1:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native result reference is missing')
    expected = (Path(root) / 'data/content_plans' / request['request_id'] / 'content_plan_v1_1_1.json'
                if stage == 'content_plan' else __import__('generation_recovery_v1').graph(Path(root), request['request_id'])['batch'])
    if Path(references[0]['path']).resolve() != expected.resolve():
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native result is not the effective original owner path')
    intents = sorted(phase.glob('*/intent.json'))
    if not intents:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native result lacks its actual provider intent')
    intent = intents[-1]
    response = intent.with_name('response.json')
    original_refs = [artifact(intent, 'native-provider-stage', request['request_id'], read(intent)['schema_version']),
                     artifact(response, 'native-provider-stage', request['request_id'], read(response)['schema_version']),
                     references[0]]
    if value['native_attempt_ref'] != original_refs[0] or value['native_evidence_refs'] != original_refs:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native projection differs from its exact provider/result references')
    result = pinned(references[0])
    schema = 'content-plan-v1.1.1' if stage == 'content_plan' else __import__('generate_mix_scripts_v1').SCHEMA_VERSION
    if result.get('request_id') != request['request_id'] or result.get('schema_version') != schema:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Native result Request identity changed')
    count = len((result.get('selected_concepts') if stage == 'content_plan' else result.get('contents')) or [])
    if value['projection'] != ('generated' if count else 'explicit_failure'):
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Projection disagrees with original Native result')
    if stage == 'content_plan':
        return {'kind':'quality_capacity_zero', 'generated_count':0, 'review_ready':False} if not count else None
    from creative_style_v1 import validate_batch
    validate_batch(result)
    if result.get('status') not in ('review_required', 'generation_incomplete') or result.get('generated_count') != count:
        raise BatchError('CREATION_BATCH_PHASE_INVALID', 'Original generation result shape changed')
    return {'kind':'generated' if result.get('status') == 'review_required' else 'partial_generated' if count else 'generation_rejected',
            'generated_count':count, 'review_ready':False}  # Human readiness ALWAYS comes from the original live reader.
