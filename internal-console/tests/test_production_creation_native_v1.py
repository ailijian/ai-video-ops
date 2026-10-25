"""Fictional Native qualification -> separate production-purpose runtime.

Every Approval/Pattern/Compatibility/Release/Human/Receipt writer is real.
Only external acquisition/analysis/generation transports are synthetic.
Nothing here is a package or approval for the actual 4090 environment.
"""
import json
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_case_library_security_v1 import node as security_node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow,repurpose_flow
from news_golden_support_v1_2 import prepare_news_business
from compatibility_golden_support import prepare_native_business
from test_creation_batch_native_v1 import EVENTS,config
from test_customer_speaker_revision_v1 import review_current
from test_review_flow_closure_v1 import amend,finish_speaker_review
from review_protocol import post_review
from app.main import build_app
from app.case_library_access import principal
from production_admission_v1 import prepare,confirm
from profile_compatibility_release_v1_1 import configure_runtime,effective_runtime
from profile_compatibility_decisions_v1_1 import read,file_sha
from profile_compatibility_contract_v1_1 import CompatibilityError
from human_review_operations_v1 import io_path

PROJECT=Path(__file__).resolve().parents[2]


def activate_fixture(prod_node,source,repo,owner,package):
    settings,_,_=prod_node;root=settings.pipeline_root
    # A real deployed checkout includes the whole committed machine inventory.
    # The old generic fixture only installed Pipeline scripts; do not weaken
    # production source verification to accommodate that partial fixture.
    for item in read(package/'manifest.json')['source_files']:
        target=settings.repo_root/item['path']
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.is_file():shutil.copyfile(PROJECT/item['path'],target)
    configure_runtime(root,source,purpose='production',contract_version='1.3',profiles=['mix','news'])
    staged=owner.stage_release_v1_1(package,root,repo)
    owner.activate_release_v1_1(root,repo,staged,uuid.uuid4().hex)
    baseline=root.parent/'docs/deliveries/creation-batch-ux-1/BASELINE.md'
    baseline.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(PROJECT/'docs/deliveries/creation-batch-ux-1/BASELINE.md',baseline)
    shutil.copytree(PROJECT/'ops-pipeline/templates/delivery',root/'templates/delivery',dirs_exist_ok=True)
    for name in ['新闻体视频制作文案导入模板.xlsx','素材混剪&数字人口播混剪文案导入模板.xlsx']:
        path=root/'output'/name;path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PROJECT/'ops-pipeline/output'/name,path)
    return replace(settings,pipeline_python_executable=str(PROJECT/'ops-pipeline/.venv/Scripts/python.exe'),
        novel_news_rollout='validation',novel_news_validation_phones=('13900000001',),publish_copy_enabled=True),staged


def new_business(node, *, story_events=EVENTS):
    # Independent fictional customers must not replay the intake identity of
    # an earlier sample. Preserve the native duplicate reader and its response.
    result=prepare_native_business(node,customer_name='生产闭环客户（全虚构）'+uuid.uuid4().hex,
        story_events=story_events,speaker_type='owner_founder')
    client=result['client'];headers=result['headers'];csrf=headers['X-CSRF-Token']
    bid=result['business_id'];sid=result['speaker_id'];url='/api/customers/'+bid
    prices=['午餐套餐29元，仅限工作日到店自取，不含配送','儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐']
    changes=[{'field':'pricing_facts','value':prices,'evidence':'全虚构客户明确提供：'+'。'.join(prices)+'。'},
        {'field':'included_service_facts','value':['套餐含一份主食与两份蔬菜','门店提供密封餐盒'],
         'evidence':'全虚构客户明确提供：套餐含一份主食与两份蔬菜，门店提供密封餐盒。'}]
    detail=client.get(url).json()
    response=client.post(url+'/review-amendments',headers=headers,json={
        'review_context':detail['approval_context']['token'],'action':'correct',
        'reason':'全虚构生产合同验证：明确真实价格和服务范围，保持人审。','changes':changes})
    assert response.status_code==200,response.text
    review_current(client,bid,csrf)
    response=post_review(client,url+'/persona/approve',headers=headers,json={'note':'Explicit fictional price/service approval'})
    assert response.status_code==200,response.text
    amend(client,bid,csrf,sid=sid,action='rebase');finish_speaker_review(client,bid,sid,csrf)
    response=post_review(client,url+'/speakers/'+sid+'/persona/approve',headers=headers,json={'note':'Explicit fictional Speaker revalidation'})
    assert response.status_code==200,response.text
    return result


def test_qualified_production_purpose_native_five_delivery_and_old_history(node,monkeypatch):
    runtime,business,news,repo,owner=native_news_runtime(node,mixed=True)
    source=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        _,novel_ref=novel_flow(client,headers,runtime,business)
        second=prepare_news_business(node,customer_name='生产接缝历史来源（全虚构）')
        _,repurpose_ref=repurpose_flow(client,headers,runtime,second)
    protected={p:io_path(p).read_bytes() for p in source.glob('data/**/*.json')}
    actor=principal(runtime,3)
    scope={'schema_version':'creative-production-admission-scope-v1.0','profiles':['mix','news'],
        'creative_styles':['conversion','persona','story'],
        'news_reuse_intents':['cross_profile_repurpose','novel_content'],'maximum_videos':5,
        'real_model_execution_authorized':True,'real_model_quality':'not_validated',
        'dispatch_per_business':1,'unknown_retry':'explicit-native-only'}
    operation=uuid.uuid4().hex
    with pytest.raises(CompatibilityError):
        prepare(source,runtime.database_path,principal(runtime,1),operation,scope,repo,
            reason='Unprivileged creation user must not grant production',news_validation_refs=[novel_ref,repurpose_ref])
    with pytest.raises(CompatibilityError):
        prepare(source,runtime.database_path,actor,uuid.uuid4().hex,scope,repo,
            reason='One path cannot qualify the other',news_validation_refs=[novel_ref])
    preview=prepare(source,runtime.database_path,actor,operation,scope,repo,
        reason='Explicit fictional Native Pattern/Compatibility purpose review',news_validation_refs=[novel_ref,repurpose_ref])
    assert prepare(source,runtime.database_path,actor,operation,scope,repo,
        reason='Explicit fictional Native Pattern/Compatibility purpose review',news_validation_refs=[novel_ref,repurpose_ref])==preview
    import production_admission_v1 as admission
    original_write=admission.write_once
    with monkeypatch.context() as fault:
        def interrupted(path,value):
            if Path(path).parent==source/admission.DIRECTORY/'decisions':
                raise OSError('Injected interruption after independent Pattern purpose receipt')
            return original_write(path,value)
        fault.setattr(admission,'write_once',interrupted)
        with pytest.raises(OSError):confirm(source,runtime.database_path,actor,operation,preview['preview_ref']['sha256'],repo)
    pattern_receipt=source/'data/patterns/production_purpose_operations'/operation/'decision.json'
    pattern_sha=file_sha(pattern_receipt)
    assert admission.head(source) is None
    decision=confirm(source,runtime.database_path,actor,operation,preview['preview_ref']['sha256'],repo)
    assert file_sha(pattern_receipt)==pattern_sha
    package=owner.build_release(source,source.parent.parent/'prod-pack',repo,
        contract_version='1.3',purpose='production',production_admission_ref=decision['decision_ref'])
    owner.verify_release(package,repo)
    inventory=[item['path'] for item in read(package/'manifest.json')['files']]
    assert not any(any(part in path for part in ('/personas/','/generation_requests/','/content_ledgers/','/customer_intakes/')) for path in inventory)
    assert not any(path.endswith(('.mp4','.sqlite3')) for path in inventory)
    with contextmanager(security_node.__wrapped__)(source.parent.parent/'prod-fixture') as prod_node:
        settings,accounts,storage=prod_node
        root=settings.pipeline_root
        production,staged=activate_fixture(prod_node,source,repo,owner,package)
        assert effective_runtime(root)['manifest']['purpose']=='production'
        prod_business=new_business(prod_node)
        import test_creation_batch_delivery_v1 as delivery
        monkeypatch.setattr(delivery,'mixed_runtime',lambda _:(production,prod_business))
        delivery.test_five_native_slots_concentrated_human_publish_and_two_profile_delivery(prod_node)
        # A separate fresh approved customer proves Conversion's real consumer,
        # not a relabel of Persona or a reuse of the already consumed topics.
        with contextmanager(security_node.__wrapped__)(storage/'cv') as conversion_node:
            conversion_runtime,_=activate_fixture(conversion_node,source,repo,owner,package)
            conversion=new_business(conversion_node)
            import test_creative_style_native_v1 as styles
            monkeypatch.setattr(styles,'style_runtime',lambda *args,**kwargs:(conversion_runtime,conversion))
            styles.test_persona_native_request_review_publish_delivery_and_negative(conversion_node,False,'conversion')
        # Repurpose in the NEW production runtime keeps its own Native binding.
        with TestClient(build_app(production)) as client:
            login=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
            headers={'X-CSRF-Token':login.json()['csrf_token']}
            before={p:io_path(p).read_bytes() for p in root.glob('data/content_ledgers/**/*.json')}
            # The retained News Pattern accepts a price-led semantic source.
            # A Story-rich Mix source must not be forced into that eligibility.
            repurpose_business=prepare_news_business(prod_node,
                customer_name='价格改编来源（全虚构）'+uuid.uuid4().hex)
            repurpose_flow(client,headers,production,repurpose_business,key='production_repurpose_once',record_isolated_evidence=False)
            assert all(io_path(p).read_bytes()==value for p,value in before.items())
        result={'purpose':'production-contract-in-isolated-fictional-runtime','real_models_called':False,
            'production_admission_ref':decision['decision_ref'],'release_ref':staged,
            'maximum_scope':5,'twenty_forty_production_validated':False,
            'protected_source_json_count':len(protected),'protected_source_json_unchanged':all(io_path(p).read_bytes()==value for p,value in protected.items())}
        (storage/'production_native_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    assert all(io_path(p).read_bytes()==value for p,value in protected.items())
