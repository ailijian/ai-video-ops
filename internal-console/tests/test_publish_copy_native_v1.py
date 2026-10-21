"""PC1--3: real Native approval/Release and delivery, synthetic transport only."""
import copy
import shutil
import time
from pathlib import Path
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from test_case_evidence_revision_v1 import node
from test_news_novel_runtime_v1_2 import native_news_runtime
from test_news_qualification_complete_v1_2 import novel_flow, repurpose_flow
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from profile_compatibility_decisions_v1_1 import read, file_sha, ref
import publish_copy_v1 as pc
from publish_copy_sources_v1 import source

PROJECT = Path(__file__).resolve().parents[2]

def install_templates(root):
    shutil.copytree(PROJECT / 'ops-pipeline/templates/delivery/publish_v1',
                    root / 'templates/delivery/publish_v1', dirs_exist_ok=True)

def synthetic(src):
    items = []
    for original in src['items']:
        units = original['units']
        text = '\n'.join(u['text'] for u in units) if units else original['narration']
        title = units[0]['text'] if units else original['title']
        item = {'target_id': original['target_id'], 'source_version_sha256': src['source_sha256'],
            'publish_title': title, 'publish_body': text, 'topics': ['午餐套餐']}
        if src['mode'] != 'mix': item['production_headlines'] = [{'order': n, 'text': u['text'], 'source_unit_ids': [u['unit_id']], 'mapping_kind': 'extract'} for n, u in enumerate(units, 1)]
        items.append(item)
    return {'items': items}

@pytest.mark.parametrize('mode', ['novel_content', 'cross_profile_repurpose', 'mix'])
def test_native_publish_news_delivery_and_replay(node, mode):
    runtime, business, _, _, _ = native_news_runtime(node, mixed=mode != 'novel_content')
    runtime = replace(runtime, publish_copy_enabled=True)
    root = runtime.pipeline_root; install_templates(root)
    with TestClient(build_app(runtime)) as client:
        login = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        assert login.status_code == 200, login.text
        headers = {'X-CSRF-Token': login.json()['csrf_token']}
        if mode == 'novel_content': rid, _ = novel_flow(client, headers, runtime, business)
        else:
            nrid, _ = repurpose_flow(client, headers, runtime, business)
            request = read(root / 'data/news_deliveries' / nrid / 'news_delivery_request_v1.json')
            rid = nrid if mode == 'cross_profile_repurpose' else request['source_content_id'].rsplit('-C', 1)[0]
        original_files = {str(p): file_sha(p) for p in (root / 'data/generation_batches' / rid).glob('*.json')}
        timings={}
        def timed(name,callback):
            start=time.perf_counter();value=callback();timings[name]=round(time.perf_counter()-start,3);return value
        ledger = root / 'data/content_ledgers' / business['business_id'] / 'content_ledger_v1.json'
        ledger_before = file_sha(ledger)
        src = source(root, rid)
        url = '/api/create/' + rid + '/publish-copy'
        # A real worker may claim the durable queued Task before the HTTP
        # submitter writes its Native binding. Reproduce that exact ordering.
        from unittest.mock import patch
        from contextlib import nullcontext
        import app.publish_copy_gateway as gateway
        from publish_copy_native_support import worker
        queued = gateway.submit_task
        def claimed_before_http_binding(*args, **kwargs):
            task = queued(*args, **kwargs)
            completed = worker(runtime, task['task_id'])
            assert completed.returncode == 0, (completed.stdout, completed.stderr)
            assert get_task(runtime.database_path, task['task_id'])['status'] == 'completed'
            return task
        with (patch.object(gateway, 'submit_task', side_effect=claimed_before_http_binding)
              if mode == 'cross_profile_repurpose' else nullcontext()):
            response = timed('generate_admission',lambda:client.post(url + '/generate', headers=headers, json={}))
        assert response.status_code == 200, response.text
        tid = response.json()['task']['task_id']; task = get_task(runtime.database_path, tid)
        execution = task['payload']['publish_copy']; calls = []
        def generate(settings, request_id, **kwargs):
            return pc.run(root, request_id, kwargs['operation_id'], kwargs['authorization_context'],
                transport=lambda prompt: calls.append(prompt) or {'payload': synthetic(src)})
        runner = BackgroundTaskRunner(runtime, handlers={'publish_copy_generate': generate})
        try: timed('generate_worker',lambda:runner._run(tid))
        finally: runner.close()
        assert get_task(runtime.database_path, tid)['status'] == 'completed', get_task(runtime.database_path, tid)
        if mode == 'cross_profile_repurpose':
            from publish_copy_native_support import calls as transport_calls
            assert calls == [] and len(transport_calls(root, rid)) == 1
        else:
            assert len(calls) == 1
        state = client.get(url).json()['state']
        assert state['state'] == 'draft_ready', state
        assert client.post(url + '/export', headers=headers).status_code != 200
        assert client.post(url + '/confirm', headers=headers, json={'draft_ref': state['draft']['ref']}).status_code == 200
        response = timed('export_admission',lambda:client.post(url + '/export', headers=headers))
        assert response.status_code == 200, response.text
        etid = response.json()['task']['task_id']; runner = BackgroundTaskRunner(runtime)
        try: timed('export_worker',lambda:runner._run(etid))
        finally: runner.close()
        assert get_task(runtime.database_path, etid)['status'] == 'completed', get_task(runtime.database_path, etid)
        state = client.get(url).json()['state']; assert state['delivery']['state'] == 'completed', state
        assert state['task_snapshot_before_native'] is True
        # The optimized page is still the same Native state and strict completed
        # delivery, with one fresh source read shared only within that query.
        import subprocess
        comparison = subprocess.run([runtime.pipeline_python_executable, '-c', '''
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
import publish_copy_v1 as pc
from creation_delivery_v1 import effective
root,rid=Path(sys.argv[1]),sys.argv[2]
expected={**pc.state(root,rid),'delivery':effective(root,rid)}
with patch.object(pc,'source',wraps=pc.source) as fresh_source:
    assert pc.project(root,rid)==expected
    assert fresh_source.call_count==1
''', str(root), rid], capture_output=True, text=True, encoding='utf-8',
            env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
        assert comparison.returncode == 0, comparison.stdout + comparison.stderr
        output = Path(state['delivery']['output_path']); sha = file_sha(output)
        import subprocess, json
        opened = subprocess.run([runtime.pipeline_python_executable, '-c',
            'import sys,json;from openpyxl import load_workbook;w=load_workbook(sys.argv[1]);'
            'print(json.dumps({"sheets":w.sheetnames,"headers":[w.active.cell(4,c).value for c in range(1,w.active.max_column+1)],'
            '"production":w.active["A5"].value,"rows":w.active.max_row,"cells":[w.active.cell(5,c).value for c in range(1,w.active.max_column+1)]},ensure_ascii=False))', str(output)],
            capture_output=True, text=True, encoding='utf-8', env={**__import__('os').environ, 'PYTHONIOENCODING':'utf-8'})
        assert opened.returncode == 0, opened.stderr
        workbook = json.loads(opened.stdout)
        assert workbook['sheets'] == ['Sheet1']
        assert workbook['headers'] == (['视频制作标题','视频制作口播内容','视频发布标题','视频发布正文内容','视频话题'] if mode == 'mix'
            else ['视频制作内容','视频发布标题','视频发布正文内容','视频话题'])
        assert workbook['production'] == (src['items'][0]['title'] if mode == 'mix' else '\n'.join(u['text'] for u in src['items'][0]['units']))
        assert workbook['rows'] == 5
        item=state['draft']['payload']['items'][0]
        assert workbook['cells']==(([src['items'][0]['title'],src['items'][0]['narration']] if mode=='mix' else [workbook['production']])+
            [item['publish_title'],item['publish_body'],' '.join('#'+t.lstrip('#') for t in item['topics'])])
        for _ in range(2):
            assert client.post(url + '/export', headers=headers).json()['accepted'] is False
            result = client.get(url + '/excel/' + state['delivery']['delivery_id'])
            assert result.status_code == 200 and result.content == output.read_bytes()
        assert file_sha(output) == sha and file_sha(ledger) == ledger_before
        assert all(file_sha(Path(p)) == expected for p, expected in original_files.items())
        artifact=__import__('os').environ.get('AIVO_VERIFICATION_ARTIFACTS')
        if artifact:
            Path(artifact,f'native-{mode}-timing.json').write_text(json.dumps({
                'mode':mode,'request_id':rid,'timings_seconds':timings,'synthetic_calls':1,
                'output_sha256':sha,'ledger_unchanged_by_publishing':file_sha(ledger)==ledger_before,
                'scope':'isolated fresh Native fixture; not a matched before/after timing'},ensure_ascii=False,indent=2),encoding='utf-8')
