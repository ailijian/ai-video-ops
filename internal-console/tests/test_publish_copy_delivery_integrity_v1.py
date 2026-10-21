"""PC-E08/10/12: immutable Native deliveries, hostile copies only for negatives."""
import copy,json,os
from dataclasses import replace
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow
from test_publish_copy_native_v1 import install_templates
from test_generation_export_anchor_v1 import hostile_copy
from publish_copy_native_support import generation,worker,current,post,confirm,calls
from profile_compatibility_decisions_v1_1 import read,file_sha,ref
from app.main import build_app
from app.task_service import get_task
import creation_delivery_v1 as delivery


def test_effective_delivery_parent_graph_and_prepared_receipt_integrity(node):
    runtime,b,_,_,_=native_news_runtime(node)
    runtime=replace(runtime,publish_copy_enabled=True);root=runtime.pipeline_root;install_templates(root)
    with TestClient(build_app(runtime)) as client:
        logged=client.post('/api/auth/login',json={'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':logged.json()['csrf_token']};rid,_=novel_flow(client,headers,runtime,b)
        tid=generation(client,headers,rid)['task']['task_id'];assert worker(runtime,tid).returncode==0
        versions=[]
        for n in range(2):
            state=current(client,rid)
            if n:
                payload=copy.deepcopy(state['draft']['payload'])
                payload['items'][0]['publish_title']='本期介绍'+payload['items'][0]['publish_title']
                post(client,'/api/create/'+rid+'/publish-copy/edit',headers,{'draft_ref':state['draft']['ref'],'payload':payload})
            confirm(client,headers,rid)
            tid=post(client,'/api/create/'+rid+'/publish-copy/export',headers)['task']['task_id']
            assert worker(runtime,tid).returncode==0
            assert get_task(runtime.database_path,tid)['status']=='completed'
            versions.append(current(client,rid)['delivery'])
        assert versions[0]['delivery_id']!=versions[1]['delivery_id']
        directory=root/'data/generation_batches'/rid/'deliveries'
        protected={str(p.relative_to(root)):file_sha(p) for p in root.rglob('*') if p.is_file() and '.locks' not in p.parts}
        call_count=len(calls(root,rid));observed=[]
        attacks=['mtime','pending_candidate','missing_parent','fork','unknown_schema','event_filename',
            'missing_prepared','missing_receipt','missing_completion','output_bytes','receipt_source',
            'receipt_template','receipt_closure','prepared_output','confirmation_sha','expected_head','foreign_business']
        for number,attack in enumerate(attacks):
            with hostile_copy(root,number+300) as clone:
                assert delivery.effective(clone,rid)['delivery_id']==versions[1]['delivery_id']
                base=clone/directory.relative_to(root);did=versions[1]['delivery_id'];candidate=base/did
                event=base/'effective'/(did+'.json');value=read(event)
                if attack=='mtime':
                    os.utime(base/'effective'/(versions[0]['delivery_id']+'.json'),(2000000000,2000000000))
                    os.utime(event,(1000000000,1000000000))
                elif attack=='pending_candidate':
                    pending=base/('e'*32);pending.mkdir();(pending/'untrusted.xlsx').write_bytes(b'not an approved delivery')
                elif attack=='missing_parent':value['parent']={'path':'data/missing.json','sha256':'a'*64}
                elif attack=='fork':
                    extra=base/'effective'/('f'*32+'.json');extra.write_text(json.dumps(value),encoding='utf-8')
                elif attack=='unknown_schema':value['schema_version']='creation-delivery-effective-version-event-v9.0'
                elif attack=='event_filename':event.rename(event.with_name('f'*32+'.json'))
                elif attack.startswith('missing_'):
                    p=candidate/(attack.removeprefix('missing_')+'.json');p.rename(p.with_suffix('.retained'))
                elif attack=='output_bytes':
                    output=clone/versions[1]['output_ref']['path'] if 'output_ref' in versions[1] else clone/read(candidate/'receipt.json')['output_ref']['path']
                    output.write_bytes(output.read_bytes()+b'unapproved trailing data')
                elif attack.startswith('receipt_'):
                    p=candidate/'receipt.json';v=read(p)
                    field={'receipt_source':'source_sha256','receipt_template':'template_ref','receipt_closure':'original_closure_ref'}[attack]
                    if isinstance(v[field],dict):v[field]['sha256']='f'*64
                    else:v[field]='f'*64
                    p.write_text(json.dumps(v),encoding='utf-8')
                elif attack=='prepared_output':
                    p=candidate/'prepared.json';v=read(p);v['output_ref']['sha256']='f'*64;p.write_text(json.dumps(v),encoding='utf-8')
                else:
                    p=candidate/'intent.json';v=read(p)
                    if attack=='confirmation_sha':v['confirmation_ref']['sha256']='f'*64
                    elif attack=='expected_head':v['expected_head']=None
                    else:v['business_id']='customer_foreign'
                    p.write_text(json.dumps(v),encoding='utf-8')
                if attack in {'missing_parent','unknown_schema'}:event.write_text(json.dumps(value),encoding='utf-8')
                if attack in {'mtime','pending_candidate'}:
                    assert delivery.effective(clone,rid)['delivery_id']==did
                    assert delivery.read_version(clone,rid,versions[0]['delivery_id'])['is_current'] is False
                else:
                    import pytest
                    with pytest.raises((RuntimeError,OSError,ValueError,KeyError)):delivery.effective(clone,rid)
                observed.append({'case':attack,'expected':'same_valid_head' if attack in {'mtime','pending_candidate'} else 'rejected'})
        assert all(file_sha(root/p)==sha for p,sha in protected.items())
        assert len(calls(root,rid))==call_count==1
        (root/'delivery_integrity_evidence.json').write_text(json.dumps({'request_id':rid,'versions':versions,
            'cases':observed,'original_bytes_unchanged':True,'external_calls':call_count},ensure_ascii=False,indent=2),encoding='utf-8')
