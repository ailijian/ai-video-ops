"""Read-only adapters to the three existing Native approval owners."""
from pathlib import Path
from contextlib import contextmanager

from profile_compatibility_decisions_v1_1 import read, file_sha, ref, digest
from publish_copy_contract_v1 import identifier, PublishCopyError

def source(root, request_id):
    root = Path(root).resolve(); identifier(request_id)
    if request_id.startswith('news_'):
        import news_delivery_v1 as owner
        request_path, request = owner._load_request(root, request_id)
        directory = owner._request_root(root, request_id)
        approved_path = owner._approved_path(root, request_id)
        review_path = owner._review_path(root, request_id)
        plan_path = directory / 'news_delivery_plan_v1.json'
        business_path, business = owner._latest_approved_persona(root, request['business_id'], 'business')
        speaker_path, speaker = owner._latest_approved_persona(root, request['speaker_id'], 'speaker')
        owner._verify_speaker_business_lineage(business_path, business, speaker)
        if any(request['lineage'][key]['sha256'] != file_sha(path) for key, path in (
                ('business_persona', business_path), ('speaker_persona', speaker_path))):
            raise PublishCopyError('SOURCE_CHANGED')
        from news_export_recovery_v1 import source_snapshot, verify_native_human_bundle, bound_source_paths
        verify_native_human_bundle(root, request=request_path, plan=plan_path, review=review_path,
                                   approved=approved_path, kind='repurpose')
        _, ledger = owner._ledger(root, request['business_id'])
        entry = owner._source_entry(ledger, request['source_content_id'])
        if digest(entry) != request['source_content']['canonical_sha256']:
            raise PublishCopyError('SOURCE_CHANGED')
        binding = request.get('profile_compatibility_v1_2')
        snapshot = source_snapshot(root, request=request_path, plan=plan_path, review=review_path,
            approved=approved_path, business=business_path, speaker=speaker_path,
            structural=bound_source_paths(root, request.get('lineage', {})), semantic_source=entry,
            binding=binding, consumer='news_repurpose')
        approved = read(approved_path)
        units = [{'unit_id': item['slot_id'], 'text': item['approved_text'], 'order': index,
                  'fragment_sha256': digest(item)} for index, item in enumerate(approved['approved_slots'], 1)]
        mode = 'cross_profile_repurpose'; business_id = request['business_id']
        items = [{'target_id': request_id + '-P001', 'target_kind': 'news_repurpose_presentation', 'units': units}]
        receipt = directory / 'news_dynamic_excel_export_receipt_v1.json'
        closure = directory / 'news_delivery_export_closure_v1.json'
    else:
        request_path = root / 'data/generation_requests' / request_id / 'generation_request_v1.json'
        request = read(request_path); business_id = request['persona_id']
        directory = root / 'data/generation_batches' / request_id
        if request.get('target_profile') == 'news':
            import novel_news_v1 as owner
            context = owner._source_context(root, request_id); paths = context['paths']
            approved_path = paths['approved']; approved = read(approved_path)
            from news_export_recovery_v1 import source_snapshot, verify_native_human_bundle, bound_source_paths
            verify_native_human_bundle(root, request=request_path, plan=paths['plan'], review=paths['review'],
                                       approved=approved_path, kind='novel')
            from novel_news_generation_recovery_v1 import snapshot as generation_snapshot
            generation_snapshot(root, context)
            binding = request.get('profile_compatibility_v1_2')
            business_path = Path(request['lineage']['business_persona_ref']['path'])
            speaker_path = Path(request['lineage']['speaker_persona_ref']['path'])
            snapshot = source_snapshot(root, request=request_path, plan=paths['plan'], review=paths['review'],
                approved=approved_path, business=business_path, speaker=speaker_path,
                structural=bound_source_paths(root, context['source_plan']), binding=binding, consumer='novel_news')
            units = [{'unit_id': item['beat_id'], 'text': item['text'], 'order': index,
                      'fragment_sha256': digest(item)} for index, item in enumerate(approved['micro_information_beats'], 1)]
            items = [{'target_id': request_id + '-N001', 'target_kind': 'novel_news_content', 'units': units}]; mode = 'novel_content'
            business = context['persona']; receipt = paths['receipt']; closure = paths['closure']
        else:
            from delivery_receipt_recovery_v1 import human_state, source_snapshot
            state = human_state(directory)
            if not state.get('completed') or not state.get('approved'):
                raise PublishCopyError('APPROVAL_REQUIRED', '请先完成制作文案的人工审核。')
            approved_path = directory / 'approved_generation_batch_v1.json'
            approved = read(approved_path)
            approval_path = directory / 'generation_batch_approval_receipt.json'
            from generation_recovery_v1 import validate_approved_source
            validate_approved_source(root, request_id, approved, read(approval_path))
            batch = read(approval_path)['source_batch']['path']
            batch_path = Path(batch) if Path(batch).is_absolute() else root / batch
            snapshot = source_snapshot(root, batch_path)
            from show_customer_status_v1 import resolve_current_persona
            current = resolve_current_persona(root, business_id, 'business')
            business_path = Path(current['path']); business = read(business_path)
            plan = read(root / snapshot['source_plan_ref']['path'])
            binding = plan.get('profile_compatibility_v1_1')
            mode = 'mix'
            items = [{'target_id': item['content_id'], 'target_kind': 'mix_content', 'title': item['title'],
                      'narration': item['narration'], 'units': []} for item in approved['contents']]
            receipt = directory / 'mix_excel_export_receipt_v1.json'
            closure = directory / 'generation_export_closure_v1.json'
            snapshot['approval_receipt_ref'] = ref(root, approval_path)
    snapshot['approved_ref'] = ref(root, approved_path)
    # No raw intake, private speaker biography or video analysis is exposed.
    from generate_mix_scripts_v1 import safe_persona_projection
    from privacy_projection_v1 import project_value
    safe = project_value(safe_persona_projection(business), 'safe_verbatim')
    result = {'request_id': request_id, 'mode': mode, 'business_id': business_id,
              'snapshot': snapshot, 'items': items, 'approved_sha256': file_sha(approved_path),
              'safe_business': safe, 'binding': binding}
    result['source_sha256'] = digest(result)
    result['refs'] = list(_refs(snapshot))
    result['_directory'] = directory; result['_business_path'] = Path(business_path)
    result['_receipt'] = receipt; result['_closure'] = closure
    return result

def _refs(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}:
            yield value
        else:
            for child in value.values(): yield from _refs(child)
    elif isinstance(value, list):
        for child in value: yield from _refs(child)

@contextmanager
def current_authority(root, value):
    if value['mode'] == 'mix':
        from profile_compatibility_release_v1_1 import CONFIG, runtime_write
        if (Path(root) / CONFIG).is_file():
            with runtime_write(root, pinned=value['binding']): yield
        else: yield
    else:
        from news_export_recovery_v1 import current_authority as native
        with native(root, value['binding']): yield
