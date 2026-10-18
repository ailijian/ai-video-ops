"""Console adapter for the Canonical Human evidence revision/coverage owner."""
from __future__ import annotations

from typing import Literal
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .canonical_gateway import CanonicalOperationError
from .case_library_access import principal, reviewer_authorization, reviewer_lock, require_private_case
from . import review_commands
from .task_service import TaskSubmissionError, submit_task, get_task, GPU_HEAVY
from human_review_operations_v1 import digest, read, file_sha
from case_evidence_revision_v1 import (resolve_target, source_refs, review_scope, save_revision,
    bind_build_execution, revisions, check_ref, RevisionError)


class NarrationEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    segment_id: str = Field(min_length=1,max_length=80)
    corrected_text: str = Field(min_length=1,max_length=4000)
    basis: Literal['source_audio_listening']
    evidence_frame_refs: list[str] = Field(min_length=1,max_length=100)


class BoundaryEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    boundary_frame_id: str = Field(min_length=1,max_length=120)
    target_frame_id: str = Field(min_length=1,max_length=120)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    review_context: str = Field(min_length=1,max_length=50000)
    attempt_id: str = Field(pattern=r'^[A-Za-z0-9_-]{8,128}$')
    expected_candidate_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_sources_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_revision_sha256: str | None = Field(...,pattern=r'^[a-f0-9]{64}$')
    narration_edits: list[NarrationEdit] = Field(default_factory=list,max_length=100)
    boundary_edits: list[BoundaryEdit] = Field(default_factory=list,max_length=100)
    reason: str = Field(default='',max_length=1000)


def translated(exc):
    return CanonicalOperationError(exc.code,str(exc),'请核对当前版本、来源和待处理问题后继续。')


def workspace(settings, case_id, attempt_id):
    """Private reviewer projection; paths, raw words and grants are not exposed."""
    try:
        target=resolve_target(settings.pipeline_root,case_id,attempt_id)
        result={'state':target.state,'revision_id':target.revision_root.name if target.revision_root else None,
            'revision_sha256':(target.revision_ref or {}).get('sha256'),
            'can_save':False,'can_approve':False,'scope':None,'narration':[],'boundaries':[],'frames':[]}
        if target.candidate is None:
            edit=read(target.revision_root/'edit_v1.json')
            result.update(message='修改已保存，等待重新校验。' if target.state!='failed' else '重新校验失败，请从原计算任务恢复。',
                saved_narration=[{'segment_id':r['segment_id'],'original_text':r['original'].get('source_text'),
                    'corrected_text':r['corrected_text']} for r in edit['narration_edits']])
            execution=target.revision_root/'build_execution_v1.json'
            if execution.is_file(): result['build_task_id']=read(execution)['build_task_id']
            return result
        sources=source_refs(settings.pipeline_root,target.candidate)
        repo=settings.pipeline_root.parent
        audio,narration,manifest,visual,shots=[read(check_ref(repo,sources[k])) for k in
            ('audio_v1','narration_review_v1','visual_manifest','visual_v1','shot_boundaries')]
        scope=review_scope(settings.pipeline_root,case_id,attempt_id)
        result.update(can_save=True,can_approve=scope['summary']['blocked']==0,
            candidate_sha256=file_sha(target.candidate),sources_sha256=digest(sources),
            scope={'scope_sha256':scope['scope_sha256'],'summary':scope['summary'],
                'items':[{k:v for k,v in r.items() if k!='revision_edit_ref'} for r in scope['items']]},
            narration=[{'segment_id':s['segment_id'],'start':s['start'],'end':s['end'],
                'original_text':s['source_text'],'effective_text':s['reviewed_text'],'frame_refs':s.get('evidence_frame_refs') or []}
                for s in narration['segments']],
            boundaries=[{'frame_id':s['boundary']['selected_from_frame_ref'],'start':s['start'],'end':s['end'],
                'locked':s['start']==0} for s in shots['shots']],
            frames=[{'frame_id':f.get('frame_id') or f['filename'],'seconds':f['timestamp_seconds']} for f in manifest['frames']
                if (f.get('frame_id') or f['filename']) in {v['frame_id'] for v in visual['frames']}])
        return result
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
        return {'state':'unavailable','can_save':False,'can_approve':False,'scope':None,
            'message':'当前审核范围无法建立，暂不能批准入库。请恢复完整来源与依赖证据，或重新分析后再审核。'}


def register_routes(app,settings,require_console_access,require_csrf,review_command,task_runner):
    @app.post('/api/cases/{case_id}/review-revisions')
    def save(case_id: str, payload: RevisionRequest,
             x_csrf_token: str | None = Header(default=None,alias='X-CSRF-Token'),
             session=Depends(require_console_access)):
        require_csrf(session,x_csrf_token)
        actor=principal(settings,int(session.user['id']))
        reviewer_authorization(settings,actor)
        require_private_case(settings,actor['user_id'],case_id,payload.attempt_id)
        def preflight(command):
            with reviewer_lock(settings,actor):
                reviewer_authorization(settings,actor)
                if command['context']['snapshot']['attempt_id']!=payload.attempt_id:
                    raise review_commands.blocked()
                try:
                    save_revision(settings.pipeline_root,case_id,payload.attempt_id,
                        operation_id=command['context']['operation_id'],actor=actor,database_path=settings.database_path,
                        validate_only=True,**payload.model_dump(exclude={'review_context','attempt_id'}))
                except RevisionError as exc:
                    raise translated(exc) from exc
        def execute(command):
            with reviewer_lock(settings,actor):
                reviewer_authorization(settings,actor)
                if command['context']['snapshot']['attempt_id']!=payload.attempt_id:
                    raise review_commands.blocked()
                try:
                    target=save_revision(settings.pipeline_root,case_id,payload.attempt_id,
                        operation_id=command['context']['operation_id'],actor=actor,database_path=settings.database_path,
                        saved_at=command['at'],**payload.model_dump(exclude={'review_context','attempt_id'}))
                    original=read(target.original_candidate)
                    existing_binding=target.revision_root/'build_execution_v1.json'
                    ended=(read(target.attempt_root/'case_analysis_attempt_v1.json').get('status')=='rejected'
                        or (target.attempt_root/'human_review_decision_v1.json').exists()
                        or (settings.pipeline_root/'data/cases'/case_id/'approval_receipt.json').exists())
                    if ended and not existing_binding.exists():
                        return {'revision_id':target.revision_root.name,'state':'saved','build_task_id':None,
                            'message':'原修改已保存；该投稿已结束，不再排入计算。'}
                    if existing_binding.exists():
                        task=get_task(settings.database_path,read(existing_binding)['build_task_id'])
                        if task is None:
                            raise RevisionError('CASE_REVISION_EXECUTION_INVALID','原计算任务不可用，不能创建其他任务冒充恢复。')
                    else:
                        task=submit_task(settings.database_path,task_id_prefix='case-revision',task_type='case_analysis',
                        subject_ref=case_id,operation_identity='case_revision:'+case_id+':'+target.revision_root.name,
                            execution_lane=GPU_HEAVY,payload={'source_url':original['identity']['source_url'],
                                'review_operation_id':command['context']['operation_id'],
                                'evidence_revision':{'attempt_id':payload.attempt_id,'revision_id':target.revision_root.name,
                                    'revision_sha256':target.revision_ref['sha256']}},stage='等待修订校验',
                            created_by_user_id=actor['user_id'],queue_max=settings.task_queue_max,
                            gpu_pending_per_user_max=settings.gpu_pending_per_user_max)
                    bind_build_execution(settings.pipeline_root,settings.database_path,case_id,payload.attempt_id,
                        target.revision_root.name,task['task_id'])
                    if not ended:task_runner.schedule(task['task_id'])
                    return {'revision_id':target.revision_root.name,'state':'saved','build_task_id':task['task_id'],
                        'message':'修改已保存，等待重新校验。'}
                except RevisionError as exc:
                    raise translated(exc) from exc
                except TaskSubmissionError as exc:
                    raise CanonicalOperationError('CASE_REVISION_SAVED_AWAITING_TASK','修改已保存，计算任务暂未排入。',
                        '请刷新后继续原保存操作；不会丢失修改或重复创建任务。') from exc
        return review_command('case',case_id,session,payload,f'/api/cases/{case_id}/review-revisions',execute,preflight=preflight)

    @app.get('/api/cases/{case_id}/review-revisions/{revision_id}')
    def detail(case_id: str,revision_id: str,attempt_id: str,session=Depends(require_console_access)):
        actor=principal(settings,int(session.user['id']))
        reviewer_authorization(settings,actor)
        require_private_case(settings,actor['user_id'],case_id,attempt_id)
        if not any(v['revision_id']==revision_id for _,v in revisions(settings.pipeline_root,case_id,attempt_id)):
            raise HTTPException(404)
        return workspace(settings,case_id,attempt_id)
