"""Finite confirmed Intake coordination. Only EX-S1 creates original Tasks."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from typing import Annotated,Literal
from pydantic import Field,model_validator
from human_review_operations_v1 import read,write_once,digest,file_sha
from . import case_excel_import as imports,case_excel_native as native
from .case_library_access import principal,owns_task
from .database import connect
from .operation_lock import operation_lock,authority_mutation_barrier
from .task_service import get_task,find_active_case_task,TaskSubmissionError

Id=imports.Identifier;Sha=imports.Sha;Base=imports.StrictRecord
class PrepareInput(Base):
    operation_id: Annotated[str,Field(pattern=r'^orch_[a-f0-9]{32}$')]
    import_operation_id: Id
    expected_import_head_sha256: Sha
    selected_rows: Annotated[list[imports.RowRef],Field(min_length=1,max_length=imports.parser.MAX_ROWS)]
    @model_validator(mode='after')
    def unique(self):
        if len({r.row_id for r in self.selected_rows})!=len(self.selected_rows):raise ValueError('Duplicate Row')
        return self

class ItemPreview(Base):
    row: imports.RowRef
    native_prepare: dict
    native_preview: dict
    submission_operation_id: Id
    relation: Literal['new_task','linked_owned_task','duplicate','pending_source']
    @model_validator(mode='after')
    def native_contract(self):
        native.checked(self.native_prepare,'NativePrepareInput');native.checked(self.native_preview,'NativePreview')
        p=self.native_prepare;v=self.native_preview
        if (p['row_id']!=self.row.row_id or p['expected_row_sha256']!=self.row.row_sha256
                or v['origin']['row_id']!=self.row.row_id or v['origin']['row_sha256']!=self.row.row_sha256
                or v['origin']['batch_id']!=p['batch_id']
                or self.relation in {'new_task','linked_owned_task'} and not v['can_submit']):raise ValueError('Native Row identity mismatch')
        return self

class Preview(Base):
    schema_version: Literal['case-excel-orchestration-preview-v1.0']
    principal: dict
    input: PrepareInput
    batch_id: Id
    batch_sha256: Sha
    items: Annotated[list[ItemPreview],Field(min_length=1,max_length=imports.parser.MAX_ROWS)]
    new_task_count: Annotated[int,Field(ge=0)]
    preview_sha256: Sha
    @model_validator(mode='after')
    def identity(self):
        native.checked(self.principal,'Principal')
        value=self.model_dump();value.pop('preview_sha256')
        if (digest(value)!=self.preview_sha256 or [x.row for x in self.items]!=self.input.selected_rows
                or self.new_task_count!=sum(x.relation=='new_task' for x in self.items)
                or any(x.native_prepare['import_operation_id']!=self.input.import_operation_id
                    or x.native_prepare['batch_id']!=self.batch_id or x.native_preview['principal']!=self.principal
                    or x.native_prepare['expected_import_head_sha256']!=self.input.expected_import_head_sha256 for x in self.items)):
            raise ValueError('Preview identity mismatch')
        return self

class SubmitInput(Base):
    schema_version: Literal['case-excel-orchestration-submit-v1.0']
    preview: Preview
    confirmed_submit_analysis: Literal[True]

class Intent(Base):
    schema_version: Literal['case-excel-orchestration-intent-v1.0']
    principal: dict
    input: SubmitInput
    input_sha256: Sha
    created_at: str

class ControlInput(Base):
    operation_id: Annotated[str,Field(pattern=r'^control_[a-f0-9]{32}$')]
    action: Literal['pause','resume','cancel']
    expected_parent_sha256: Sha|None

class Control(Base):
    schema_version: Literal['case-excel-orchestration-control-v1.0']
    principal: dict
    input: ControlInput
    parent_sha256: Sha|None
    at: str

class RowResult(Base):
    schema_version: Literal['case-excel-orchestration-row-result-v1.0']
    row: imports.RowRef
    state: Literal['submitted','linked','duplicate','pending_source','cancelled']
    native_submission: dict|None
    at: str

class Failure(Base):
    schema_version: Literal['case-excel-orchestration-row-failure-v1.0']
    row: imports.RowRef
    error_code: str
    retryable: bool
    at: str


def checkpoint(point):pass
def now():return datetime.now(timezone.utc).isoformat()
def dump(value):return value.model_dump() if hasattr(value,'model_dump') else value
def load(path,model):
    try:return model.model_validate(read(path)).model_dump()
    except (ValueError,KeyError,RuntimeError) as exc:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID') from exc


def directory(settings,actor,batch,operation):
    import re
    if not re.fullmatch(r'orch_[a-f0-9]{32}',operation):raise imports.ImportError('IMPORT_NOT_FOUND',404)
    return imports._batch_dir(settings,actor['user_id'],batch)/'native_orchestrations'/operation


def native_input(item):
    p=item['native_preview']
    return {'schema_version':'case-excel-native-submission-input-v1.0-proposal','submission_operation_id':item['submission_operation_id'],
        'origin':p['origin'],'expected_submission_parent_sha256':None,'source_upload_id':p['source']['source_upload_id'],
        'confirmed_submit_analysis':True,'preflight_sha256':p['preflight_sha256'],'action':'analyze_new','reason':'','expected_prior_attempt':None}


def preview(settings,session,batch,payload):
    payload=PrepareInput.model_validate(payload).model_dump()
    record=imports.detail(settings,session,batch);actor=principal(settings,session.user['id'])
    if record['head_sha256']!=payload['expected_import_head_sha256']:raise imports.ImportError('IMPORT_HEAD_CHANGED')
    candidates={r['row_id']:r for r in record['rows']}
    operations=[x for x in record['operations'] if x['intent']['operation_id']==payload['import_operation_id']]
    if len(operations)!=1:raise imports.ImportError('IMPORT_NOT_FOUND',404)
    operation=operations[0];items=[]
    for ref in payload['selected_rows']:
        row=candidates.get(ref['row_id'])
        if not row or imports.record_sha(row)!=ref['row_sha256']:raise imports.ImportError('EXCEL_NATIVE_SOURCE_CHANGED')
        binding=next((v for v in operation['intent']['row_source_bindings'] if v['row_id']==ref['row_id']),None)
        if binding is None:raise imports.ImportError('IMPORT_NOT_FOUND',404)
        prepare={'schema_version':'case-excel-native-prepare-input-v1.0-proposal','batch_id':batch,'row_id':ref['row_id'],
            'import_operation_id':payload['import_operation_id'],'expected_row_sha256':ref['row_sha256'],
            'expected_import_intent_sha256':operation['intent_sha256'],'expected_import_head_sha256':record['head_sha256'],
            'source_upload_id':(binding['native_upload_ref'] or {}).get('upload_id'),'action':'analyze_new','reason':'','expected_prior_attempt':None}
        p=native.preview(settings,session,batch,ref['row_id'],prepare)
        relation='pending_source'
        try:
            source=native.resolve_douyin_source_input(row['raw_case']['source_url'])
            case_id=source.video_id;active=find_active_case_task(settings.database_path,case_id)
            with connect(settings.database_path) as db:
                prior=db.execute("SELECT 1 FROM tasks WHERE task_type='case_analysis' AND subject_ref=?",(case_id,)).fetchone()
            from .canonical_gateway import resolve_case_source_duplicate
            duplicate=resolve_case_source_duplicate(settings,source.canonical_url)
            relation='linked_owned_task' if p['can_submit'] and active and owns_task(settings,actor['user_id'],active) else 'duplicate' if active or prior or duplicate else 'new_task' if p['can_submit'] else 'pending_source'
        except native.SourceInputError:pass
        items.append({'row':ref,'native_prepare':prepare,'native_preview':p,'relation':relation,
            'submission_operation_id':'native_'+digest([actor,batch,payload['operation_id'],ref])[:40]})
    value={'schema_version':'case-excel-orchestration-preview-v1.0','principal':actor,'input':payload,'batch_id':batch,
        'batch_sha256':record['batch_sha256'],'items':items,'new_task_count':sum(v['relation']=='new_task' for v in items)}
    value['preview_sha256']=digest(value)
    return Preview.model_validate(value).model_dump()


def intent(settings,session,batch,operation):
    actor=principal(settings,session.user['id']);root=directory(settings,actor,batch,operation)
    if not (root/'intent.json').is_file():raise imports.ImportError('IMPORT_NOT_FOUND',404)
    value=load(root/'intent.json',Intent)
    if (value['principal']!=actor or value['input']['preview']['principal']!=actor
            or value['input']['preview']['batch_id']!=batch or value['input']['preview']['input']['operation_id']!=operation
            or value['input_sha256']!=digest(value['input'])):raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
    return root,value


def controls(root,actor):
    head=None;state='active';history=[];seen=set()
    for sequence,path in enumerate(sorted((root/'controls').glob('*.json')),1):
        v=load(path,Control)
        if (path.name!=f'{sequence:06}.json' or v['principal']!=actor or v['parent_sha256']!=head
                or v['input']['expected_parent_sha256']!=head or state=='cancelled' or v['input']['operation_id'] in seen):
            raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
        seen.add(v['input']['operation_id']);head=file_sha(path);state={'pause':'paused','resume':'active','cancel':'cancelled'}[v['input']['action']];history.append(v)
    return state,head,history


def admission_guard(settings,actor,batch,payload):
    """Rechecked inside the original Task DB transaction; control writes share it."""
    base=imports._batch_dir(settings,actor['user_id'],batch)/'native_orchestrations'
    for path in base.glob('*/intent.json'):
        value=load(path,Intent)
        if value['principal']!=actor:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
        items=[v for v in value['input']['preview']['items'] if v['submission_operation_id']==payload['submission_operation_id']]
        if not items:continue
        if len(items)!=1 or items[0]['relation']=='pending_source' or native_input(items[0])!=payload:
            raise imports.ImportError('EXCEL_ORCHESTRATION_INTENT_CONFLICT')
        state,_,_=controls(path.parent,actor)
        if state!='active':raise imports.ImportError('EXCEL_ORCHESTRATION_'+state.upper())


def submit(settings,session,batch,payload,schedule):
    payload=SubmitInput.model_validate(payload).model_dump();p=payload['preview'];actor=principal(settings,session.user['id'])
    root=directory(settings,actor,batch,p['input']['operation_id'])
    with authority_mutation_barrier(settings),operation_lock(settings.pipeline_root,'excel-orchestration:'+digest([actor,batch,root.name])):
        if (root/'intent.json').exists():
            _,saved=intent(settings,session,batch,root.name)
            if saved['input']!=payload:raise imports.ImportError('EXCEL_ORCHESTRATION_INTENT_CONFLICT')
        else:
            if preview(settings,session,batch,p['input'])!=p:raise imports.ImportError('EXCEL_NATIVE_PREVIEW_CHANGED')
            value=Intent(schema_version='case-excel-orchestration-intent-v1.0',principal=actor,input=SubmitInput.model_validate(payload),
                input_sha256=digest(payload),created_at=now()).model_dump()
            with imports._authorized(settings,session):write_once(root/'intent.json',value)
        checkpoint('intent')
    return advance(settings,session,batch,root.name,schedule)


def advance(settings,session,batch,operation,schedule):
    actor=principal(settings,session.user['id'])
    with authority_mutation_barrier(settings),operation_lock(settings.pipeline_root,'excel-orchestration:'+digest([actor,batch,operation])):
        root,saved=intent(settings,session,batch,operation)
        with imports._authorized(settings,session):pass
        state,_,_=controls(root,actor)
        for item in saved['input']['preview']['items']:
            output=root/'rows'/item['row']['row_id']/'result.json'
            if output.exists():continue
            admitted=native.mapping(settings,actor,item['submission_operation_id'])
            failures=sorted(output.parent.glob('failure_*.json'))
            last=load(failures[-1],Failure) if failures else None
            if last and not last['retryable']:continue
            if state=='paused' and not admitted:continue
            status='cancelled' if state=='cancelled' and not admitted else 'pending_source' if item['relation']=='pending_source' else 'duplicate' if item['relation']=='duplicate' and not item['native_preview']['can_submit'] else None
            result=None
            if status is None:
                try:
                    result=native.submit(settings,session,batch,item['row']['row_id'],native_input(item),schedule,_barrier_held=True)
                    status={'admitted':'submitted','linked_owned_task':'linked','duplicate_private_recorded':'duplicate'}[result['state']]
                    checkpoint('native_admitted')
                except TaskSubmissionError as exc:
                    if exc.code in {'TASK_QUEUE_FULL','GPU_PENDING_LIMIT_REACHED'}:break
                    _failure(output,item,exc.code,False);continue
                except imports.ImportError as exc:
                    if exc.status==403:raise
                    _failure(output,item,exc.code,False);continue
                except OSError:
                    _failure(output,item,'EXCEL_NATIVE_RECOVERY_REQUIRED',True);continue
            reference=None
            if result:
                native_dir=native.path_for(settings,actor,batch,item['row']['row_id'],item['submission_operation_id'])
                reference=native.ref(settings,native_dir/'association.json')
            value=RowResult(schema_version='case-excel-orchestration-row-result-v1.0',row=imports.RowRef.model_validate(item['row']),
                state=status,native_submission=reference,at=now()).model_dump()
            with imports._authorized(settings,session):write_once(output,value)
            checkpoint('row_result')
    return result_projection(settings,session,batch,operation)


def _failure(output,item,code,retryable):
    paths=sorted(output.parent.glob('failure_*.json'))
    value=Failure(schema_version='case-excel-orchestration-row-failure-v1.0',row=imports.RowRef.model_validate(item['row']),
        error_code=code,retryable=retryable,at=now()).model_dump()
    write_once(output.parent/f'failure_{len(paths)+1:06}.json',value)


def control(settings,session,batch,operation,payload):
    payload=ControlInput.model_validate(payload).model_dump();actor=principal(settings,session.user['id'])
    with authority_mutation_barrier(settings),operation_lock(settings.pipeline_root,'excel-orchestration:'+digest([actor,batch,operation])):
        root,saved=intent(settings,session,batch,operation);state,head,history=controls(root,actor)
        existing=[v for v in history if v['input']['operation_id']==payload['operation_id']]
        if existing:
            if existing[0]['input']!=payload:raise imports.ImportError('EXCEL_ORCHESTRATION_INTENT_CONFLICT')
        else:
            if state=='cancelled' or payload['expected_parent_sha256']!=head:raise imports.ImportError('EXCEL_ORCHESTRATION_CONTROL_CHANGED')
            value=Control(schema_version='case-excel-orchestration-control-v1.0',principal=actor,input=ControlInput.model_validate(payload),parent_sha256=head,at=now()).model_dump()
            with imports._authorized(settings,session):write_once(root/'controls'/f'{len(history)+1:06}.json',value)
    return result_projection(settings,session,batch,operation)


def result_projection(settings,session,batch,operation):
    root,saved=intent(settings,session,batch,operation);actor=saved['principal'];state,head,_=controls(root,actor);items=[]
    originals=imports.detail(settings,session,batch);titles={v['row_id']:v['raw_case'].get('source_title') for v in originals['rows']};recorded=0
    with imports._authorized(settings,session):pass
    for item in saved['input']['preview']['items']:
        output=root/'rows'/item['row']['row_id']/'result.json';result=load(output,RowResult) if output.exists() else None
        if result and result['row']!=item['row']:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
        if result:
            recorded+=1
            if result['state'] in {'submitted','linked'} and result['native_submission'] is None:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
            if result['state']=='pending_source' and item['relation']!='pending_source':raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
            if result['state']=='duplicate' and result['native_submission'] is None and item['relation']!='duplicate':raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
        row={'row_id':item['row']['row_id'],'title':titles.get(item['row']['row_id']),'state':result['state'] if result else 'cancelled' if state=='cancelled' else 'pending',
            'task_id':None,'task_status':None,'new_task':False,'href':None,'error_code':None}
        task=None
        if result and result['native_submission']:
            original=native.read_submission(settings,session,batch,row['row_id'],item['submission_operation_id'])
            path=native.path_for(settings,actor,batch,row['row_id'],item['submission_operation_id'])/'association.json'
            if native.ref(settings,path)!=result['native_submission']:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
            if result['state']!={'admitted':'submitted','linked_owned_task':'linked','duplicate_private_recorded':'duplicate'}[original['state']]:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
            row['new_task']=original['relation_kind']=='new_origin_task'
            if original['task_id']:
                task=get_task(settings.database_path,original['task_id'])
                if not task or not owns_task(settings,actor['user_id'],task):raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
        elif result and result['state']=='duplicate':
            # An already completed Task on THIS exact saved Row remains a
            # provable owned association. Project it without a new admission.
            old=native.owned_row_submissions(settings,session,batch,row['row_id'])
            identities={v['task_id'] for v in old if v['task_id'] and v['origin']==item['native_preview']['origin']}
            if len(identities)>1:raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
            if identities:
                task=get_task(settings.database_path,next(iter(identities)))
                if not task or not owns_task(settings,actor['user_id'],task):raise imports.ImportError('EXCEL_ORCHESTRATION_HISTORY_INVALID')
        elif not result:
            failures=sorted(output.parent.glob('failure_*.json'))
            if failures:
                last=load(failures[-1],Failure);row.update(state='failed',error_code=last['error_code'])
                # A terminal admission failure is a processed Row, even though
                # it has no Native Task association. Do not poll it forever or
                # imply that retrying can bypass its stale-source rejection.
                if not last['retryable']:recorded+=1
        if task:_project_owned_task(settings,row,task)
        items.append(row)
    return {'schema_version':'case-excel-orchestration-result-projection-v1.0','batch_id':batch,'operation_id':operation,
        'control_state':state,'control_head_sha256':head,'planned_new_task_count':saved['input']['preview']['new_task_count'],
        'actual_new_task_count':sum(r['new_task'] for r in items),'submission_complete':recorded==len(items),
        'rows':items,'intent_sha256':file_sha(root/'intent.json')}


def _project_owned_task(settings,row,task):
    row.update(task_id=task['task_id'],task_status=task['status'],href='/tasks/'+task['task_id'])
    if task['status']=='failed':row.update(state='failed',error_code=task['error_code'])
    elif task['status']=='awaiting_review':row['state']='awaiting_review'
    elif task['status']=='completed':
        from .canonical_gateway import get_case_detail,CanonicalOperationError
        from .case_shared_display import sharing_status
        try:
            case=get_case_detail(settings,task['subject_ref'],attempt_id=task['task_id'])
            if case['review']['approved']:
                sharing=sharing_status(settings,task['subject_ref'])
                row.update({key:sharing[key] for key in ('sharing_state','sharing_label','sharing_next_action') if key in sharing})
                # Keep the existing orchestration state for old consumers;
                # display wording comes from the original Publication reader.
                row['state']='approved_shared' if sharing['sharing_state']=='approved_shared' else 'approved_pending_share'
        except (CanonicalOperationError,OSError,ValueError,KeyError):pass
