"""One explicit five-slot command, bounded original Human mutations and replay."""
import subprocess
from unittest.mock import patch
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from creation_batch_golden_support import mixed_runtime
from test_creation_batch_capacity_v2 import EVENTS
from test_creation_batch_native_v1 import config
from test_creation_batch_orchestration_v1 import external_boundaries
from publish_copy_native_support import post
from app.main import build_app
from app.creation_batch_gateway import advance,state
from app.creation_batch_delivery_gateway import owner
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from human_review_operations_v1 import read
import native_batch_v1 as native


def test_one_five_slot_human_command_continues_original_decisions_and_keeps_completed_receipts(node):
    runtime,business=mixed_runtime(node,story_events=EVENTS);root=runtime.pipeline_root
    with TestClient(build_app(runtime)) as client:
        login=post(client,'/api/auth/login',{}, {'phone':'13900000001','password':'SyntheticCase2026!'})
        headers={'X-CSRF-Token':login['csrf_token']}
        body={**{k:business[k] for k in ('business_id','speaker_id')},'configuration':config(story=5),'operation_id':'five_human_bounded'}
        pre=post(client,'/api/create/batches/preview',headers,body)['preview']
        bid=post(client,'/api/create/batches/confirm',headers,{**body,'preflight_sha256':pre['source_configuration_sha256']})['result']['batch_id']
        runner=BackgroundTaskRunner(runtime)
        try:
            with patch.object(subprocess,'run',external_boundaries):
                for _ in range(6):
                    task=advance(runtime,bid)['task'];runner._run(task['task_id'])
                    assert get_task(runtime.database_path,task['task_id'])['status']=='completed'
            pre=client.get('/api/create/batches/'+bid+'/human-options?scope=native_content_review').json()['preview']
            assert len(pre['items'])==5
            command={'scope':pre['scope'],'source_sha256':pre['source_sha256'],'operation_id':'one_explicit_human_command',
                'items':[{**{k:v for k,v in item.items() if k!='display'},'decision':'approve'} for item in pre['items']]}
            context=native.current_context(root,bid);protected={}
            real_run=subprocess.run
            def local_human_run(*args,**kwargs):
                assert 'creation_batch_review_v1.py' in str(args[0][1])
                assert kwargs['timeout']==180
                assert not any(k.startswith('DEEPSEEK_') for k in kwargs['env'])
                return real_run(*args,**kwargs)
            for index,approved in enumerate((2,4,5)):
                with patch.object(subprocess,'run',local_human_run):
                    result=owner(runtime,bid,'execute',context,**command,maximum_mutations=1)
                assert result['all_native_completed']==(index==2)
                assert result['continuation_needed']==(index<2)
                assert state(runtime,bid,native.current_context(root,bid))['counts']['approved']==approved
                assert all(p.read_bytes()==raw for p,raw in protected.items())
                protected={p:p.read_bytes() for p in root.glob('data/generation_batches/*/generation_batch_approval_receipt.json')}
            result=owner(runtime,bid,'execute',context,**command,maximum_mutations=1)
            assert result['all_native_completed']
            assert all(p.read_bytes()==raw for p,raw in protected.items())
            assert not list(root.glob('data/content_ledgers/**/*.json'))
            assert len(list(native.directory(root,bid).glob('human_commands/*/command.json')))==1
        finally:runner.close()
