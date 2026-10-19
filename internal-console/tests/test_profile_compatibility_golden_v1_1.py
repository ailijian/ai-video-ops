from test_case_evidence_revision_v1 import node
import uuid
import os
import shutil
import subprocess
import json
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path

from compatibility_golden_support import prepare_native_golden, prepare_native_business
from profile_compatibility_decisions_v1_1 import decision_graph, read
from profile_compatibility_release_v1_1 import configure_runtime
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from fastapi.testclient import TestClient
from app.main import build_app
from app.background_task_service import BackgroundTaskRunner
from app.task_service import get_task
from app.content_delivery_gateway import export_mix_excel


def test_all_fictional_native_case_pattern_and_independent_compatibility(node):
    golden = prepare_native_golden(node)
    root = node[0].pipeline_root
    graph = decision_graph(root)
    assert len(graph['heads']) == 3
    assert all(v['effective'] for v in graph['heads'].values())
    assert read(golden['pattern_path'])['scope']['supported_case_ids'] == sorted(t['case_id'] for t in golden['targets'])
    assert read(golden['pattern_receipt'])['human_gate'] is True
    assert golden['compatibility']['receipt']['human_gate'] is True
    assert golden['compatibility']['receipt']['actor']['user_id'] == 3
    assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))


def test_native_golden_published_activation_and_official_creation_gate(node):
    golden = prepare_native_golden(node)
    business = prepare_native_business(node)
    settings, accounts, storage = node
    project = Path(__file__).resolve().parents[2]
    repo, owner = committed_source_snapshot(project, storage / 's')
    root = settings.pipeline_root
    configure_runtime(root, root, purpose='isolated-validation')
    package = owner.build_release(root, storage / 'p', repo, contract_version='1.1', purpose='isolated-validation')
    assert owner.verify_release(package, repo)['approved_cases'] == 3
    staged = owner.stage_release_v1_1(package, root, repo)
    activation = owner.activate_release_v1_1(root, repo, staged, uuid.uuid4().hex)
    assert owner.preflight(root, repo)['binding']['activation_ref'] == activation['activation_ref']
    runtime_settings = replace(settings, pipeline_python_executable=str(project / 'ops-pipeline/.venv/Scripts/python.exe'))
    with TestClient(build_app(runtime_settings)) as client:
        response = client.post('/api/auth/login', json={'phone': '13900000001', 'password': 'SyntheticCase2026!'})
        assert response.status_code == 200, response.text
        headers = {'X-CSRF-Token': response.json()['csrf_token']}
        response = client.post('/api/create/capacity-preview', headers=headers, json={
            'business_id': business['business_id'], 'speaker_id': business['speaker_id'], 'profile': 'mix', 'quantity': 1})
        assert response.status_code == 200, response.text
        value = response.json()['preview']
        assert value['production_feasibility']['status'] == 'supported', value
        assert value['recommendation']['can_continue'] is True, value
        assert not list(root.glob('data/generation_requests/*/generation_request_v1.json'))
        body = {'business_id': business['business_id'], 'speaker_id': business['speaker_id'], 'profile': 'mix',
                'requested_quantity': 1, 'confirmed_quantity': 1, 'idempotency_key': 'native_golden_creation_once'}
        created = client.post('/api/create/confirm', headers=headers, json=body)
        assert created.status_code == 200, created.text
        request_id = created.json()['result']['request_id']
        again = client.post('/api/create/confirm', headers=headers, json=body)
        assert again.status_code == 200 and again.json()['result']['request_id'] == request_id, again.text
        resolved = client.post(f'/api/create/{request_id}/resolve-sources', headers=headers)
        assert resolved.status_code == 200, resolved.text
        source_plan = read(root / 'data/production_plans' / request_id / 'generation_source_plan_v1.json')
        assert source_plan['coverage']['status'] == 'supported'
        assert source_plan['profile_compatibility_v1_1']['activation_ref'] == activation['activation_ref']
        assert {v['case_id'] for v in source_plan['eligible_case_pool']} == {v['case_id'] for v in golden['targets']}
        exercise_creation_tasks(client, headers, runtime_settings, request_id, project)


def exercise_creation_tasks(client, headers, settings, request_id, project):
    root = settings.pipeline_root
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DEEPSEEK_', 'QYAPI_', 'AIVO_'))}
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    actual_run = subprocess.run
    def boundary_command(command, *args, **kwargs):
        name = Path(command[1]).name if len(command) > 1 else ''
        mapping = {'resolve_generation_content_plan_v1.py': 'plan', 'resolve_generation_batch_v1.py': 'generate'}
        if name in mapping:
            rid = command[command.index('--request-id') + 1]
            command = [command[0], str(project / 'ops-pipeline/tests/compatibility_creation_synthetic.py'),
                       mapping[name], str(root), rid]
            kwargs['env'] = env
        return actual_run(command, *args, **kwargs)
    # Retain real Gateway checks and the existing Task runner. Only the provider
    # transport inside the child command is replaced by synthetic output.
    boundary = patch.object(subprocess, 'run', boundary_command)
    boundary.start()
    runner = BackgroundTaskRunner(settings)
    def start(path):
        response = client.post(f'/api/create/{request_id}/{path}', headers=headers)
        assert response.status_code == 200, response.text
        task_id = response.json()['task']['task_id']
        runner._run(task_id)
        return task_id, get_task(settings.database_path, task_id)
    try:
        planning_id, planned = start('resolve-content-plan')
        assert planned['status'] == 'completed', planned
        final = root / 'data/content_plans' / request_id / 'content_plan_v1_1_1.json'
        assert len(read(final)['selected_concepts']) == 1, read(final)
        protected_plan = final.read_bytes()
        generation_id, generated = start('generate-scripts')
        assert generated['status'] == 'completed', generated
        assert final.read_bytes() == protected_plan
        batch_path = root / 'data/generation_batches' / request_id / 'generation_batch_v1.json'
        batch = read(batch_path)
        assert batch['status'] == 'review_required' and len(batch['contents']) == 1
        protected_batch = batch_path.read_bytes()
        # A real attempted export before Human approval must fail with no file.
        export_id, refused = start('export-mix')
        assert refused['status'] == 'failed', refused
        assert not list((root / 'output').glob('*' + request_id + '*.xlsx'))
        response = client.post(f'/api/create/{request_id}/review', headers=headers, json={
            'items': [{'content_id': batch['contents'][0]['content_id'], 'decision': 'revised',
                'revised_title': '先把忌口核对清楚', 'revised_narration': batch['contents'][0]['narration'],
                'note': 'Native explicit Human title revision of all-fictional output'}],
            'note': 'Independent native Human content approval; no media rights granted'})
        assert response.status_code == 200, response.text
        assert batch_path.read_bytes() == protected_batch
        template = root / 'output/素材混剪&数字人口播混剪文案导入模板.xlsx'
        template.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / 'ops-pipeline/output' / template.name, template)
        # Background operations resume through their original business endpoint;
        # /api/tasks/{id}/retry belongs exclusively to Case analysis.
        retry = client.post(f'/api/create/{request_id}/export-mix', headers=headers)
        assert retry.status_code == 200, retry.text
        retry_id = retry.json()['task']['task_id']
        runner._run(retry_id)
        exported = get_task(settings.database_path, retry_id)
        assert exported['status'] == 'completed', exported
        assert get_task(settings.database_path, export_id)['status'] == 'failed'
        assert exported['operation_identity'] == refused['operation_identity']
        closure_path = root / 'data/generation_batches' / request_id / 'generation_export_closure_v1.json'
        closure = read(closure_path)
        ledger_path = Path(closure['content_ledger']['path'])
        before = ledger_path.read_bytes()
        assert len(read(ledger_path)['entries']) == 1
        assert Path(closure['excel_export']['path']).is_file()
        import zipfile
        with zipfile.ZipFile(closure['excel_export']['path']) as archive:
            assert archive.testzip() is None
            assert '先把忌口核对清楚'.encode('utf-8') in archive.read('xl/worksheets/sheet1.xml')
        # Original closure recovery owns history and cannot append again.
        replay = export_mix_excel(settings, request_id)
        assert ledger_path.read_bytes() == before
        assert read(closure_path) == closure
    finally:
        runner.close()
        boundary.stop()
