"""Versioned trusted operations delegated by the original research/Pattern owners.

No Registry is an approval input. Native comparison/candidate/Pattern semantics
remain in their existing owners; this companion binds explicit local principals.
"""
from datetime import datetime,timezone
from pathlib import Path
from profile_compatibility_contract_v1_1 import CompatibilityError,OPERATION,validate
from profile_compatibility_contract_v1_2 import (PATTERN_CAPABILITY,RESEARCH_RECEIPT,
    PATTERN_INTENT,PATTERN_RECEIPT,PROFILE,RULES,validate_contract)
from profile_compatibility_authorization_v1 import authorization,validate_grant_proof
from profile_compatibility_decisions_v1_1 import (read,ref,resolve_ref,write_once,digest,
    file_sha,reviewer_operation,DOMAIN,write_bytes_once)


def reviewer_name(actor):
    return f"principal:{actor['namespace']}:{actor['user_id']}"


def validate_production_purpose_review(value):
    """Versioned purpose extension only; the old isolated receipt stays unchanged."""
    from production_admission_v1 import PATTERN_SCHEMA
    validate(value, PATTERN_SCHEMA)
    validate_grant_proof(value['authorization'], capability=PATTERN_CAPABILITY)
    if value['actor'] != value['authorization']['principal']:
        raise CompatibilityError('Pattern production-purpose review principal differs')
    keys = [digest(item) for item in value['patterns']]
    if keys != sorted(set(keys)):
        raise CompatibilityError('Pattern production-purpose scope must be exact and unique')
    return value


def prepare_production_purpose_review(root, database_path, actor, operation_id, targets):
    from production_admission_v1 import PATTERN_REVIEW
    patterns = {digest({k: target[k] for k in ('pattern_ref','pattern_approval_ref')}):
                {k: target[k] for k in ('pattern_ref','pattern_approval_ref')} for target in targets}
    for item in patterns.values():
        validate_pattern(root, item['pattern_ref'], item['pattern_approval_ref'])
    value = {'schema_version': PATTERN_REVIEW, 'operation_id': operation_id, 'actor': actor,
        'authorization': authorization(database_path, actor, capability=PATTERN_CAPABILITY),
        'decision': 'approve_exact_production_purpose', 'patterns': [patterns[k] for k in sorted(patterns)],
        'purpose': 'production', 'case_scope_expanded': False, 'customer_truth_created': False,
        'human_confirmation_required': True, 'at': datetime.now(timezone.utc).isoformat()}
    return validate_production_purpose_review(value)


def confirm_production_purpose_review(root, database_path, actor, proposal):
    """Called only inside the original Release review's locked Human confirmation."""
    from production_admission_v1 import PATTERN_DECISION,check
    validate_production_purpose_review(proposal)
    if (proposal['actor'] != actor or authorization(database_path, actor, capability=PATTERN_CAPABILITY)
            != proposal['authorization']):
        raise CompatibilityError('Pattern production-purpose permission changed')
    for item in proposal['patterns']:
        validate_pattern(root, item['pattern_ref'], item['pattern_approval_ref'])
    path = Path(root)/'data/patterns/production_purpose_operations'/proposal['operation_id']/'decision.json'
    old = read(path) if path.is_file() else None
    receipt = {**proposal, 'schema_version': PATTERN_DECISION, 'human_gate': True,
        'confirmed_at': old['confirmed_at'] if old else datetime.now(timezone.utc).isoformat()}
    write_once(path, check(receipt, PATTERN_DECISION))
    return ref(root,path)


def profile_sources(root,profile_ref,rules_ref):
    from production_profile_v1 import declared_news_profile_v1_2
    p=validate_contract(read(resolve_ref(root,profile_ref)),PROFILE)
    r=validate_contract(read(resolve_ref(root,rules_ref)),RULES)
    if p!=declared_news_profile_v1_2(p['export_contract']['template_ref']) or r['profile_sha256']!=profile_ref['sha256']:
        raise CompatibilityError('Pure News Profile/rules changed')
    resolve_ref(root,p['export_contract']['template_ref'])
    return p,r


def supporting_cases(root,comparison):
    cases=[]
    for case_id,item in sorted(comparison['input_artifacts'].items()):
        paths={}
        for source,key in [('approved_case_ref','case_ref'),('fingerprint_ref','fingerprint_ref'),('storyboard_ref','storyboard_ref')]:
            path=Path(item[source]['path']).resolve()
            if file_sha(path)!=item[source]['sha256']:
                raise CompatibilityError('Research source changed')
            paths[key]=ref(root,path)
            if key=='storyboard_ref':
                frozen=Path(root)/DOMAIN/'sources'/paths[key]['sha256']/'storyboard.json'
                write_bytes_once(frozen,path.read_bytes())
                paths[key]=ref(root,frozen)
        receipt=Path(root)/'data/cases'/case_id/'approval_receipt.json'
        paths['case_approval_ref']=ref(root,receipt)
        case=read(resolve_ref(root,paths['case_ref']));approval=read(receipt)
        if (paths['case_ref']['path']!=f'data/cases/{case_id}/case_v1.json'
            or approval.get('human_gate') is not True or approval.get('decision')!='approved'
            or approval.get('case_sha256_after_approval')!=paths['case_ref']['sha256']
            or case.get('lifecycle',{}).get('approved') is not True
            or approval.get('frozen_artifacts',{}).get('reverse_storyboard_v1',{}).get('sha256')!=paths['storyboard_ref']['sha256']):
            raise CompatibilityError('Native Case Human Approval or frozen Micro-beat source is missing')
        cases.append({'case_id':case_id,**paths})
    if len(cases)!=3:raise CompatibilityError('Three independent Approved News Cases required')
    return cases


def research_context(comparison_path,context):
    required={'root','database_path','actor','operation_id','profile_ref','rules_ref'}
    if set(context)!=required:raise CompatibilityError('Trusted research operation context required')
    root=Path(context['root']).resolve();validate(context['operation_id'],OPERATION)
    proof=authorization(context['database_path'],context['actor'],capability=PATTERN_CAPABILITY)
    profile_sources(root,context['profile_ref'],context['rules_ref'])
    comparison=read(comparison_path)
    if comparison.get('research_direction')!='price_offer_led_micro_information':
        raise CompatibilityError('Only the approved narrow price/offer News scope is supported')
    value={**context,'authorization':proof,'comparison_ref':ref(root,comparison_path),
           'supporting_cases':supporting_cases(root,comparison),'reviewer':reviewer_name(context['actor'])}
    target=root/'data/patterns/research_operations'/context['operation_id']/'approval.json'
    old=read(target) if target.is_file() else None
    if old:
        validate_contract(old,RESEARCH_RECEIPT)
        for key in ('operation_id','actor','authorization','comparison_ref','profile_ref','rules_ref','supporting_cases'):
            if old[key]!=value[key]:raise CompatibilityError('Research operation identity or grant changed')
    value['decided_at']=old['decided_at'] if old else datetime.now(timezone.utc).isoformat()
    return value


def research_record(native_review,context):
    value={'schema_version':RESEARCH_RECEIPT,
        **{k:context[k] for k in ('operation_id','actor','authorization','comparison_ref','profile_ref','rules_ref','supporting_cases','decided_at')},
        'decision':'approve_research_comparison','approval_scope':'research_comparison_only_not_pattern_approval',
        'human_gate':True,'native_review':native_review}
    return validate_contract(value,RESEARCH_RECEIPT)


def research_projection(record,expected_sha=None):
    validate_contract(record,RESEARCH_RECEIPT)
    validate_grant_proof(record['authorization'],capability=PATTERN_CAPABILITY)
    native=record['native_review'];reviewer=reviewer_name(record['actor'])
    if (record['actor']!=record['authorization']['principal']
        or native.get('reviewer')!=reviewer or native.get('reviewed_at')!=record['decided_at']
        or native.get('comparison_ref',{}).get('sha256')!=record['comparison_ref']['sha256']
        or (expected_sha and record['comparison_ref']['sha256']!=expected_sha)):
        raise CompatibilityError('Trusted research provenance mismatch')
    return reviewer,native


def approve_research(root,database_path,actor,operation_id,comparison_ref,profile_ref,rules_ref):
    from compare_approved_cases_v1 import build_comparison_human_approval
    with reviewer_operation(root,actor):
        context={'root':root,'database_path':database_path,'actor':actor,'operation_id':operation_id,
                 'profile_ref':profile_ref,'rules_ref':rules_ref}
        value=build_comparison_human_approval(resolve_ref(root,comparison_ref),reviewer=reviewer_name(actor),trusted_context=context)
        path=Path(root)/'data/patterns/research_operations'/operation_id/'approval.json'
        write_once(path,value)
        return ref(root,path)


def pattern_context(candidate_path,profile_path,context):
    required={'root','database_path','actor','operation_id','rules_ref'}
    if set(context)!=required:raise CompatibilityError('Trusted Pattern operation context required')
    root=Path(context['root']).resolve();validate(context['operation_id'],OPERATION)
    profile_ref=ref(root,profile_path);profile_sources(root,profile_ref,context['rules_ref'])
    proof=authorization(context['database_path'],context['actor'],capability=PATTERN_CAPABILITY)
    candidate=read(candidate_path);lineage=candidate['lineage']
    comparison_path=Path(lineage['comparison_ref']['path']);research_path=Path(lineage['comparison_human_approval_ref']['path'])
    comparison=read(comparison_path);research=read(research_path)
    from compare_approved_cases_v1 import validate_comparison_human_approval
    validate_comparison_human_approval(research,expected_comparison_sha256=file_sha(comparison_path))
    if research.get('schema_version')!=RESEARCH_RECEIPT:
        raise CompatibilityError('New Pattern requires independently authenticated research approval')
    from mine_pattern_candidates_v1 import build_news_pattern_candidate
    if candidate!=build_news_pattern_candidate(comparison_path,research_path):
        raise CompatibilityError('Candidate differs from the native comparison/research projection')
    value={**context,'authorization':proof,'pattern_id':candidate['pattern_id'],
        'candidate_ref':ref(root,candidate_path),'comparison_ref':ref(root,comparison_path),
        'research_approval_ref':ref(root,research_path),'profile_ref':profile_ref,
        'supporting_cases':supporting_cases(root,comparison),'reviewer':reviewer_name(context['actor'])}
    for key in ('profile_ref','rules_ref','supporting_cases'):
        if value[key]!=research[key]:raise CompatibilityError('Pattern and research scopes or source versions differ')
    path=root/'data/patterns/approval_operations'/context['operation_id']/'intent.json'
    old=read(path) if path.is_file() else None
    if old:
        validate_contract(old,PATTERN_INTENT)
        for k in old:
            if k not in {'schema_version','decision','human_gate','decided_at'} and old[k]!=value[k]:
                raise CompatibilityError('Pattern operation payload or grant conflicts')
    value['decided_at']=old['decided_at'] if old else datetime.now(timezone.utc).isoformat()
    return value


def approve_pattern(root,database_path,actor,operation_id,candidate_ref,profile_ref,rules_ref):
    from approve_pattern_v1 import build_news_approved_pattern
    context={'root':root,'database_path':database_path,'actor':actor,'operation_id':operation_id,'rules_ref':rules_ref}
    with reviewer_operation(root,actor):
        candidate=resolve_ref(root,candidate_ref);profile=resolve_ref(root,profile_ref)
        verified=pattern_context(candidate,profile,context)
        intent={'schema_version':PATTERN_INTENT,'decision':'approve','human_gate':True,
                **{k:verified[k] for k in ('operation_id','actor','authorization','pattern_id','decided_at',
                    'candidate_ref','comparison_ref','research_approval_ref','profile_ref','rules_ref','supporting_cases')}}
        directory=Path(root)/'data/patterns/approval_operations'/operation_id
        intent_path=directory/'intent.json';write_once(intent_path,validate_contract(intent,PATTERN_INTENT))
        pattern,_=build_news_approved_pattern(candidate,profile,reviewer=reviewer_name(actor),trusted_context=context)
        approved=Path(root)/'data/patterns/approved'/pattern['pattern_id']/'versions'/operation_id
        pattern_path=approved/'pattern_v1.json';write_once(pattern_path,pattern)
        receipt={**intent,'schema_version':PATTERN_RECEIPT,'intent_ref':ref(root,intent_path),
                 'approved_pattern':ref(root,pattern_path)}
        receipt_path=approved/'approval_receipt.json';write_once(receipt_path,validate_contract(receipt,PATTERN_RECEIPT))
        return {'pattern_ref':ref(root,pattern_path),'pattern_approval_ref':ref(root,receipt_path)}


def validate_pattern(root,pattern_ref,receipt_ref):
    """Portable Reader: resolve exact versioned refs inside the supplied bundle."""
    from approve_pattern_v1 import validate_news_approved_pattern
    receipt=validate_contract(read(resolve_ref(root,receipt_ref)),PATTERN_RECEIPT)
    pattern=read(resolve_ref(root,pattern_ref));validate_news_approved_pattern(pattern)
    validate_grant_proof(receipt['authorization'],capability=PATTERN_CAPABILITY)
    intent=validate_contract(read(resolve_ref(root,receipt['intent_ref'])),PATTERN_INTENT)
    if (receipt['approved_pattern']!=pattern_ref or receipt['actor']!=receipt['authorization']['principal']
        or any(receipt[k]!=v for k,v in intent.items() if k!='schema_version')
        or receipt['pattern_id']!=pattern['pattern_id']):
        raise CompatibilityError('Pattern Human decision/intent lineage mismatch')
    profile_sources(root,receipt['profile_ref'],receipt['rules_ref'])
    research=read(resolve_ref(root,receipt['research_approval_ref']))
    from compare_approved_cases_v1 import validate_comparison_human_approval
    validate_comparison_human_approval(research,expected_comparison_sha256=receipt['comparison_ref']['sha256'])
    resolve_ref(root,receipt['candidate_ref']);resolve_ref(root,receipt['comparison_ref'])
    for item in receipt['supporting_cases']:
        for k,v in item.items():
            if k.endswith('_ref'):resolve_ref(root,v)
        case_sha=item['case_ref']['sha256'];cid=item['case_id']
        approval=read(resolve_ref(root,item['case_approval_ref']))
        if (approval.get('human_gate') is not True or approval.get('case_sha256_after_approval')!=case_sha
            or pattern.get('lineage',{}).get('supporting_case_sha256',{}).get(cid)!=case_sha
            or pattern['lineage']['supporting_fingerprint_sha256'].get(cid)!=item['fingerprint_ref']['sha256']
            or pattern['lineage']['supporting_micro_beat_storyboard_sha256'].get(cid)!=item['storyboard_ref']['sha256']):
            raise CompatibilityError('Pattern exact support map changed')
    if sorted(pattern['scope']['supported_case_ids'])!=sorted(x['case_id'] for x in receipt['supporting_cases']):
        raise CompatibilityError('Pattern approved scope cannot expand')
    return pattern,receipt
