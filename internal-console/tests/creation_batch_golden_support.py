"""Qualified fictional mixed runtime; all Authority writers remain Native."""
import shutil,uuid
from pathlib import Path
from dataclasses import replace
from compatibility_golden_support import prepare_native_golden,prepare_native_business
from news_golden_support_v1_2 import prepare_news_compatibility
from test_customer_speaker_revision_v1 import review_current
from test_review_flow_closure_v1 import amend,finish_speaker_review
from review_protocol import post_review
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_release_v1_1 import configure_runtime
from test_creation_batch_native_v1 import EVENTS
PROJECT=Path(__file__).resolve().parents[2]

def mixed_runtime(node, *, story_events=None, pricing_facts=None, personal_practices=None):
    prepare_native_golden(node)
    prepare_news_compatibility(node)
    business=prepare_native_business(node,story_events=EVENTS,speaker_type='owner_founder',personal_practices=personal_practices)
    settings,_,storage=node;root=settings.pipeline_root
    shutil.copytree(PROJECT/'ops-pipeline/templates/delivery',root/'templates/delivery',dirs_exist_ok=True)
    client=business['client'];headers=business['headers'];csrf=headers['X-CSRF-Token']
    bid=business['business_id'];sid=business['speaker_id'];url='/api/customers/'+bid
    prices=pricing_facts if pricing_facts is not None else ['午餐套餐29元，仅限工作日到店自取，不含配送','儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐']
    changes=[{'field':'pricing_facts','value':prices,'evidence':'全虚构客户明确提供：'+'。'.join(prices)+'。'},
        {'field':'included_service_facts','value':['套餐含一份主食与两份蔬菜','门店提供密封餐盒'],
         'evidence':'全虚构客户明确提供：套餐含一份主食与两份蔬菜，门店提供密封餐盒。'}]
    if story_events is not None:
        values=['店主小周亲自负责核对订单',*story_events]
        changes.append({'field':'founder_or_operator_story','value':values,
            'evidence':'全虚构客户逐项提供的事件记录：'+'。'.join(values)+'。'})
    detail=client.get(url).json()
    corrected=client.post(url+'/review-amendments',headers=headers,json={
        'review_context':detail['approval_context']['token'],'action':'correct',
        'reason':'全虚构来源核对，保留已批准人物经历与事件，加入明确价格及条件。',
        'changes':changes})
    assert corrected.status_code==200,corrected.text
    review_current(client,bid,csrf)
    approved=post_review(client,url+'/persona/approve',headers=headers,json={'note':'Explicit fictional Human price/service approval'})
    assert approved.status_code==200,approved.text
    amend(client,bid,csrf,sid=sid,action='rebase');finish_speaker_review(client,bid,sid,csrf)
    approved=post_review(client,url+'/speakers/'+sid+'/persona/approve',headers=headers,json={'note':'Explicit fictional Speaker revalidation'})
    assert approved.status_code==200,approved.text
    baseline=settings.repo_root/'docs/deliveries/creation-batch-ux-1/BASELINE.md'
    baseline.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(PROJECT/'docs/deliveries/creation-batch-ux-1/BASELINE.md',baseline)
    repo,owner=committed_source_snapshot(PROJECT,storage/'s',complete=True)
    configure_runtime(root,root,purpose='isolated-validation',contract_version='1.2',profiles=['mix','news'])
    package=owner.build_release(root,storage/'p',repo,contract_version='1.2',purpose='isolated-validation')
    owner.verify_release(package,repo)
    staged=owner.stage_release_v1_1(package,root,repo);owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
    return replace(settings,pipeline_python_executable=str(PROJECT/'ops-pipeline/.venv/Scripts/python.exe'),
        novel_news_rollout='validation',novel_news_validation_phones=('13900000001',),publish_copy_enabled=True),business

