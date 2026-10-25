"""Shared effective News admission, delegated to the original native consumers."""
from pathlib import Path
from contextlib import contextmanager
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import read,resolve_ref,file_sha
from profile_compatibility_release_v1_1 import CONFIG,effective_runtime,runtime_write
from profile_compatibility_release_v1_2 import binding as make_binding


def configured(root):
    path=Path(root)/CONFIG
    if not path.is_file():return False
    config=read(path)
    return config.get('schema_version')=='compatibility-runtime-config-v1.2' or (
        config.get('schema_version')=='compatibility-runtime-config-v1.3' and 'news' in config.get('profiles',[]))


def current(root,*,reuse_intent='novel_content',pinned=None):
    from news_qualification_v1_2 import read_context
    scope=read_context(root)
    if scope:
        if pinned is not None and pinned!=scope['binding']:
            raise CompatibilityError('Read-only qualification cannot change its exact source binding')
        if reuse_intent!=scope['binding']['reuse_intent']:
            raise CompatibilityError('Read-only qualification cannot change its native route')
        return scope['active'],scope['binding']
    if pinned is not None:
        import profile_compatibility_contract_v1_2 as contract
        if pinned.get('schema_version')=='profile-compatibility-runtime-binding-v1.3':
            import profile_compatibility_contract_v1_3 as contract
        contract.validate_contract(pinned,contract.BINDING)
        if pinned['target_profile']!='news':raise CompatibilityError('News requires its own independent binding')
    active=effective_runtime(root,pinned=pinned)
    if active['manifest'].get('schema_version')=='creative-authority-release-v1.3':
        from profile_compatibility_release_v1_3 import binding
        return active,binding(active,reuse_intent)
    if active['manifest'].get('schema_version')!='creative-authority-release-v1.2':
        raise CompatibilityError('News cannot consume a Mix-only or legacy release')
    return active,make_binding(active,reuse_intent)


def sources(root,plan):
    pinned=plan.get('profile_compatibility_v1_2')
    if not pinned or plan.get('profile_compatibility_v1_1'):
        raise CompatibilityError('New News source cannot downgrade or combine compatibility contracts')
    active,_=current(root,pinned=pinned,reuse_intent=pinned['reuse_intent'])
    bundle=active['bundle_root']
    return active,resolve_ref(bundle,pinned['pattern_ref']),{
        s['case_id']:resolve_ref(bundle,s['fingerprint_ref']) for s in pinned['structural_sources']}


def validate_personas(root,business_path,speaker_path,*,consumer='novel_news'):
    from show_customer_status_v1 import resolve_current_persona,resolve_speaker_persona
    from customer_constraints_v1 import assert_production_allowed
    b=read(business_path);business=resolve_current_persona(Path(root),b['persona_id'],'business')
    speaker=resolve_speaker_persona(Path(root),business,read(speaker_path)['persona_id'])
    if Path(business['path']).resolve()!=Path(business_path).resolve() or Path(speaker['path']).resolve()!=Path(speaker_path).resolve():
        raise CompatibilityError('Current Approved Business/Speaker version differs from the pinned source')
    for p in (business,speaker):assert_production_allowed(p['artifact'],p['path'],consumer=consumer)
    return business,speaker


def validate_request_personas(root,request):
    lineage=request.get('lineage') or {}
    novel=request.get('reuse_intent')=='novel_content'
    br=lineage.get('business_persona_ref' if novel else 'business_persona') or {}
    sr=lineage.get('speaker_persona_ref' if novel else 'speaker_persona') or {}
    sha_key='file_sha256' if novel else 'sha256'
    for item in (br,sr):
        if not item.get('path') or file_sha(item['path'])!=item.get(sha_key):
            raise CompatibilityError('Native News Request Persona source changed')
    return validate_personas(root,Path(br['path']),Path(sr['path']),
        consumer='novel_news' if novel else 'news_repurpose')


def feasibility(root,business_path,speaker_path,quantity,selected_content=None,reuse_intent='novel_content'):
    active,pinned=current(root,reuse_intent=reuse_intent)
    business,speaker=validate_personas(root,business_path,speaker_path)
    facts=business['artifact'].get('facts',{})
    price=facts.get('pricing_facts',{})
    from generate_mix_scripts_v1 import safe_persona_projection
    from close_generation_export_v1 import _build_fact_atoms
    from novel_news_opportunity_v1 import SUPPORT_FIELDS
    fields=set(safe_persona_projection(business['artifact'])['facts'])&({'pricing_facts'}|set(SUPPORT_FIELDS))
    atoms=_build_fact_atoms(business['artifact'],file_sha(business_path),speaker['artifact'],file_sha(speaker_path))
    independent={str(a.get('normalized_meaning') or a['original_known_fact']).strip()
        for a in atoms if a.get('field') in fields}
    valid=(quantity==1 and price.get('state')=='known' and bool(str(price.get('value') or '').strip())
        and len(independent)>=4 and (selected_content is None or 'pricing_facts' in selected_content.get('primary_fact_refs',[])))
    production=active['manifest'].get('schema_version')=='creative-authority-release-v1.3'
    return {'status':'supported' if valid else 'unsupported','blocker_type':None if valid else 'NEWS_PRICE_SOURCE_REQUIRED',
        'blocker_codes':[] if valid else ['NEWS_PRICE_SOURCE_REQUIRED'],
        'humanized_reason':('已批准结构可用于本次受限新闻体创作。' if production else '已批准结构可用于本次隔离新闻体验证。') if valid else '请先核实价格及适用条件，并选择一条价格内容方向。',
        'optional_customer_truth_route':None,'requested_quantity':quantity,'supported_quantity':1 if valid else 0,
        'selected_pattern_count':1 if valid else 0,'eligible_case_count':len(pinned['structural_sources']) if valid else 0,
        'authority':{'generation_request_created':False,'source_plan_written':False,'matching_core':'native News v1.2 effective graph',
            'production_eligibility_granted':production},'profile_compatibility_v1_2':pinned}


def source_plan(root,request_path,request):
    from match_generation_sources_v1 import write_source_plan
    root=Path(root);pinned=request.get('profile_compatibility_v1_2')
    if not pinned or request.get('profile_compatibility_v1_1'):
        raise CompatibilityError('News Request has no exact v1.2 admission')
    active,_=current(root,pinned=pinned)
    lineage=request['lineage'];bp=Path(lineage['business_persona_ref']['path']);sp=Path(lineage['speaker_persona_ref']['path'])
    for path,key in ((bp,'business_persona_ref'),(sp,'speaker_persona_ref')):
        if file_sha(path)!=lineage[key]['file_sha256']:raise CompatibilityError('News Persona source changed')
    checked=feasibility(root,bp,sp,request['quantity'],request.get('selected_content'))
    if checked['status']!='supported':raise CompatibilityError(checked['humanized_reason'])
    pattern=read(resolve_ref(active['bundle_root'],pinned['pattern_ref']))
    plan={'schema_version':'generation-source-plan-v1.0','request_id':request['request_id'],
        'created_at':request['created_at'],'profile_compatibility_v1_2':pinned,
        'request':{'request_id':request['request_id'],'request_sha':file_sha(request_path),'profile':'news','quantity':1},
        'persona':{'path':str(bp),'file_sha256':file_sha(bp)},
        'speaker_persona':{'path':str(sp),'file_sha256':file_sha(sp)},
        'selected_patterns':[{'pattern_id':pattern['pattern_id'],'approved_pattern_sha':pinned['pattern_ref']['sha256'],
            'compatible_profiles':['news'],'scope':'price_offer_led_only'}],
        'eligible_case_pool':[{'case_id':s['case_id'],'approved_case_sha':s['case_ref']['sha256'],
            'fingerprint_sha':s['fingerprint_ref']['sha256'],'compatible_profiles':['news']} for s in pinned['structural_sources']],
        'coverage':{'status':'supported','code':'NEWS_ISOLATED_STRUCTURAL_COVERAGE','blocker_type':None,
            'humanized_reason':checked['humanized_reason']},'feasibility':checked,
        'authority':{'case_facts_transferred':False,'media_rights_granted':False,'customer_truth_created':False}}
    path=root/'data/production_plans'/request['request_id']/'generation_source_plan_v1.json';existed=path.is_file()
    path,sha=write_source_plan(plan,root/'data/production_plans')
    return {'ok':True,'request_id':request['request_id'],'source_plan_path':str(path),'source_plan_sha256':sha,
        'coverage_status':'supported','coverage_code':'NEWS_ISOLATED_STRUCTURAL_COVERAGE',
        'selected_pattern_count':1,'eligible_case_count':len(pinned['structural_sources']),
        'blocker_type':None,'blocker_codes':[],'humanized_reason':checked['humanized_reason'],
        'optional_customer_truth_route':None,'remote_model_called':False,'script_generation_performed':False,
        'generation_batch_created':False,'content_ledger_written':False,'recovered':existed}
