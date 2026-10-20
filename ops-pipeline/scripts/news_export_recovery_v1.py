"""NR0: publication safety delegated by the two original Native News writers.

This module writes only intent/prepared evidence. Approval, delivery Receipt,
Closure and Ledger remain owned by novel_news_v1/news_delivery_v1.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from case_console_authorization_v1 import digest
from human_review_operations_v1 import io_path
from operation_lock_v1 import operation_lock
from profile_compatibility_contract_v1_1 import ACTOR, HASH, ID, OPERATION, REF, TEXT, array, obj, validate
from profile_compatibility_decisions_v1_1 import file_sha, read, ref, resolve_ref, write_once

INTENT = 'news-export-intent-v1.0'
PREPARED = 'news-export-prepared-publication-v1.0'
EXPORTER = 'native-dynamic-news-export-v1.1'
NOVEL_RECEIPT = 'novel-news-excel-export-receipt-v1.1'
REPURPOSE_RECEIPT = 'news-dynamic-excel-export-receipt-v1.1'
NOVEL_CLOSURE = 'novel-news-export-closure-v1.1'
REPURPOSE_CLOSURE = 'news-delivery-export-closure-v1.1'
SNAPSHOT = obj({'request_ref': REF, 'plan_ref': REF, 'review_ref': REF, 'approved_ref': REF,
    'business_ref': REF, 'speaker_ref': REF, 'structural_refs': array(REF),
    'authority_binding': {'type': 'object'}, 'restriction_sha256': HASH, 'semantic_source_sha256': HASH})
AUTHORITY = obj({'principal': ACTOR, 'database_identity_sha256': HASH, 'user_state_sha256': HASH})
SCHEMAS = {
    INTENT: obj({'schema_version': {'const': INTENT}, 'operation_id': OPERATION,
        'request_id': ID, 'request_type': {'enum': ['novel_content', 'cross_profile_repurpose']},
        'business_id': ID, 'speaker_id': ID, 'sources': SNAPSHOT, 'template_ref': REF,
        'exporter_version': {'const': EXPORTER}, 'output_path': TEXT, 'titles': array(TEXT, 4),
        'actor': ACTOR, 'authorization': AUTHORITY, 'created_at': TEXT}),
    PREPARED: obj({'schema_version': {'const': PREPARED}, 'operation_id': OPERATION,
        'intent_ref': REF, 'staged_ref': REF, 'output_ref': REF, 'template_ref': REF,
        'sources_sha256': HASH, 'workbook_parts_sha256': HASH}),
}
PREFIX = obj({'semantic_count': {'type':'integer','minimum':0}, 'semantic_sha256': HASH,
              'presentation_count': {'type':'integer','minimum':0}, 'presentation_sha256': HASH})
PUBLICATION = obj({'intent_ref':REF,'prepared_ref':REF})
SCHEMAS.update({
    NOVEL_RECEIPT: obj({'schema_version':{'const':NOVEL_RECEIPT},'request_id':ID,
        'reuse_intent':{'const':'novel_content'},'created_at':TEXT,'output_path':TEXT,'output_sha256':HASH,
        'publication':PUBLICATION,'approved_ref':REF,'validation_passed':{'const':True},'actor':ACTOR}),
    REPURPOSE_RECEIPT: obj({'schema_version':{'const':REPURPOSE_RECEIPT},'publication':PUBLICATION,
        'ledger_prefix':PREFIX,'created_at':TEXT,'request_id':ID,'profile':{'const':'news'},
        'reuse_intent':{'const':'cross_profile_repurpose'},'semantic_novelty':{'const':False},
        'source_content_ref':TEXT,'approved_news_delivery':REF,'template_path':TEXT,'template_sha256':HASH,
        'output_path':TEXT,'output_name':TEXT,'output_sha256':HASH,'exported_row_count':{'const':1},
        'slot_count':{'type':'integer','minimum':4},'headers':array(TEXT,4),'titles':array(TEXT,4),
        'content_ledger':obj({'path':TEXT,'sha256_after':HASH,
            'semantic_entry_count_before':{'type':'integer','minimum':0},
            'semantic_entry_count_after':{'type':'integer','minimum':0},
            'semantic_entries_sha256_before':HASH,'semantic_entries_sha256_after':HASH,
            'presentation_history_entry':{'type':'object'}}),
        'authority':obj({'new_semantic_content_created':{'const':False},
            'communicated_information_units_created':{'const':0},'case_facts_transferred':{'const':False},
            'remote_model_calls':{'const':0}}),'validation_passed':{'const':True}}),
    NOVEL_CLOSURE: obj({'schema_version':{'const':NOVEL_CLOSURE},'request_id':ID,
        'receipt_ref':REF,'ledger_prefix':PREFIX,'content_id':TEXT,'presentation_id':TEXT,
        'semantic_entry_count_delta':{'const':1},'presentation_semantic_entry_count_delta':{'const':0},
        'approved_sha256':HASH,'output_sha256':HASH,'ledger_sha256_after':HASH,
        'validation':obj({'passed':{'const':True},'case_fact_transfer':{'const':False}})}),
    REPURPOSE_CLOSURE: obj({'schema_version':{'const':REPURPOSE_CLOSURE},'receipt_ref':REF,'ledger_prefix':PREFIX,
        'created_at':TEXT,'request_id':ID,'status':{'const':'approved_exported_presentation_history_closed'},
        'request':REF,'approved_news_delivery':REF,
        'excel_export':obj({'path':TEXT,'sha256':HASH,'slot_count':{'type':'integer','minimum':4}}),
        'presentation_history':obj({'presentation_id':TEXT,'content_ledger_sha256_after':HASH,
            'semantic_entry_count_delta':{'const':0},'semantic_entries_changed':{'const':False}}),
        'authority':obj({'semantic_novelty':{'const':False},'new_semantic_content_count_delta':{'const':0},
            'presentation_history_append_only':{'const':True},'remote_model_calls':{'const':0}}),
        'validation':obj({key:{'const':True} for key in ('passed','excel_validation_passed',
            'semantic_entry_count_unchanged','semantic_entries_sha256_unchanged','presentation_history_entry_present')})}),
})


class NewsExportError(RuntimeError):
    def __init__(self, code, message='导出尚未完成，可继续原操作。'):
        self.code = code
        super().__init__(message)


def check(value, version):
    try:
        validate(value, SCHEMAS[version])
        if version == INTENT and not 4 <= len(value['titles']) <= 8:
            raise ValueError('Beat count')
        if version == REPURPOSE_RECEIPT:
            count = len(value['titles'])
            ledger = value['content_ledger']
            if (not 4 <= count <= 8 or value['slot_count'] != count
                or value['headers'] != [f'标题{i}' for i in range(1,count+1)]
                or ledger['semantic_entry_count_before'] != ledger['semantic_entry_count_after']
                or ledger['semantic_entries_sha256_before'] != ledger['semantic_entries_sha256_after']):
                raise ValueError('Receipt business fields')
        return value
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        raise NewsExportError('NEWS_EXPORT_CONTRACT_INVALID', '导出记录需要重新核对。') from exc


def paths(directory):
    return {'intent': Path(directory) / 'news_export_intent_v1.json',
            'prepared': Path(directory) / 'news_export_prepared_publication_v1.json',
            'staged': Path(directory) / 'news_export_staged.xlsx'}


def identity(context, intent=None):
    """Revalidate the existing local Session; persist no Session credential."""
    from generation_recovery_v1 import authorization
    try:
        if set(context) != {'actor', 'authorization'}:
            raise ValueError('Context fields')
        actor, proof = context['actor'], context['authorization']
        current = authorization(proof['database_path'], actor, proof['session_fingerprint'])
        if current != proof:
            raise ValueError('Stale authorization')
        value = {'principal': actor, 'database_identity_sha256': digest(str(Path(proof['database_path']).resolve())),
                 'user_state_sha256': current['user_state_sha256']}
        if intent and (intent['actor'] != actor or intent['authorization'] != value):
            raise ValueError('Original actor or permission state differs')
        return value
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as exc:
        raise NewsExportError('NEWS_EXPORT_AUTHORIZATION_REQUIRED', '导出身份或权限已变化，请重新登录并核对原操作。') from exc


def validate_workbook(output, template, titles):
    """Compare every OOXML member against the trusted native template projection.

    ZIP metadata timestamps are not business content. Prepared SHA binds the
    exact ZIP bytes actually published; no reconstructed file replaces them.
    """
    from news_delivery_v1 import _news_workbook_parts
    try:
        expected = _news_workbook_parts(Path(template), titles)
        with zipfile.ZipFile(io_path(output)) as archive:
            names = archive.namelist()
            if (archive.comment or len(names) != len(set(names)) or set(names) != set(expected)
                    or archive.testzip() is not None):
                raise ValueError('OOXML inventory/CRC')
            offset = 0
            central_size = 0
            for item in archive.infolist():
                # The native ZIP has no preamble, trailing payload, duplicate
                # local members, comments, extras, encryption or descriptors.
                name_bytes = item.filename.encode('utf-8' if item.flag_bits & 0x800 else 'cp437')
                if (item.header_offset != offset or item.extra or item.comment or item.flag_bits & ~0x800
                        or item.file_size != len(expected[item.filename])
                        or item.compress_type != zipfile.ZIP_DEFLATED):
                    raise ValueError('Unapproved ZIP container content')
                offset += 30 + len(name_bytes) + item.compress_size
                central_size += 46 + len(name_bytes)
            if offset != archive.start_dir or Path(output).stat().st_size != offset + central_size + 22:
                raise ValueError('Unapproved hidden ZIP payload')
            if any(archive.read(name) != data for name, data in expected.items()):
                raise ValueError('Unapproved OOXML content')
        return digest({name: hashlib.sha256(data).hexdigest() for name, data in sorted(expected.items())})
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise NewsExportError('NEWS_EXPORT_WORKBOOK_INVALID', '导出文件内容与已审核内容不一致，需要重新核对。') from exc


def source_snapshot(root, *, request, plan, review, approved, business, speaker, structural=(),
                    semantic_source=None, binding=None, consumer):
    """Exact current sources, including live Customer restrictions."""
    from customer_constraints_v1 import assert_production_allowed
    from news_delivery_v1 import _latest_approved_persona
    result = {name + '_ref': ref(root, path) for name, path in (
        ('request', request), ('plan', plan), ('review', review), ('approved', approved),
        ('business', business), ('speaker', speaker))}
    restrictions = []
    for path in (business, speaker):
        persona = read(path)
        restrictions.append(assert_production_allowed(persona, path, consumer=consumer))
        # The native source reader owns approval. Additionally forbid using an
        # older Persona after an approved revision advances during recovery.
        persona_id = persona.get('persona_id')
        parent = Path(root) / 'data/personas' / str(persona_id)
        if any(read(p).get('lifecycle', {}).get('approved') is True for p in parent.glob('revision_*/persona_v1.json')):
            latest, _ = _latest_approved_persona(Path(root), persona_id, persona['persona_scope'])
            if Path(latest).resolve() != Path(path).resolve():
                raise NewsExportError('NEWS_EXPORT_SOURCE_CHANGED', '客户或出镜人资料已更新，请重新核对。')
    result.update(structural_refs=[ref(root, p) for p in sorted(set(map(Path, structural)))],
        authority_binding=binding or {}, restriction_sha256=digest(restrictions),
        semantic_source_sha256=digest(semantic_source))
    return result


@contextmanager
def native_operation(root, business_id):
    from news_qualification_v1_2 import prohibit_write
    prohibit_write(root)
    # Console holds its original backup barrier and Business lock while the
    # child runs. Windows CRT read locks cannot be reacquired by that child.
    # Offline native mutation remains offline-only per RUNBOOK. This finer
    # lock serializes both News owners, without changing the shared lock owner.
    with operation_lock(root, 'news-native-export:' + business_id):
        yield


@contextmanager
def current_authority(root, binding):
    """Use the original live release owner; never treat a Mix-only root as News."""
    from profile_compatibility_release_v1_1 import CONFIG, runtime_write
    if not (Path(root) / CONFIG).is_file():
        if binding:
            raise NewsExportError('NEWS_EXPORT_AUTHORITY_UNAVAILABLE', '当前创作参考版本尚未激活。')
        yield
        return
    # v1.2 is added by the separately approved NC0 implementation. Until that
    # reader exists, unknown schemas stay closed rather than downgrade to v1.1.
    from profile_compatibility_contract_v1_1 import CompatibilityError
    try:
        from news_qualification_v1_2 import read_context
        historical=read_context(root)
        if historical:
            if binding!=historical['binding']:
                raise NewsExportError('NEWS_EXPORT_AUTHORITY_CHANGED')
            yield
            return
        from news_runtime_v1_2 import configured
        typed_news = configured(root)
        if typed_news and not binding:
            raise NewsExportError('NEWS_EXPORT_AUTHORITY_UNAVAILABLE','请先核对当前新闻体创作资格。')
        with runtime_write(root, pinned=binding) as active:
            if typed_news:
                from profile_compatibility_contract_v1_2 import BINDING, validate_contract
                from profile_compatibility_release_v1_2 import binding as exact_news_binding
                validate_contract(binding, BINDING)
                if binding != exact_news_binding(active, binding['reuse_intent']):
                    raise NewsExportError('NEWS_EXPORT_AUTHORITY_CHANGED')
            if 'news' not in active['manifest']['profiles']:
                raise NewsExportError('NEWS_EXPORT_NEWS_COMPATIBILITY_REQUIRED', '当前发布版本未批准新闻体创作。')
            yield
    except CompatibilityError as exc:
        raise NewsExportError('NEWS_EXPORT_AUTHORITY_CHANGED', '创作参考的批准或发布状态已变化，需要重新核对。') from exc


def prepare_publication(root, directory, *, request_id, request_type, business_id, speaker_id,
                        sources, template, output, titles, context, renderer):
    """Resume only exact immutable intent/prepared evidence; never adopt an orphan."""
    root, output, template = Path(root).resolve(), Path(output).resolve(), Path(template).resolve()
    p = paths(directory)
    try:
        output_relative = output.relative_to(root / 'output').as_posix()
        if not output_relative or output.is_symlink() or template.is_symlink():
            raise ValueError('Output identity')
    except ValueError as exc:
        raise NewsExportError('NEWS_EXPORT_PATH_INVALID') from exc
    if output.exists() and (not p['intent'].is_file() or not p['prepared'].is_file()):
        raise NewsExportError('NEWS_EXPORT_LEGACY_UNBOUND_ORPHAN', '导出结果需要重新核对。')
    old = check(read(p['intent']), INTENT) if p['intent'].is_file() else None
    authorization = identity(context, old)
    value = {'schema_version': INTENT, 'operation_id': old['operation_id'] if old else uuid.uuid4().hex,
        'request_id': request_id, 'request_type': request_type, 'business_id': business_id,
        'speaker_id': speaker_id, 'sources': sources, 'template_ref': ref(root, template),
        'exporter_version': EXPORTER, 'output_path': 'output/' + output_relative, 'titles': titles,
        'actor': context['actor'], 'authorization': authorization,
        'created_at': old['created_at'] if old else datetime.now(timezone.utc).isoformat()}
    check(value, INTENT)
    if old and old != value:
        raise NewsExportError('NEWS_EXPORT_INTENT_CONFLICT', '原导出来源或参数已变化，需要重新核对。')
    write_once(p['intent'], value)
    if not p['prepared'].is_file():
        if not p['staged'].is_file():
            # A crash during rendering retains its unique partial temporary file.
            # A retry may prepare the missing complete stage; no file is replaced.
            temporary = Path(directory) / ('news-export-' + uuid.uuid4().hex + '.tmp.xlsx')
            renderer(template_path=template, output_path=temporary, titles=titles)
            validate_workbook(temporary, template, titles)
            with io_path(temporary).open('r+b') as handle:
                os.fsync(handle.fileno())
            os.link(io_path(temporary), io_path(p['staged']))
        parts_sha = validate_workbook(p['staged'], template, titles)
        prepared = {'schema_version': PREPARED, 'operation_id': value['operation_id'],
            'intent_ref': ref(root, p['intent']), 'staged_ref': ref(root, p['staged']),
            'output_ref': {'path': value['output_path'], 'sha256': file_sha(p['staged'])},
            'template_ref': value['template_ref'], 'sources_sha256': digest(sources),
            'workbook_parts_sha256': parts_sha}
        write_once(p['prepared'], check(prepared, PREPARED))
    validate_prepared(root, directory, output=output, template=template, titles=titles, sources=sources)
    if not output.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Atomic no-clobber publication on Windows/NTFS and POSIX. Never
            # os.replace an existing destination. Stage and output share bytes.
            os.link(io_path(p['staged']), io_path(output))
        except FileExistsError:
            pass  # The strict prepared-byte check below handles the race.
    prepared = validate_prepared(root, directory, output=output, template=template, titles=titles, sources=sources,
                                 published=True)
    return value, prepared


def validate_prepared(root, directory, **kwargs):
    try:
        return _validate_prepared(root,directory,**kwargs)
    except NewsExportError:
        raise
    except (RuntimeError,ValueError,KeyError,TypeError,OSError) as exc:
        raise NewsExportError('NEWS_EXPORT_PUBLICATION_CONFLICT','导出结果需要重新核对。') from exc


def _validate_prepared(root, directory, *, output, template, titles, sources=None, published=False):
    p = paths(directory)
    intent = check(read(p['intent']), INTENT)
    prepared = check(read(p['prepared']), PREPARED)
    if (prepared['intent_ref'] != ref(root, p['intent']) or prepared['operation_id'] != intent['operation_id']
            or prepared['template_ref'] != intent['template_ref'] or ref(root, template) != intent['template_ref']
            or prepared['sources_sha256'] != digest(intent['sources']) or intent['titles'] != titles
            or prepared['output_ref']['path'] != intent['output_path']
            or Path(root) / intent['output_path'] != Path(output)
            or (sources is not None and sources != intent['sources'])):
        raise NewsExportError('NEWS_EXPORT_PUBLICATION_CONFLICT')
    for source in intent['sources'].values():
        if isinstance(source, dict) and set(source) == {'path', 'sha256'}:
            resolve_ref(root, source)
    for source in intent['sources']['structural_refs']:
        resolve_ref(root, source)
    stage = resolve_ref(root, prepared['staged_ref'])
    if (prepared['output_ref']['sha256'] != file_sha(stage)
            or validate_workbook(stage, template, titles) != prepared['workbook_parts_sha256']):
        raise NewsExportError('NEWS_EXPORT_PUBLICATION_CONFLICT')
    if Path(output).exists() or published:
        try:
            if ref(root, output) != prepared['output_ref']:
                raise ValueError('Published SHA mismatch')
            validate_workbook(output, template, titles)
        except (RuntimeError, ValueError, OSError) as exc:
            raise NewsExportError('NEWS_EXPORT_OUTPUT_CONFLICT', '原导出文件已变化，已保留现场，请重新核对。') from exc
    return prepared


def ledger_prefix(ledger):
    entries = ledger.get('entries') or []
    presentations = ledger.get('extensions', {}).get('presentation_history_v1', {}).get('entries') or []
    return {'semantic_count': len(entries), 'semantic_sha256': digest(entries),
            'presentation_count': len(presentations), 'presentation_sha256': digest(presentations)}


def validate_ledger_prefix(ledger, prefix):
    entries = ledger.get('entries') or []
    presentations = ledger.get('extensions', {}).get('presentation_history_v1', {}).get('entries') or []
    from news_delivery_v1 import validate_presentation_history_chain
    validate_presentation_history_chain(presentations)
    if (len(entries) < prefix['semantic_count'] or len(presentations) < prefix['presentation_count']
            or digest(entries[:prefix['semantic_count']]) != prefix['semantic_sha256']
            or digest(presentations[:prefix['presentation_count']]) != prefix['presentation_sha256']):
        raise NewsExportError('NEWS_EXPORT_LEDGER_HISTORY_CONFLICT', '原交付的内容历史已变化，需要重新核对。')


def bound_source_paths(root, value):
    """Read only declared immutable native refs; Ledger has event identity instead."""
    result = set()
    if isinstance(value, dict):
        if value.get('path') and (value.get('sha256') or value.get('file_sha256')):
            path = Path(value['path'])
            if not path.is_absolute():
                path = Path(root) / path
            if 'content_ledgers' not in path.parts:
                expected = value.get('sha256') or value.get('file_sha256')
                if file_sha(path) != expected:
                    raise NewsExportError('NEWS_EXPORT_SOURCE_CHANGED', '原导出来源已变化，需要重新核对。')
                result.add(path.resolve())
        for item in value.values():
            result.update(bound_source_paths(root, item))
    elif isinstance(value, list):
        for item in value:
            result.update(bound_source_paths(root, item))
    return result


def receipt_publication(root, directory):
    p = paths(directory)
    return {'intent_ref': ref(root, p['intent']), 'prepared_ref': ref(root, p['prepared'])}


def ledger_intent(root, reference, *, business_id, request_id, titles, approved_sha256, output_sha256):
    """Evidence admission for the original Ledger owner's exact missing step."""
    path = resolve_ref(root, reference)
    intent = check(read(path), INTENT)
    prepared = check(read(paths(path.parent)['prepared']), PREPARED)
    if (intent['business_id'] != business_id or intent['request_id'] != request_id
        or intent['titles'] != titles or intent['sources']['approved_ref']['sha256'] != approved_sha256
        or prepared['output_ref']['sha256'] != output_sha256 or prepared['intent_ref'] != reference):
        raise NewsExportError('NEWS_EXPORT_LEDGER_INTENT_CONFLICT')
    validate_prepared(root,path.parent,output=Path(root)/intent['output_path'],
        template=resolve_ref(root,intent['template_ref']),titles=titles,published=True)
    return intent


def verify_native_human_bundle(root, *, request, plan, approved, review, kind):
    """Read the original Human decision, never infer approval from a filename."""
    p, a, r = read(plan), read(approved), read(review)
    if kind == 'novel':
        from novel_news_v1 import _normalize_beats, _source_context
        context = _source_context(root, read(request)['request_id'])
        original = p['micro_information_beats']
        decisions = r.get('decisions') or []
        by_id = {item.get('beat_id'): item for item in decisions}
        if (len(decisions) != len(original) or len(by_id) != len(original)
                or set(by_id) != {b['beat_id'] for b in original}
                or r.get('reviewed_by') != a.get('reviewed_by') or r.get('reviewed_at') != a.get('reviewed_at')
                or a.get('plan_sha256') != file_sha(plan)):
            raise NewsExportError('NEWS_EXPORT_HUMAN_LINEAGE_INVALID')
        beats=[]
        for beat in original:
            decision=by_id[beat['beat_id']]
            if decision.get('decision') not in {'approved','revised','rejected'}:
                raise NewsExportError('NEWS_EXPORT_HUMAN_LINEAGE_INVALID')
            if decision['decision']=='rejected': continue
            projected=dict(beat)
            if decision['decision']=='revised': projected['text']=str(decision.get('revised_text') or '').strip()
            beats.append(projected)
        if _normalize_beats(beats,context) != a.get('micro_information_beats'):
            raise NewsExportError('NEWS_EXPORT_HUMAN_LINEAGE_INVALID')
    else:
        from news_delivery_v1 import approve_news_delivery
        approve_news_delivery(pipeline_root=Path(root), request_id=read(request)['request_id'],
            review_path=Path(review), verify_only=True)
        if (a.get('human_review',{}).get('review_sha256') != file_sha(review)
                or a.get('lineage',{}).get('plan_sha256') != file_sha(plan)
                or p.get('request_sha256') != file_sha(request)):
            raise NewsExportError('NEWS_EXPORT_HUMAN_LINEAGE_INVALID')


def validate_receipt_publication(root, directory, receipt, *, output, template, titles):
    check(receipt, receipt.get('schema_version'))
    p = paths(directory)
    if receipt.get('publication') != receipt_publication(root, directory):
        raise NewsExportError('NEWS_EXPORT_RECEIPT_CONFLICT')
    intent = check(read(p['intent']), INTENT)
    with current_authority(root, intent['sources']['authority_binding']):
        validate_prepared(root, directory, output=output, template=template, titles=titles, published=True)
    if (receipt.get('output_sha256') != file_sha(output)
            or receipt.get('created_at') != intent['created_at']
            or ('actor' in receipt and receipt['actor'] != intent['actor'])):
        raise NewsExportError('NEWS_EXPORT_RECEIPT_CONFLICT')
    return intent


def partial_state(root, directory, *, output, receipt, closure):
    """Structural state only. Owners must validate Receipt/Closure before complete."""
    p = paths(directory)
    if Path(closure).is_file():
        return 'completion_requires_validation'
    if Path(output).exists() and not all(p[k].is_file() for k in ('intent','prepared')):
        return 'legacy_unbound_orphan'
    if Path(receipt).is_file():
        return 'receipt_complete_closure_pending'
    if Path(output).exists():
        return 'published_receipt_pending' if all(p[k].is_file() for k in ('intent','prepared')) else 'legacy_unbound_orphan'
    if p['prepared'].is_file():
        return 'prepared_unpublished'
    return 'xlsx_not_generated'
