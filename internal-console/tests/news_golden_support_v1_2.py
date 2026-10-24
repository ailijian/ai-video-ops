"""Fresh fictional sources; native Case, research and Pattern Human Gates."""
import os,subprocess,uuid,shutil
from pathlib import Path
from app.case_library_access import principal
from app.profile_compatibility_gateway import manage_reviewer
from app.task_service import update_task
from profile_compatibility_decisions_v1_1 import write_once,ref,read
from test_case_share_joint_v1 import payload


def prepare_news_pattern(node):
    settings,accounts,storage=node;root=settings.pipeline_root
    project=Path(__file__).resolve().parents[2]
    python=project/'ops-pipeline/.venv/Scripts/python.exe'
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','QYAPI_','AIVO_'))}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    ids=['7999999999999999861','7999999999999999862','7999999999999999863'];cases=[]
    for cid in ids:
        client,headers,_=accounts['A']
        response=client.post('/api/case-intake/groups',headers=headers,json={
            'client_request_id':str(uuid.uuid4()),'text':f'https://www.douyin.com/video/{cid}'})
        assert response.status_code==200,response.text
        task=response.json()['items'][0]['task']
        command=[str(python),str(project/'ops-pipeline/tests/news_case_synthetic.py'),str(root),cid,task['task_id']]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',env=env,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        update_task(settings.database_path,task['task_id'],status='awaiting_review',progress=100)
        url='/api/cases/'+cid
        ctx=client.get(url+'/classification').json()
        response=client.post(url+'/classification',headers=headers,json={'industry':'餐饮','profile':'news',
            'candidate_sha256':ctx['candidate_sha256'],'expected_confirmation_sha256':ctx['confirmation_sha256']})
        assert response.status_code==200,response.text
        reviewer,rh,_=accounts['C'];detail=reviewer.get(url).json()
        response=reviewer.post(url+'/review',headers=rh,json=payload(detail))
        assert response.status_code==200,response.text
        case=root/'data/cases'/cid/'case_v1.json';value=read(case)
        assert value['lifecycle']['approved'] and value['storyboard']['micro_beat_sequence']
        result=subprocess.run([str(python),str(root/'scripts/build_case_fingerprint_v1.py'),'--case',str(case),
            '--output-root',str(root/'data/fingerprints')],capture_output=True,text=True,encoding='utf-8',env=env,timeout=60)
        assert result.returncode==0,result.stdout+result.stderr
        cases.append(ref(root,case))
    template=root/'output/新闻体视频制作文案导入模板.xlsx'
    template.parent.mkdir(parents=True,exist_ok=True)
    if not template.exists():shutil.copyfile(project/'ops-pipeline/output/新闻体视频制作文案导入模板.xlsx',template)
    from production_profile_v1 import initialize_news_profile_v1_2,build_news_research_bundle_v1_2
    definitions=initialize_news_profile_v1_2(root,template)
    bundle=build_news_research_bundle_v1_2(root,ids)
    operation=uuid.uuid4().hex;directory=root/'data/comparisons/news'/operation
    bp=directory/'bundle.json';write_once(bp,bundle)
    from compare_approved_cases_v1 import build_generalized_research_comparison
    cp=directory/'comparison.json';write_once(cp,build_generalized_research_comparison(bp))
    from news_pattern_authority_v1_1 import approve_research,approve_pattern,validate_pattern
    from profile_compatibility_contract_v1_2 import PATTERN_CAPABILITY
    actor=principal(settings,3)
    manage_reviewer(settings,3,action='grant',operator='isolated-native-news-fixture',
        reason='Independent explicit review of new fictional News Case structure',capability=PATTERN_CAPABILITY)
    research=approve_research(root,settings.database_path,actor,uuid.uuid4().hex,ref(root,cp),**definitions)
    from mine_pattern_candidates_v1 import build_news_pattern_candidate
    candidate=build_news_pattern_candidate(cp,root/research['path'])
    candidate_path=root/'data/patterns/candidates'/operation/'pattern_candidate_v1.json';write_once(candidate_path,candidate)
    pattern=approve_pattern(root,settings.database_path,actor,uuid.uuid4().hex,ref(root,candidate_path),**definitions)
    validate_pattern(root,**{'pattern_ref':pattern['pattern_ref'],'receipt_ref':pattern['pattern_approval_ref']})
    return {'case_ids':ids,'cases':cases,'research_ref':research,'candidate_ref':ref(root,candidate_path),
            'comparison_ref':ref(root,cp),**definitions,**pattern,'actor':actor}


def prepare_news_compatibility(node):
    result=prepare_news_pattern(node);settings,accounts,storage=node;root=settings.pipeline_root
    from profile_compatibility_news_v1_2 import prepare_target
    from profile_compatibility_decisions_v1_1 import target_id
    from profile_compatibility_contract_v1_2 import CAPABILITY
    targets=[prepare_target(root,case_id=cid,**{k:result[k] for k in (
        'pattern_ref','pattern_approval_ref','profile_ref','rules_ref')}) for cid in result['case_ids']]
    reviewer,headers,_=accounts['C'];operation=uuid.uuid4().hex
    body={'operation_id':operation,'decisions':[{'target_id':target_id(t),'target':t,'action':'approve',
        'parent':None,'withdraws':None,'reason':'Explicit isolated qualification of exact fictional News sources'} for t in targets]}
    denied=reviewer.post('/api/profile-compatibility/preview',headers=headers,json=body)
    assert denied.status_code==409,denied.text
    manage_reviewer(settings,3,action='grant',operator='isolated-native-news-fixture',
        reason='Independent explicit News Compatibility reviewer permission',capability=CAPABILITY)
    response=reviewer.post('/api/profile-compatibility/preview',headers=headers,json=body)
    assert response.status_code==200,response.text
    preview=response.json()
    response=reviewer.post('/api/profile-compatibility/confirm',headers=headers,json={
        'operation_id':operation,'preview_sha256':preview['preview_ref']['sha256']})
    assert response.status_code==200,response.text
    result.update(targets=targets,compatibility=response.json())
    return result


def prepare_news_business(node, *, customer_name='明禾餐食（全虚构 Golden）', pricing_facts=None):
    """Explicit fictional source correction through the existing Human Owner."""
    from compatibility_golden_support import prepare_native_business
    from test_customer_speaker_revision_v1 import review_current
    from test_review_flow_closure_v1 import amend,finish_speaker_review
    from review_protocol import post_review
    result=prepare_native_business(node, customer_name=customer_name)
    client=result['client'];headers=result['headers'];csrf=headers['X-CSRF-Token']
    bid=result['business_id'];sid=result['speaker_id'];url='/api/customers/'+bid
    prices=pricing_facts if pricing_facts is not None else ['午餐套餐29元，仅限到店自取，不含配送']
    changes=[{'field':'pricing_facts','value':prices,
        'evidence':'全虚构客户明确提供：'+'。'.join(prices)+'。'},
        {'field':'included_service_facts','value':['套餐含一份主食与两份蔬菜','门店提供密封餐盒'],
        'evidence':'全虚构客户明确提供：套餐含一份主食与两份蔬菜，门店提供密封餐盒。'}]
    detail=client.get(url).json()
    response=client.post(url+'/review-amendments',headers=headers,json={
        'review_context':detail['approval_context']['token'],'action':'correct',
        'reason':'虚构客户提供准确价格、适用条件及包含服务，交由人工独立核对。','changes':changes})
    assert response.status_code==200,response.text
    review_current(client,bid,csrf)
    response=post_review(client,url+'/persona/approve',headers=headers,json={'note':'Explicit independent price/service Human approval'})
    assert response.status_code==200,response.text
    amend(client,bid,csrf,sid=sid,action='rebase')
    finish_speaker_review(client,bid,sid,csrf)
    response=post_review(client,url+'/speakers/'+sid+'/persona/approve',headers=headers,json={
        'note':'Explicit Speaker confirmation after approved Business price/service correction'})
    assert response.status_code==200,response.text
    return result
