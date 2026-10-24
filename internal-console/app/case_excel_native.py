"""Case Intake delegation: exact private row -> original Native Task.

Import save remains inert. Companions record intent/association, never analysis,
approval, type, evidence or publication authority. Only Task owns dispatch.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import ExitStack,nullcontext
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from fastapi import HTTPException
from human_review_operations_v1 import digest, file_sha, read, write_once, io_path
from case_source_upload_v1 import read_upload
from . import case_excel_import as imports
from .case_library_access import principal, owns_task, record_submission, submission_path
from .database import connect, transaction
from .douyin_source_input import resolve_douyin_source_input, SourceInputError
from .operation_lock import authority_mutation_barrier, operation_lock, scoped_lock_key, OperationLockTimeout
from .task_service import create_case_task, get_task, find_active_case_task, iso_utc, TaskSubmissionError


@lru_cache(maxsize=1)
def schema():
    value = json.loads(Path(__file__).with_name('case_excel_native_schemas.json').read_text('utf-8'))
    Draft202012Validator.check_schema(value)
    return value


def checked(value, name):
    validator = Draft202012Validator({**schema(), '$ref': '#/$defs/'+name})
    if not validator.is_valid(value):
        raise imports.ImportError('EXCEL_NATIVE_CONTRACT_INVALID',422)
    return value


def checkpoint(point):
    """Failure-injection seam; no production fallback."""


def ref(settings, path):
    return {'path':io_path(path).relative_to(io_path(settings.pipeline_root)).as_posix(), 'sha256':file_sha(path)}


def path_for(settings, actor, batch, row, operation):
    for value in (batch,row,operation):
        if not re.fullmatch(r'[a-z][a-z0-9_-]{1,127}',value):
            raise imports.ImportError('IMPORT_NOT_FOUND',404)
    return imports._batch_dir(settings,actor['user_id'],batch)/'native_submissions'/operation


def read_ref(settings, value):
    checked(value,'SourceRef')
    base=settings.pipeline_root.resolve();path=base/value['path']
    if not path.resolve().is_relative_to(base) or any(p.is_symlink() for p in [path,*path.parents] if p.is_relative_to(base)):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    if file_sha(path)!=value['sha256']:
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    return read(path)


def row_bundle(settings, session, batch, row, operation):
    record=imports.detail(settings,session,batch)
    rows=[r for r in record['rows'] if r['row_id']==row]
    operations=[v for v in record['operations'] if v['intent']['operation_id']==operation]
    if len(rows)!=1 or len(operations)!=1:
        raise imports.ImportError('IMPORT_NOT_FOUND',404)
    source=operations[0];result=source['result']
    matches=[r for r in (result or {}).get('row_results',[]) if r['row_id']==row]
    if len(matches)!=1 or matches[0]['state'] not in {'saved_unverified','pending_source','already_recorded_private'}:
        raise imports.ImportError('EXCEL_NATIVE_SAVE_NOT_COMPLETE')
    candidate=rows[0]
    if matches[0]['candidate_ref_sha256']!=imports.record_sha(candidate):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    origin={'batch_id':batch,'batch_sha256':record['batch_sha256'],'row_id':row,
        'row_sha256':imports.record_sha(candidate),'import_operation_id':operation,
        'import_intent_sha256':source['intent_sha256'],'workbook_sha256':record['batch']['file_sha256'],
        'import_result_sha256':imports.record_sha(result)}
    binding=next(v for v in source['intent']['row_source_bindings'] if v['row_id']==row)
    return record,candidate,checked(origin,'ImportOrigin'),binding


def source_snapshot(settings, session, row, binding, upload_id):
    source=resolve_douyin_source_input(row['raw_case']['source_url'])
    bound=binding['native_upload_ref']
    if upload_id != (bound or {}).get('upload_id'):
        raise imports.ImportError('EXCEL_NATIVE_UPLOAD_BINDING_CHANGED')
    active=find_active_case_task(settings.database_path,source.video_id)
    upload=None;media=None
    if upload_id:
        if active and owns_task(settings,session.user['id'],active):
            upload=active['payload'].get('source_upload')
            if upload!=bound:raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
        else:
            from .case_uploads import validate_for_submission
            upload=validate_for_submission(settings,upload_id,source.canonical_url,session.user['id'])
        receipt,_=read_upload(settings.pipeline_root,upload_id,source_url=source.canonical_url,
            user_id=session.user['id'],receipt_sha256=upload['receipt_sha256'])
        media=receipt['source_video_sha256']
    provider=settings.case_acquisition_provider
    if not upload_id and (provider=='upload_only' or (provider=='qiyun' and not (os.environ.get('QYAPI_APP_ID') and os.environ.get('QYAPI_APP_KEY')))):
        raise imports.ImportError('EXCEL_NATIVE_MEDIA_REQUIRED',422)
    return checked({'canonical_url':source.canonical_url,'case_id':source.video_id,'acquisition_provider':provider,
        'source_upload_id':upload_id,'upload_receipt_sha256':upload['receipt_sha256'] if upload else None,
        'media_sha256':media,'provider_source_url':source.extracted_url.split('?',1)[0].split('#',1)[0] if source.extracted_url.startswith('https://v.douyin.com/') else None},'NativeSourceSnapshot')


def preview(settings, session, batch, row, payload):
    checked(payload,'NativePrepareInput')
    if payload['batch_id']!=batch or payload['row_id']!=row:
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    record,candidate,origin,binding=row_bundle(settings,session,batch,row,payload['import_operation_id'])
    if (payload['expected_row_sha256']!=origin['row_sha256'] or payload['expected_import_intent_sha256']!=origin['import_intent_sha256']
            or payload['expected_import_head_sha256']!=record['head_sha256']):
        raise imports.ImportError('IMPORT_HEAD_CHANGED')
    blockers=[];source=None
    if payload['action']!='analyze_new':
        blockers.append('EXCEL_NATIVE_USE_ORIGINAL_REANALYSIS_GATE')
    try:
        source=source_snapshot(settings,session,candidate,binding,payload['source_upload_id'])
    except SourceInputError:
        blockers.append('EXCEL_NATIVE_SUPPORTED_SOURCE_REQUIRED')
    except imports.ImportError as exc:
        blockers.append(exc.code)
    except HTTPException:
        blockers.append('EXCEL_NATIVE_MEDIA_REQUIRED')
    # Native source validation failures must never be interpreted as media approval.
    with imports._authorized(settings,session):
        result={'schema_version':'case-excel-native-preview-v1.0-proposal','principal':principal(settings,session.user['id']),
            'origin':origin,'current_import_head_sha256':record['head_sha256'],'source':source,'can_submit':not blockers,
            'blocker_codes':blockers,'case_approved':False,'shared_published':False}
        result['preflight_sha256']=digest(result)
        return checked(result,'NativePreview')


def mapping(settings, actor, operation, db=None):
    own=db is None;db=db or connect(settings.database_path)
    try:
        r=db.execute('SELECT * FROM case_excel_native_admissions_v1 WHERE namespace=? AND user_id=? AND operation_id=?',
            (actor['namespace'],actor['user_id'],operation)).fetchone()
        return dict(r) if r else None
    finally:
        if own:db.close()


def association(settings, directory, intent, admitted):
    task=get_task(settings.database_path,admitted['task_id']) if admitted else None
    if task and not owns_task(settings,intent['principal']['user_id'],task):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    if task:
        record_submission(settings,intent['principal']['user_id'],task=task)
    checkpoint('submission_receipt')
    result={'schema_version':'case-excel-native-submission-v1.0-proposal','principal':intent['principal'],
        'submission_operation_id':intent['input']['submission_operation_id'],'origin':intent['input']['origin'],
        'input_digest':intent['input_sha256'],'intent_sha256':file_sha(directory/'intent.json'),'parent_sha256':None,
        'state':'admitted' if admitted and admitted['relation_kind']=='new_origin_task' else 'linked_owned_task' if admitted else 'duplicate_private_recorded',
        'task_id':task['task_id'] if task else None,'native_input_sha256':digest(task['payload']) if task else None,
        'case_approved':False,'shared_published':False,'relation_kind':admitted['relation_kind'] if admitted else 'none'}
    checked(result,'NativeSubmissionRecord');write_once(directory/'association.json',result)
    checkpoint('association')
    return result


def submit(settings, session, batch, row, payload, schedule, *, _barrier_held=False):
    checked(payload,'NativeSubmissionInput')
    actor=principal(settings,session.user['id']);origin=payload['origin']
    if origin['batch_id']!=batch or origin['row_id']!=row or payload['expected_submission_parent_sha256'] is not None:
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    directory=path_for(settings,actor,batch,row,payload['submission_operation_id'])
    with (nullcontext() if _barrier_held else authority_mutation_barrier(settings)), operation_lock(settings.pipeline_root,'excel-native:'+digest([actor,payload['submission_operation_id']])):
        for previous_intent in imports._path(settings,actor['user_id']).glob('*/native_submissions/'+payload['submission_operation_id']+'/intent.json'):
            prior_intent=checked(read(previous_intent),'NativeSubmissionIntent')
            if prior_intent['input']!=payload or prior_intent['principal']!=actor:
                raise imports.ImportError('EXCEL_NATIVE_INTENT_CONFLICT')
        previous=mapping(settings,actor,payload['submission_operation_id'])
        if previous and (previous['origin_sha256']!=digest(origin) or previous['submission_input_sha256']!=digest(payload)):
            raise imports.ImportError('EXCEL_NATIVE_INTENT_CONFLICT')
        # Replays retain the exact original input, even when the current draft changes.
        if (directory/'intent.json').exists():
            intent=checked(read(directory/'intent.json'),'NativeSubmissionIntent')
            if intent['input']!=payload or intent['principal']!=actor:
                raise imports.ImportError('EXCEL_NATIVE_INTENT_CONFLICT')
            with imports._authorized(settings,session):pass
            admitted=mapping(settings,actor,payload['submission_operation_id'])
            if admitted:
                with imports._authorized(settings,session):
                    result=association(settings,directory,intent,admitted)
                if admitted['relation_kind']=='new_origin_task':
                    validate_primary_origin(settings,get_task(settings.database_path,admitted['task_id']))
                    schedule(admitted['task_id'])
                return result
            if (directory/'association.json').exists():
                result=checked(read(directory/'association.json'),'NativeSubmissionRecord')
                if result['state']!='duplicate_private_recorded':raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
                return result
        # Resolve outside the DB transaction; file locks must never wait inside SQLite.
        prepare={'schema_version':'case-excel-native-prepare-input-v1.0-proposal','batch_id':batch,'row_id':row,
            'import_operation_id':origin['import_operation_id'],'expected_row_sha256':origin['row_sha256'],
            'expected_import_intent_sha256':origin['import_intent_sha256'],'expected_import_head_sha256':None,
            'source_upload_id':payload['source_upload_id'],'action':payload['action'],'reason':payload['reason'],
            'expected_prior_attempt':payload['expected_prior_attempt']}
        current,candidate,actual,binding=row_bundle(settings,session,batch,row,origin['import_operation_id'])
        if actual!=origin:raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
        prepare['expected_import_head_sha256']=current['head_sha256']
        source=source_snapshot(settings,session,candidate,binding,payload['source_upload_id'])
        with operation_lock(settings.pipeline_root,scoped_lock_key('case',source['case_id'])), ExitStack() as locks:
            if source['source_upload_id']:
                locks.enter_context(operation_lock(settings.pipeline_root,'source-upload:'+source['source_upload_id']))
            # Do not call detail/preview while holding an upload lock: its Reader
            # obtains that same lock. Revalidate immutable source bytes directly.
            expected={'schema_version':'case-excel-native-preview-v1.0-proposal','principal':actor,'origin':origin,
                'current_import_head_sha256':current['head_sha256'],'source':source,'can_submit':True,'blocker_codes':[],
                'case_approved':False,'shared_published':False}
            if payload['action']!='analyze_new' or digest(expected)!=payload['preflight_sha256']:
                raise imports.ImportError('EXCEL_NATIVE_PREVIEW_CHANGED')
            if source['source_upload_id']:
                receipt,_=read_upload(settings.pipeline_root,source['source_upload_id'],source_url=source['canonical_url'],
                    user_id=actor['user_id'],receipt_sha256=source['upload_receipt_sha256'])
                if receipt['source_video_sha256']!=source['media_sha256']:raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
            if (directory/'intent.json').exists():
                intent=checked(read(directory/'intent.json'),'NativeSubmissionIntent')
                if intent['source']!=source or datetime.now(timezone.utc)-datetime.fromisoformat(intent['created_at'])>timedelta(hours=24):
                    raise imports.ImportError('EXCEL_NATIVE_PREVIEW_CHANGED')
            else:
                intent=checked({'schema_version':'case-excel-native-submission-intent-v1.0-proposal','principal':actor,
                    'input':payload,'source':source,'input_sha256':digest(payload),'created_at':iso_utc(),
                    'case_approved':False,'shared_published':False},'NativeSubmissionIntent')
                with imports._authorized(settings,session):write_once(directory/'intent.json',intent)
            checkpoint('intent')
            if source['source_upload_id']:
                reservation=checked({'schema_version':'case-excel-native-upload-reservation-v1.0-proposal','principal':actor,
                    'submission_intent':ref(settings,directory/'intent.json'),'submission_input_sha256':digest(payload),'source':source,
                    'created_at':intent['created_at'],'unadmitted_expires_at':(datetime.fromisoformat(intent['created_at'])+timedelta(hours=24)).isoformat().replace('+00:00','Z'),
                    'grants_media_production_rights':False},'UploadReservation')
                write_once(directory/'source_upload_reservation.json',reservation)
            checkpoint('reservation')
            from .canonical_gateway import resolve_case_source_duplicate
            duplicate=resolve_case_source_duplicate(settings,source['canonical_url'])
            active=find_active_case_task(settings.database_path,source['case_id'])
            with transaction(settings.database_path,immediate=True) as db:
                imports.validate_session(db,session)
                from .case_excel_orchestration import admission_guard
                admission_guard(settings,actor,batch,payload)
                if imports._head(imports._batch_dir(settings,actor['user_id'],batch))[0]!=current['head_sha256']:
                    raise imports.ImportError('IMPORT_HEAD_CHANGED')
                # No terminal task can be turned into a new analysis by changing Excel keys.
                prior=db.execute("SELECT 1 FROM tasks WHERE task_type='case_analysis' AND subject_ref=?",(source['case_id'],)).fetchone()
                if (active and not owns_task(settings,actor['user_id'],active)) or (not active and (duplicate or prior)):
                    admitted=None
                else:
                    task_origin=checked({'schema_version':'case-excel-native-origin-v1.0-proposal','submission_operation_id':payload['submission_operation_id'],
                        'principal':actor,'origin_sha256':digest(origin),'submission_intent':ref(settings,directory/'intent.json'),
                        'submission_input_sha256':digest(payload)},'NativeTaskOrigin')
                    task=create_case_task(settings.database_path,source_url=source['canonical_url'],case_id=source['case_id'],
                        source_upload={'upload_id':source['source_upload_id'],'receipt_sha256':source['upload_receipt_sha256']} if source['source_upload_id'] else None,
                        acquisition_provider=source['acquisition_provider'],provider_source_url=source['provider_source_url'],
                        created_by_user_id=actor['user_id'],queue_max=settings.task_queue_max,gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
                        excel_native_origin=task_origin,_connection=db)
                    if task['created_by']['user_id']!=actor['user_id']:
                        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
                    # A racing legacy writer can only be linked when input scope matches.
                    for key,value in [('source_url',source['canonical_url']),('acquisition_provider',source['acquisition_provider']),
                            ('source_upload',{'upload_id':source['source_upload_id'],'receipt_sha256':source['upload_receipt_sha256']} if source['source_upload_id'] else None)]:
                        if task['payload'].get(key)!=value:raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
                    relation='new_origin_task' if task['payload'].get('excel_native_origin')==task_origin else 'linked_owned_task'
                    db.execute('INSERT INTO case_excel_native_admissions_v1 VALUES(?,?,?,?,?,?,?,?,?)',
                        (actor['namespace'],actor['user_id'],payload['submission_operation_id'],digest(origin),digest(payload),task['task_id'],relation,0,intent['created_at']))
                    checkpoint('task_transaction')
                    admitted=mapping(settings,actor,payload['submission_operation_id'],db)
            checkpoint('task_committed')
            with imports._authorized(settings,session):
                result=association(settings,directory,intent,admitted)
        if admitted and admitted['relation_kind']=='new_origin_task':
            validate_primary_origin(settings,get_task(settings.database_path,admitted['task_id']))
            schedule(admitted['task_id'])
        checkpoint('scheduled')
        return result


def validate_primary_origin(settings, task, *, for_dispatch=False):
    """Worker and reviewer share the same exact immutable origin validation."""
    origin=checked(task['payload'].get('excel_native_origin'),'NativeTaskOrigin')
    intent=checked(read_ref(settings,origin['submission_intent']),'NativeSubmissionIntent')
    actor=intent['principal'];original=intent['input']['origin'];operation=intent['input']['submission_operation_id']
    if (actor!=origin['principal'] or actor!=principal(settings,actor['user_id']) or task['created_by']['user_id']!=actor['user_id']
            or digest(original)!=origin['origin_sha256'] or digest(intent['input'])!=origin['submission_input_sha256']
            or intent['input_sha256']!=origin['submission_input_sha256'] or operation!=origin['submission_operation_id']):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    directory=path_for(settings,actor,original['batch_id'],original['row_id'],operation)
    if ref(settings,directory/'intent.json')!=origin['submission_intent']:raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    assoc=checked(read(directory/'association.json'),'NativeSubmissionRecord')
    admitted=mapping(settings,actor,operation)
    if (not admitted or admitted['task_id']!=task['task_id'] or admitted['relation_kind']!='new_origin_task'
            or admitted['origin_sha256']!=digest(original) or admitted['submission_input_sha256']!=digest(intent['input'])
            or assoc['task_id']!=task['task_id'] or assoc['origin']!=original or assoc['principal']!=actor
            or assoc['native_input_sha256']!=digest(task['payload']) or assoc['intent_sha256']!=file_sha(directory/'intent.json')):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    base=imports._batch_dir(settings,actor['user_id'],original['batch_id'])
    batch=imports._read(base/'batch.json',imports.Batch);row=imports._read(base/'rows'/(original['row_id']+'.json'),imports.Row)
    saved=imports._read(base/'operations'/original['import_operation_id']/'intent.json',imports.Intent)
    result=imports._validated_result(base/'operations'/original['import_operation_id']/'result.json',saved)
    if (imports.record_sha(batch)!=original['batch_sha256'] or imports.record_sha(row)!=original['row_sha256']
            or imports.record_sha(saved)!=original['import_intent_sha256'] or imports.record_sha(result)!=original['import_result_sha256']
            or batch['file_sha256']!=original['workbook_sha256'] or row['owner_user_id']!=actor['user_id']):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    receipt=read(submission_path(settings,'tasks',task['task_id']))
    if receipt['principal']!=actor or receipt['identity']!=task['task_id'] or not owns_task(settings,actor['user_id'],task):
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    if task['subject_ref']!=intent['source']['case_id'] or task['payload']['source_url']!=intent['source']['canonical_url']:
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    source=intent['source']
    expected_upload={'upload_id':source['source_upload_id'],'receipt_sha256':source['upload_receipt_sha256']} if source['source_upload_id'] else None
    if task['payload'].get('source_upload')!=expected_upload or task['payload']['acquisition_provider']!=source['acquisition_provider']:
        raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    if for_dispatch and source['source_upload_id']:
        receipt,_=read_upload(settings.pipeline_root,source['source_upload_id'],source_url=source['canonical_url'],user_id=actor['user_id'],receipt_sha256=source['upload_receipt_sha256'])
        if receipt['source_video_sha256']!=source['media_sha256']:
            raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
    return intent,row,directory


def read_submission(settings, session, batch, row, operation):
    actor=principal(settings,session.user['id']);directory=path_for(settings,actor,batch,row,operation)
    with imports._authorized(settings,session):
        if not (directory/'association.json').exists():raise imports.ImportError('IMPORT_NOT_FOUND',404)
        result=checked(read(directory/'association.json'),'NativeSubmissionRecord')
        if result['principal']!=actor or result['origin']['row_id']!=row:raise imports.ImportError('IMPORT_NOT_FOUND',404)
        intent=checked(read(directory/'intent.json'),'NativeSubmissionIntent')
        if (intent['principal']!=actor or result['intent_sha256']!=file_sha(directory/'intent.json')
                or result['input_digest']!=digest(intent['input']) or result['origin']!=intent['input']['origin']):
            raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
        admitted=mapping(settings,actor,operation)
        if result['task_id']:
            task=get_task(settings.database_path,result['task_id'])
            if not admitted or admitted['task_id']!=result['task_id'] or not owns_task(settings,actor['user_id'],task):
                raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
        return result


def owned_row_submissions(settings,session,batch,row):
    """Exact associations for the owned list; never infer from latest files."""
    directory=imports._batch_dir(settings,session.user['id'],batch)
    result=[]
    for path in (directory/'native_submissions').glob('*/association.json'):
        value=checked(read(path),'NativeSubmissionRecord')
        if value['origin']['row_id']==row:
            result.append(read_submission(settings,session,batch,row,path.parent.name))
    return result


def upload_is_reserved(settings, upload_id):
    """Called only under the original Upload lock; never acquires a DB/file lock."""
    for p in (settings.pipeline_root/'data/case_intake_imports').glob('*/*/native_submissions/*/source_upload_reservation.json'):
        try:
            v=checked(read(p),'UploadReservation')
            if v['source']['source_upload_id']!=upload_id:continue
            intent=checked(read_ref(settings,v['submission_intent']),'NativeSubmissionIntent')
            original=intent['input']['origin'];actor=intent['principal']
            if (io_path(p.parent)!=path_for(settings,actor,original['batch_id'],original['row_id'],intent['input']['submission_operation_id'])
                    or v['principal']!=actor or v['source']!=intent['source'] or v['submission_input_sha256']!=digest(intent['input'])
                    or v['created_at']!=intent['created_at']
                    or datetime.fromisoformat(v['unadmitted_expires_at'])!=datetime.fromisoformat(intent['created_at'])+timedelta(hours=24)):
                raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
            admitted=mapping(settings,actor,intent['input']['submission_operation_id'])
            if admitted:
                task=get_task(settings.database_path,admitted['task_id'])
                # Unknown holds survive failure cleanup; known terminal results
                # follow the original Upload/Task retention policy.
                if task and (task['status'] in {'queued','running'} or task['error_code']=='CASE_EXTERNAL_RESULT_UNKNOWN'):return True
            elif datetime.now(timezone.utc)<datetime.fromisoformat(v['unadmitted_expires_at']):return True
        except (OSError,ValueError,KeyError,RuntimeError):
            # A damaged hold cannot authorize deletion. Surface the condition to
            # the original cleanup owner; do not treat it as a valid reservation.
            import logging
            logging.getLogger(__name__).warning('Native upload reservation invalid; cleanup deferred')
            raise ValueError('Invalid native upload reservation')
    return False


def reviewer_notes(settings, session, case_id, attempt_id):
    from .case_library_access import reviewer_authorization, reviewer_lock, require_private_case
    from .canonical_gateway import _find_case_path
    actor=principal(settings,session.user['id'])
    with operation_lock(settings.pipeline_root,scoped_lock_key('case',case_id)), reviewer_lock(settings,actor):
        grant=reviewer_authorization(settings,actor)
        require_private_case(settings,actor['user_id'],case_id,attempt_id)
        task=get_task(settings.database_path,attempt_id)
        if not task or task['subject_ref']!=case_id or task['status'] not in {'awaiting_review','completed'}:
            raise imports.ImportError('IMPORT_NOT_FOUND',404)
        _find_case_path(settings,case_id,attempt_id=attempt_id)
        intent,row,directory=validate_primary_origin(settings,task)
        original=intent['input']['origin'];base=imports._batch_dir(settings,intent['principal']['user_id'],original['batch_id'])
        fields=schema()['$defs']['BoundNotesProjection']['properties']['notes']['properties']
        def display(raw,keys):
            result={}
            for key in keys:
                value=raw.get(key) or None
                if value:
                    value=re.sub(r'(?:[A-Za-z]:[\\/]|\\\\)[^\s，。；]+','【文件引用已隐藏】',value)
                    value=re.sub(r'(?i)(?:bearer\s+|(?:token|cookie|password|secret)\s*[=:]\s*)\S+','【敏感值已隐藏】',value)
                    if len(value)>2000:value=value[:1985]+'…（其余请核对原稿）'
                result[key]=value
            return result
        notes={'case_notes':display(row['raw_case'],fields['case_notes']['properties']),
            'segments':[display(v,fields['segments']['items']['properties']) for v in row['raw_segments']],
            'rights_claims':display(row['raw_rights'] or {},fields['rights_claims']['properties'])}
        state=settings.pipeline_root/'data/case_analysis_attempts'/case_id/attempt_id/'case_analysis_attempt_v1.json'
        result=checked({'schema_version':'case-excel-bound-notes-projection-v1.0-proposal','actor':actor,'reviewer_grant':grant,
            'native_case_attempt':ref(settings,state),'submission':ref(settings,directory/'association.json'),
            'row':ref(settings,base/'rows'/(row['row_id']+'.json')),'trust':'unverified_submitter_candidate',
            'permitted_fields':list(notes),'notes':notes,'evidence_promoted':False,'case_approved':False,'shared_published':False},'BoundNotesProjection')
        with imports._authorized(settings,session):
            reviewer_authorization(settings,actor)
            return result
