"""News target verification delegated by Production Profile, no separate store."""
from pathlib import Path
from profile_compatibility_contract_v1_1 import CompatibilityError,validate
from profile_compatibility_contract_v1_2 import TARGET
from profile_compatibility_decisions_v1_1 import (DOMAIN,read,ref,resolve_ref,write_once,
    write_bytes_once,file_sha,digest)


def native_audit(root,case_id,case_ref,case_approval_ref,fingerprint_ref,storyboard_ref):
    case=read(resolve_ref(root,case_ref));approval=read(resolve_ref(root,case_approval_ref))
    fp=read(resolve_ref(root,fingerprint_ref));board=read(resolve_ref(root,storyboard_ref))
    from case_human_review_v2 import validate_quality_record
    validate_quality_record(case,approval)
    if (case.get('case_id')!=case_id or case.get('lifecycle',{}).get('approved') is not True
        or case.get('quality',{}).get('human_review_completed') is not True
        or approval.get('case_sha256_after_approval')!=case_ref['sha256']
        or approval.get('human_gate') is not True or approval.get('decision')!='approved'
        or approval.get('frozen_artifacts',{}).get('reverse_storyboard_v1',{}).get('sha256')!=storyboard_ref['sha256']
        or case.get('storyboard',{}).get('artifact',{}).get('sha256')!=storyboard_ref['sha256']):
        raise CompatibilityError('News source is not bound to exact Native Case Human Approval')
    carrier=fp.get('semantic_carrier_features',{})
    beats=board.get('micro_beat_sequence') or []
    if (fp.get('schema_version')!='case-fingerprint-news-v1.2' or fp.get('case_id')!=case_id
        or fp.get('source_case_sha256')!=case_ref['sha256'] or fp.get('source_storyboard_sha256')!=storyboard_ref['sha256']
        or fp.get('fingerprint_scope')!='case_structural_evidence_only'
        or fp.get('authority',{}).get('case_specific_facts_transferred') is not False
        or fp.get('pattern_state')!={'pattern_mining_performed':False,'pattern_created':False}
        or board.get('schema_version')!='reverse-storyboard-v1.2-news-micro-beat'
        or board.get('case_id')!=case_id or carrier.get('continuous_narration_required') is not False
        or len(beats)<2 or carrier.get('micro_beat_count')!=len(beats)
        or carrier.get('role_sequence')!=[b.get('semantic_role') for b in beats]):
        raise CompatibilityError('Native News Fingerprint/Micro-beat frozen source mismatch')
    price_first=beats[0].get('semantic_role')=='price_or_offer_anchor'
    return {'assessment_version':'case-profile-compatibility-assessment-v1.2','case_id':case_id,
        'observed_source_profile':'news','compatible_generation_profiles_candidate':['news'] if price_first else [],
        'approved_compatible_generation_profiles':[],'review_status':'review_required',
        'structural_evidence':{'price_offer_first':price_first,'micro_beat_count':len(beats),
            'continuous_narration_required':False,'scope_limitation':'price_offer_led_only'},
        'lineage':{'case_ref':case_ref,'case_approval_ref':case_approval_ref,
            'fingerprint_ref':fingerprint_ref,'storyboard_ref':storyboard_ref},
        'authority':{'assessment_changes_compatibility':False,'case_facts_transferred':False,
            'media_rights_granted':False,'remote_model_called':False}}


def validate_target(root,target):
    validate(target,TARGET)
    cid=target['case_id']
    for name,expected in [('case_ref',f'data/cases/{cid}/case_v1.json'),
        ('case_approval_ref',f'data/cases/{cid}/approval_receipt.json'),
        ('fingerprint_ref',f'data/fingerprints/{cid}/case_fingerprint_v1.json')]:
        if target[name]['path']!=expected:raise CompatibilityError('News target must name its canonical current source')
    from news_pattern_authority_v1_1 import validate_pattern
    pattern,receipt=validate_pattern(root,target['pattern_ref'],target['pattern_approval_ref'])
    if (pattern['pattern_id']!=target['pattern_id']
        or target['pattern_id']!='pcv1_news_price_offer_led_micro_information'
        or target['pattern_ref']['path']!=f"data/patterns/approved/{target['pattern_id']}/versions/{receipt['operation_id']}/pattern_v1.json"
        or target['pattern_approval_ref']['path']!=target['pattern_ref']['path'].rsplit('/',1)[0]+'/approval_receipt.json'
        or target['profile_ref']!=receipt['profile_ref'] or target['rules_ref']!=receipt['rules_ref']):
        raise CompatibilityError('News Pattern/profile version or canonical domain differs')
    support=next((x for x in receipt['supporting_cases'] if x['case_id']==cid),None)
    if not support or any(target[k]!=support[k] for k in ('case_ref','case_approval_ref','fingerprint_ref','storyboard_ref')):
        raise CompatibilityError('New Case is outside the exact independently approved Pattern scope')
    audit=native_audit(root,cid,**{k:target[k] for k in ('case_ref','case_approval_ref','fingerprint_ref','storyboard_ref')})
    if read(resolve_ref(root,target['audit_ref']))!=audit or audit['compatible_generation_profiles_candidate']!=['news']:
        raise CompatibilityError('News audit changed or does not support the narrow requested profile')
    return target


def prepare_target(root,*,case_id,pattern_ref,pattern_approval_ref,profile_ref,rules_ref):
    root=Path(root).resolve();case_dir=root/'data/cases'/case_id;case=read(case_dir/'case_v1.json')
    raw=Path(case['storyboard']['artifact']['path'])
    if file_sha(raw)!=case['storyboard']['artifact']['sha256']:
        raise CompatibilityError('Native Storyboard changed')
    frozen=root/DOMAIN/'sources'/file_sha(raw)/'storyboard.json';write_bytes_once(frozen,raw.read_bytes())
    sources={'case_ref':ref(root,case_dir/'case_v1.json'),'case_approval_ref':ref(root,case_dir/'approval_receipt.json'),
        'fingerprint_ref':ref(root,root/'data/fingerprints'/case_id/'case_fingerprint_v1.json'),'storyboard_ref':ref(root,frozen)}
    audit=native_audit(root,case_id,**sources)
    path=root/DOMAIN/'evidence'/(digest(audit)+'.json');write_once(path,audit)
    target={'case_id':case_id,'pattern_id':read(resolve_ref(root,pattern_ref))['pattern_id'],'target_profile':'news',
        **sources,'pattern_ref':pattern_ref,'pattern_approval_ref':pattern_approval_ref,
        'profile_ref':profile_ref,'rules_ref':rules_ref,'audit_ref':ref(root,path)}
    return validate_target(root,target)
