"""One explicit confirmation, independently committed Business/Speaker owners."""
from __future__ import annotations

import copy
from pathlib import Path
from human_review_operations_v1 import digest, file_sha, read, write_once, io_path
from . import customer_confirmation as business_owner
from . import review_commands
from .canonical_gateway import CanonicalOperationError

VERSION='customer-final-confirmation-v1.1'
APPROVE='approve_customer_and_speakers'


def validated_preparation(settings,path):
    from speaker_review_preparation_v1 import validated_result
    try:return validated_result(settings.pipeline_root,path)
    except (ValueError,RuntimeError,KeyError,TypeError) as exc:
        raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','人物整理结果或来源已变化，需要重新核对。') from exc


def preparation_request(settings, identity, user_id, actor, payload, *, persist=True):
    from .customer_gateway import validate_customer_review_context, _latest_intake_dir, _speaker_discovery_path
    from speaker_review_preparation_v1 import VERSION as PREPARATION, request_digest, person_request, now_iso
    business_owner.guard(settings,identity,all_versions=True)
    request=copy.deepcopy(payload)
    for key in ('joint_speaker_review','speaker_fact_decisions','retry_preparation','business_only'):
        request.pop(key,None)
    token=request.pop('review_context',None)
    validate_customer_review_context(settings,identity,token,user_id,actor,request)
    directory=_latest_intake_dir(settings,identity)
    discovery_path=_speaker_discovery_path(directory)
    if not discovery_path.is_file():
        raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','尚未发现可核对的出镜人，请先完成资料整理。')
    discovery=read(discovery_path)
    candidates={p['candidate_id']:p for p in discovery.get('speaker_candidates',[])}
    selections=request.get('speaker_confirmations',[])
    if not selections:
        previous=directory/'speaker_discovery_confirmation_v1.json'
        selections=read(previous).get('decisions',[]) if previous.is_file() else []
    selected=[];seen=set();speaker_ids=set()
    for item in selections:
        if not item.get('selected'):continue
        cid=item['candidate_id']
        if cid in seen or cid not in candidates:
            raise business_owner.fail('SPEAKER_CANDIDATE_NOT_FOUND','所选出镜人与原始资料不一致。')
        seen.add(cid)
        selection={k:item.get(k) for k in ('candidate_id','selected','speaker_name','public_role','speaker_type')}
        try:person=person_request(identity,candidates[cid],selection)
        except (ValueError,RuntimeError) as exc:
            raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','请补齐所选出镜人的姓名、身份和类型。') from exc
        if person['speaker_id'] in speaker_ids:
            raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','多位人物使用了相同姓名与公开身份，请先核对，避免重复建档。')
        speaker_ids.add(person['speaker_id'])
        selected.append(selection)
    selected.sort(key=lambda v:v['candidate_id'])
    value={'schema_version':PREPARATION,'business_id':identity,'intake_id':directory.name,
        'sources':{name:business_owner.ref(settings,p) for name,p in (
            ('raw',directory/'customer_onboarding_request_v1.json'),('intake',directory/'customer_intake_v1.json'),
            ('privacy',directory/'customer_intake_privacy_projection_v1.json'),('discovery',discovery_path))},
        'selections':selected}
    path=settings.pipeline_root/'data/speaker_preparations'/identity/directory.name/request_digest(value)/'request.json'
    if io_path(path).is_file():
        existing=read(path)
        if request_digest(existing)!=request_digest(value):
            raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','出镜人整理来源已变化。')
        value=existing
    elif persist:
        value['created_at']=now_iso();write_once(path,value)
    else:
        raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','出镜人资料尚未整理完成，请等待或继续整理。')
    return path,value


def preparation_status(settings,path):
    from speaker_review_preparation_v1 import validate_preparation_request
    request,_=validate_preparation_request(settings.pipeline_root,path)
    summary=path.parent/'prepared.json'
    if not io_path(summary).is_file():return {'state':'pending','people':[]}
    value=validated_preparation(settings,path)
    if value.get('request_sha256')!=file_sha(path):
        raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','人物整理结果与当前来源不一致。')
    people=[]
    for person in value['people']:
        for source in person['artifacts'].values():business_owner.check_ref(settings,source)
        candidates=read(business_owner.check_ref(settings,person['artifacts']['candidates']))
        people.append({'candidate_id':person['candidate_id'],'speaker_id':person['speaker_id'],
            'name':person['selection']['speaker_name'],'public_role':person['selection']['public_role'],
            'speaker_type':person['selection']['speaker_type'],
            'facts':[{'candidate_id':v['fact_candidate_id'],'field':v['target_field'],
                'value':v.get('normalized_value'),'source_excerpt':v.get('source_excerpt',''),
                'editable':v['target_field'] not in {'public_display_name','public_role','first_person_forbidden_claims'}}
                for v in candidates['fact_candidates']]})
    return {'state':'prepared','people':people,'preparation_sha256':file_sha(summary)}


def enqueue_preparation(settings,path,identity,user_id,*,retry=False):
    from .customer_task_service import create_customer_task
    from .task_service import update_task,get_task
    value=read(path)
    task=create_customer_task(settings.database_path,business_id=identity,intake_id=value['intake_id'],
        request_path=str(settings.pipeline_root/value['sources']['raw']['path']),customer_name='整理客户与出镜人资料',
        industry='',created_by_user_id=user_id,queue_max=settings.task_queue_max,
        speaker_preparation_request=str(path))
    if task['payload'].get('speaker_preparation_request')==str(path) and task['status']=='failed' and retry:
        update_task(settings.database_path,task['task_id'],status='queued',progress=0,stage='继续整理出镜人资料',error_code='',error_message='')
        task=get_task(settings.database_path,task['task_id'])
    return task


def proposed_person(settings,person,decisions,actor,at):
    from speaker_fact_review_v1 import (normalize_decisions,validate_decision_coverage,apply_decisions,
        build_speaker_persona_input,speaker_blockers)
    intake=read(business_owner.check_ref(settings,person['artifacts']['intake']))
    candidates=read(business_owner.check_ref(settings,person['artifacts']['candidates']))
    normalized=normalize_decisions(decisions)
    validate_decision_coverage(candidates,normalized)
    immutable={v['fact_candidate_id'] for v in candidates['fact_candidates']
        if v['target_field'] in {'public_display_name','public_role','first_person_forbidden_claims'}}
    if any(v['candidate_id'] in immutable and v['decision']!='approve' for v in normalized):
        raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','姓名、身份或原有表达禁用内容有变化，请先修改人物资料并重新整理。')
    reviewed=apply_decisions(intake=intake,candidate_artifact=candidates,decisions=normalized,reviewer=actor,reviewed_at=at)
    source=build_speaker_persona_input(business_id=person['speaker_request']['business_id'],
        speaker_id=person['speaker_id'],speaker_type=person['speaker_request']['speaker_type'],
        intake_id=person['speaker_request']['intake_id'],reviewed=reviewed,
        reviewed_path=settings.pipeline_root/person['artifacts']['candidates']['path'])
    return {'decisions':normalized,'projection':speaker_projection(source),'blockers':speaker_blockers(source)}


def speaker_projection(value):
    return {**business_owner.projection(value),'speaker_type':value.get('speaker_type'),
        'speaker_authority':copy.deepcopy(value.get('speaker_authority')),
        'critical_constraints':copy.deepcopy(value.get('critical_constraints') or [])}


def preview(settings,identity,user_id,actor,payload):
    import base64,json
    from datetime import datetime,timezone
    request=copy.deepcopy(payload)
    person_decisions=request.pop('speaker_fact_decisions',[])
    request.pop('joint_speaker_review',None);request.pop('retry_preparation',None)
    business_only=request.pop('business_only',False)
    business=business_owner.preview(settings,identity,user_id,actor,request)
    # The original signed Business context stays an exact sub-decision.
    inner=json.loads(base64.urlsafe_b64decode(business['review_context']['token'].split('.')[0]))['confirmation']
    if business_only:
        return business
    path,_=preparation_request(settings,identity,user_id,actor,payload,persist=False)
    status=preparation_status(settings,path)
    if status['state']!='prepared':
        raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','正在整理出镜人资料，完成后才能一起确认。')
    prepared=validated_preparation(settings,path)
    if not prepared['people']:return business
    supplied={v['candidate_id']:v for v in person_decisions}
    if len(supplied)!=len(person_decisions) or set(supplied)!={v['candidate_id'] for v in prepared['people']}:
        raise business_owner.fail('SPEAKER_REVIEW_INCOMPLETE','请核对全部已选择出镜人的资料。')
    people=[];public_people=[];blockers=list(business['blockers']);at=datetime.now(timezone.utc).isoformat()
    for person in prepared['people']:
        plan=proposed_person(settings,person,supplied[person['candidate_id']]['decisions'],actor,at)
        from .persona_authority import resolve_persona_authority
        from .speaker_gateway import _latest_intake_dir
        from .speaker_task_service import find_active_speaker_task
        existing=resolve_persona_authority(settings,person['speaker_id'],'speaker').current
        active=find_active_speaker_task(settings.database_path,person['speaker_id'])
        directory=_latest_intake_dir(settings,identity,person['speaker_id'])
        if existing or (directory and directory.name!=person['speaker_request']['intake_id']):
            plan['blockers'].append('已有历史人物版本，请沿原出镜人版本复核入口处理；也可明确选择本次仅确认客户。')
        if active and active['status'] in {'queued','running'}:
            plan['blockers'].append('人物资料仍在整理，完成后再一起确认。')
        # Raw personal materials remain in their immutable local preparation.
        # The signed confirmation binds their digest, without duplicating them
        # into a potentially oversized browser token for multiple people.
        people.append({**{k:v for k,v in person.items() if k!='speaker_request'},
            'speaker_request_sha256':digest(person['speaker_request']),
            **{k:v for k,v in plan.items() if k!='projection'},'projection_sha256':digest(plan['projection'])})
        public_people.append({'candidate_id':person['candidate_id'],'name':person['selection']['speaker_name'],
            'projection':plan['projection'],'blockers':plan['blockers']})
        blockers.extend(f"{person['selection']['speaker_name']}：{v}" for v in plan['blockers'])
    people_blocked=any(v['blockers'] for v in people)
    if blockers:
        inner={**inner,'mode':business_owner.SAVE,'blockers':blockers}
        inner['preview_sha256']=digest({k:v for k,v in inner.items() if k!='preview_sha256'})
    bundle={'schema_version':VERSION,'business_id':identity,'intake_id':inner['intake_id'],
        'business':inner,'preparation_request_ref':business_owner.ref(settings,path),
        'preparation_ref':business_owner.ref(settings,path.parent/'prepared.json'),
        'people':people,'mode':APPROVE if not blockers else business_owner.SAVE,'blockers':blockers,
        'can_submit':not people_blocked and (not blockers or inner['can_submit'])}
    bundle['preview_sha256']=digest(bundle)
    context=review_commands.issue(settings,'business',identity,user_id,confirmation=bundle)
    return {'schema_version':VERSION,'mode':bundle['mode'],'projection':business['projection'],
        'people':public_people,
        'blockers':blockers,'can_submit':bundle['can_submit'],'preview_sha256':bundle['preview_sha256'],
        'review_context':context}


def validate_decision(command):
    bundle=command['context'].get('confirmation')
    payload=read(command['directory']/'intent.json')['intent']['payload'] if command['saved'] else command['intent']
    if (not bundle or bundle.get('schema_version')!=VERSION
            or digest({k:v for k,v in bundle.items() if k!='preview_sha256'})!=bundle.get('preview_sha256')
            or payload.get('confirmation')!=bundle['mode'] or payload.get('preview_sha256')!=bundle['preview_sha256']
            or not bundle.get('can_submit')):
        raise business_owner.fail('CUSTOMER_CONFIRMATION_REQUIRED','请明确确认当前客户及出镜人摘要。')
    return bundle


def _verify_approval(settings,record,reviewer,operation_id):
    receipt=read(business_owner.check_ref(settings,record['approval_receipt_ref']))
    persona=read(business_owner.check_ref(settings,record['persona_ref']))
    decision=read(business_owner.check_ref(settings,record['decision_ref']))
    if (receipt.get('human_gate') is not True or receipt.get('reviewer')!=reviewer
            or receipt.get('persona_sha256_after_approval')!=record['persona_ref']['sha256']
            or receipt.get('review_decision_metadata')!={'decision_artifact_ref':record['decision_ref']}
            or persona.get('approval',{}).get('human_gate') is not True
            or decision.get('operation_id')!=operation_id):
        raise business_owner.fail('REVIEW_COMMIT_CONFLICT','原审批收据与当前操作不一致。')


def execute(settings,command,reviewer,*,on_review):
    from .case_library_access import principal
    bundle=validate_decision(command);context=command['context']
    if command['result'] is not None:
        result=command['result']
        if result.get('schema_version')!=VERSION or result.get('preview_sha256')!=bundle['preview_sha256']:
            raise business_owner.fail('REVIEW_REPLAY_CONFLICT','原联合确认结果不一致。')
        expected={p['speaker_id'] for p in bundle['people']} if bundle['mode']==APPROVE else set()
        if (result.get('operation_id')!=context['operation_id'] or len(result.get('speakers',[]))!=len(expected)
                or {p.get('speaker_id') for p in result.get('speakers',[])}!=expected
                or (bundle['mode']==APPROVE and (result.get('completion')!='customer_and_speakers_approved'
                    or not result.get('business',{}).get('approval_receipt_ref')))):
            raise business_owner.fail('REVIEW_COMMIT_CONFLICT','原操作缺少完整独立审批证明。')
        for record in [result.get('business'),*result.get('speakers',[])]:
            if record and record.get('approval_receipt_ref'):_verify_approval(settings,record,reviewer,context['operation_id'])
        for record in result.get('speakers',[]):
            target=read(business_owner.check_ref(settings,record['decision_ref']))
            if (target['actor']!=context['actor'] or target['preview_sha256']!=bundle['preview_sha256']
                    or target['business_approval_receipt_ref']!=result['business']['approval_receipt_ref']):
                raise business_owner.fail('REVIEW_COMMIT_CONFLICT','人物与客户审批关联不一致。')
        return result
    for key in ('preparation_request_ref','preparation_ref'):business_owner.check_ref(settings,bundle[key])
    prepared=validated_preparation(settings,business_owner.check_ref(settings,bundle['preparation_request_ref']))
    prepared_people={v['candidate_id']:v for v in prepared['people']}
    people_to_commit=[]
    for person in bundle['people']:
        for source in person['artifacts'].values():business_owner.check_ref(settings,source)
        source=prepared_people.get(person['candidate_id'])
        request_sha=person.get('speaker_request_sha256') or digest(person.get('speaker_request'))
        if (not source or digest(source['speaker_request'])!=request_sha
                or source['artifacts']!=person['artifacts'] or source['selection']!=person['selection']
                or source['speaker_id']!=person['speaker_id']):
            raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','人物确认与原整理来源不一致。')
        plan=proposed_person(settings,source,person['decisions'],reviewer,command['at'])
        expected_projection=person.get('projection_sha256') or digest(person.get('projection'))
        if digest(plan['projection'])!=expected_projection or plan['blockers']:
            raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','人物有效摘要与本次明确确认不一致。')
        people_to_commit.append({**person,'speaker_request':source['speaker_request'],'projection':plan['projection']})
    def finish_business(business_result):
        speakers=[]
        if bundle['mode']==APPROVE:
            if principal(settings,context['actor']['user_id'])!=context['actor']:
                raise business_owner.fail('REVIEW_ACTOR_MISMATCH','审核身份已失效。')
            for person in people_to_commit:
                speakers.append(_commit_person(settings,command,bundle,person,reviewer,business_result))
        return review_commands.finish(command,{'schema_version':VERSION,'operation_id':context['operation_id'],
            'preview_sha256':bundle['preview_sha256'],'completion':'customer_and_speakers_approved' if bundle['mode']==APPROVE else business_result['completion'],
            'business':business_result,'speakers':speakers})
    return business_owner.execute(settings,command,reviewer,on_review=on_review,finish_result=finish_business)


def _candidate_meaning(value):
    return sorted((v['fact_candidate_id'],v['target_field'],digest(v.get('normalized_value')),
        v.get('source_ref'),v.get('source_excerpt'),v.get('raw_answer_ref')) for v in value['fact_candidates'])


def _commit_person(settings,command,bundle,person,reviewer,business_result):
    from .operation_lock import operation_lock
    from . import persona_review_gateway
    from .persona_authority import resolve_persona_authority
    from .speaker_gateway import _latest_intake_dir
    from speaker_onboarding_analysis_v1 import analyze_speaker_onboarding
    from speaker_fact_review_v1 import review_speaker_facts
    from .case_library_access import principal
    context=command['context'];sid=person['speaker_id'];bid=bundle['business_id']
    with operation_lock(settings.pipeline_root,f'persona:{bid}:{sid}',timeout_seconds=0):
        if principal(settings,context['actor']['user_id'])!=context['actor']:
            raise business_owner.fail('REVIEW_ACTOR_MISMATCH','当前审核身份已失效。')
        target_file=command['directory']/'speakers'/f'{sid}.json'
        intake=_latest_intake_dir(settings,bid,sid)
        if intake is None:
            raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','客户档案已保留，出镜人建档尚未完成，请继续原操作。')
        raw=read(intake/'speaker_onboarding_request_v1.json')
        if any(raw.get(k)!=person['speaker_request'].get(k) for k in (
                'business_id','speaker_id','intake_id','speaker_name','public_role','speaker_type','materials','forbidden_claims')):
            raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','已保存人物资料与本次确认不同，需要重新核对。')
        if not target_file.is_file():
            extraction=read(business_owner.check_ref(settings,person['artifacts']['extraction']))
            analyze_speaker_onboarding(request=raw,pipeline_root=settings.pipeline_root,extractor=lambda _:extraction,
                prepared_extraction_ref=person['artifacts']['extraction'])
            actual=read(intake/'speaker_fact_candidates_v1.json')
            staged=read(business_owner.check_ref(settings,person['artifacts']['candidates']))
            if _candidate_meaning(actual)!=_candidate_meaning(staged):
                raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','人物实际整理结果与已确认摘要不同。')
            required={v['fact_candidate_id'] for v in actual['fact_candidates'] if v['candidate_state']=='requires_review'}
            reviewed=review_speaker_facts(request={'business_id':bid,'speaker_id':sid,'intake_id':intake.name,
                'reviewer':reviewer,'note':'','decisions':[v for v in person['decisions'] if v['candidate_id'] in required]},
                pipeline_root=settings.pipeline_root)
            if reviewed['status']!='completed_persona_review_required':
                raise business_owner.fail('SPEAKER_PREPARATION_REQUIRED','人物资料尚不满足批准要求，客户批准记录已保留。')
            target=resolve_persona_authority(settings,sid,'speaker').review_candidate
            if not target or speaker_projection(target['artifact'])!=person['projection']:
                raise business_owner.fail('CUSTOMER_CONFIRMATION_STALE','人物档案与确认摘要不一致。')
            write_once(target_file,{'schema_version':VERSION,'operation_id':context['operation_id'],
                'actor':context['actor'],'preview_sha256':bundle['preview_sha256'],
                'intent_ref':business_owner.ref(settings,command['directory']/'intent.json'),
                'business_approval_receipt_ref':business_result['approval_receipt_ref'],
                'preparation_ref':bundle['preparation_ref'],'fact_review_ref':business_owner.ref(settings,intake/'speaker_fact_review_v1.json'),
                'snapshot':review_commands.snapshot(settings,'speaker',sid,business_id=bid)})
        target=read(target_file)
        if (target['operation_id']!=context['operation_id'] or target['actor']!=context['actor']
                or target['preview_sha256']!=bundle['preview_sha256']):
            raise business_owner.fail('REVIEW_REPLAY_CONFLICT','人物审批提交身份不一致。')
        for key in ('intent_ref','business_approval_receipt_ref','preparation_ref','fact_review_ref'):
            business_owner.check_ref(settings,target[key])
        derived={**command,'context':{**context,'snapshot':target['snapshot'],'kind':'speaker','identity':sid,'business_id':bid}}
        decision_ref=business_owner.ref(settings,target_file)
        if principal(settings,context['actor']['user_id'])!=context['actor']:
            raise business_owner.fail('REVIEW_ACTOR_MISMATCH','人物审核身份已失效。')
        persona_review_gateway.approve(settings,derived,'speaker',sid,bid,reviewer,'',decision_metadata={'decision_artifact_ref':decision_ref})
        path=settings.pipeline_root/target['snapshot']['artifact']
        result={'speaker_id':sid,'approval_receipt_ref':business_owner.ref(settings,path.parent/'approval_receipt.json'),
            'persona_ref':business_owner.ref(settings,path),'decision_ref':decision_ref}
        _verify_approval(settings,result,reviewer,context['operation_id'])
        from .speaker_task_service import mark_speaker_task_reviewed
        mark_speaker_task_reviewed(settings.database_path,sid)
        return result
