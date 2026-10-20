"""Real ASGI/CSRF/Session/Task/Native export over disposable unit source fixtures.

These are recovery protocol checks, not News v1.2 qualification evidence.
"""
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import sys
import subprocess
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth_service import provision_user
from app.database import connect

PIPELINE = Path(__file__).resolve().parents[2] / 'ops-pipeline'
sys.path.insert(0,str(PIPELINE / 'tests'))
from news_export_support import prepare
import news_export_recovery_v1 as native
from generation_recovery_v1 import authorization


@pytest.fixture(params=['novel','repurpose'])
def node(tmp_path, settings, request, monkeypatch):
    flow=prepare(tmp_path / 'sources',request.param)
    shutil.copytree(PIPELINE / 'scripts',flow['root']/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    config=replace(settings,pipeline_root=flow['root'],background_worker_enabled=True,
        task_heartbeat_seconds=1,novel_news_rollout='on')
    run=subprocess.run
    def observe(*args,**kwargs):
        result=run(*args,**kwargs)
        if result.returncode:
            (tmp_path/'native-child-error.log').write_text(str(result.stderr)+'\n'+str(result.stdout),encoding='utf-8')
        return result
    monkeypatch.setattr(subprocess,'run',observe)
    flow['child_errors']=tmp_path/'native-child-error.log'
    with TestClient(main_module.build_app(config)) as client:
        provision_user(config.database_path,'13800000000')
        login=client.post('/api/auth/login',json={'phone':'13800000000','password':'123456'})
        csrf=login.json()['csrf_token']
        response=client.post('/api/auth/change-password',headers={'X-CSRF-Token':csrf},json={
            'current_password':'123456','new_password':'NewsRecovery2026!','confirm_password':'NewsRecovery2026!'})
        assert response.status_code==200
        flow.update(settings=config,client=client,csrf=response.json()['csrf_token'])
        with connect(config.database_path) as db:
            namespace=db.execute('SELECT namespace FROM console_principal_namespace').fetchone()[0]
            token=db.execute('SELECT token_hash FROM sessions WHERE user_id=1').fetchone()[0]
        actor={'namespace':namespace,'user_id':1}
        flow['context']={'actor':actor,'authorization':authorization(config.database_path,actor,
            hashlib.sha256(token.encode()).hexdigest())}
        base='/api/create/novel-news/' if request.param=='novel' else '/api/create/news/'
        flow['url']=base+flow['rid']
        flow['state_url']=flow['url']+('/state' if request.param=='novel' else '/delivery')
        yield flow


def count_tasks(node):
    with connect(node['settings'].database_path) as db:
        return db.execute("SELECT count(*) FROM tasks WHERE task_type='excel_export'").fetchone()[0]


def wait_task(node, response):
    assert response.status_code==200,response.text
    task_id=response.json()['task']['task_id']
    for _ in range(450):
        r=node['client'].get('/api/tasks/'+task_id)
        task=r.json().get('task',r.json())
        if task['status'] in {'failed','completed'}:
            assert task['status']=='completed',(task,node['child_errors'].read_text(encoding='utf-8') if node['child_errors'].exists() else '')
            return task
        time.sleep(.05)
    raise AssertionError('Native export task did not reach terminal status')


def test_ne19_real_http_csrf_native_task_download_and_completed_dedup(node):
    client,url=node['client'],node['url']
    assert client.post(url+'/export').status_code==403
    assert count_tasks(node)==0
    wait_task(node,client.post(url+'/export',headers={'X-CSRF-Token':node['csrf']}))
    before=count_tasks(node)
    receipt_sha=hashlib.sha256(node['receipt'].read_bytes()).hexdigest()
    assert client.get(url+'/excel').status_code==200
    for _ in range(2):
        replay=client.post(url+'/export',headers={'X-CSRF-Token':node['csrf']})
        assert replay.status_code==200,replay.text
        assert replay.json()['accepted'] is False
    assert count_tasks(node)==before==1
    assert hashlib.sha256(node['receipt'].read_bytes()).hexdigest()==receipt_sha


@pytest.mark.parametrize('window', ['published', 'receipt', 'closure'])
def test_real_failed_export_task_continues_without_creating_another_task(node, window, monkeypatch):
    from app.task_service import get_task
    client, url = node['client'], node['url']
    actual_run = subprocess.run
    fault_script = Path(__file__).with_name('news_export_process_fault.py')
    def interrupt(command, *args, **kwargs):
        if (len(command) > 2 and Path(command[1]).name in {'novel_news_v1.py','news_delivery_v1.py'}
                and 'export' in command):
            command = [command[0], str(fault_script), str(node['root']), node['rid'], node['kind'], window]
        return actual_run(command, *args, **kwargs)
    with monkeypatch.context() as patcher:
        patcher.setattr(subprocess, 'run', interrupt)
        response = client.post(url+'/export', headers={'X-CSRF-Token':node['csrf']})
        assert response.status_code == 200, response.text
        tid = response.json()['task']['task_id']
        for _ in range(450):
            task = get_task(node['settings'].database_path, tid)
            if task['status'] == 'failed': break
            time.sleep(.05)
        assert task['status'] == 'failed', task
    intent = json.loads(native.paths(node['directory'])['intent'].read_text('utf-8'))
    output = node['root'] / intent['output_path']
    xlsx_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    before = {p:p.read_bytes() for p in node['directory'].glob('*.json')}
    replay = client.post(url+'/export', headers={'X-CSRF-Token':node['csrf']})
    assert replay.status_code == 200, replay.text
    if replay.json()['accepted']:
        completed = wait_task(node, replay)
    else:
        completed = replay.json()['task']
    assert completed['task_id'] == tid and completed['status'] == 'completed'
    assert count_tasks(node) == 1
    assert hashlib.sha256(output.read_bytes()).hexdigest() == xlsx_sha
    assert all(p.read_bytes() == data for p,data in before.items())
    assert client.get(url+'/excel').status_code == 200
    for _ in range(2):
        replay=client.post(url+'/export',headers={'X-CSRF-Token':node['csrf']})
        assert replay.status_code==200,replay.text
        assert replay.json()['accepted'] is False
    assert count_tasks(node)==1
    assert hashlib.sha256(output.read_bytes()).hexdigest()==xlsx_sha


@pytest.mark.parametrize('window',['published','receipt'])
def test_ne18_19_http_partial_state_continues_original_native_operation(node,window):
    if window=='published':
        original=native.os.link
        def fault(source,target,*args,**kwargs):
            value=original(source,target,*args,**kwargs)
            if Path(str(target)).parent.name=='output':raise OSError('injected published')
            return value
        manager=patch.object(native.os,'link',side_effect=fault)
    else:
        owner=node['owner'];name='_write_new' if node['kind']=='novel' else 'write_new_json'
        original=getattr(owner,name)
        def fault(path,value):
            result=original(path,value)
            if Path(path)==node['receipt']:raise OSError('injected receipt')
            return result
        manager=patch.object(owner,name,side_effect=fault)
    with manager:
        with pytest.raises(OSError):node['export'](node['context'])
    intent=json.loads(native.paths(node['directory'])['intent'].read_text(encoding='utf-8'))
    output=node['root']/intent['output_path'];before=hashlib.sha256(output.read_bytes()).hexdigest()
    state=node['client'].get(node['state_url'])
    assert state.status_code==200,state.text
    state=state.json()['state']
    assert state['export_recovery_state']==('published_receipt_pending' if window=='published' else 'receipt_complete_closure_pending')
    assert node['client'].get(node['url']+'/excel').status_code!=200
    wait_task(node,node['client'].post(node['url']+'/export',headers={'X-CSRF-Token':node['csrf']}))
    assert hashlib.sha256(output.read_bytes()).hexdigest()==before
    assert count_tasks(node)==1


def test_ne03_19_http_orphan_never_enqueues_and_errors_hide_paths(node):
    original=native.os.link
    def fault(source,target,*args,**kwargs):
        result=original(source,target,*args,**kwargs)
        if Path(str(target)).parent.name=='output':raise OSError('published')
        return result
    with patch.object(native.os,'link',side_effect=fault):
        with pytest.raises(OSError):node['export'](node['context'])
    # Disposable negative fixture: retain the published file but remove its
    # protocol evidence from this fixture namespace, simulating an old orphan.
    for name in ('intent','prepared'):
        path=native.paths(node['directory'])[name]
        path.rename(path.with_suffix('.retained-negative-fixture'))
    response=node['client'].post(node['url']+'/export',headers={'X-CSRF-Token':node['csrf']})
    assert response.status_code==503
    assert 'NEWS_EXPORT_LEGACY_UNBOUND_ORPHAN' in response.text
    assert str(node['root']) not in response.text and 'Traceback' not in response.text
    assert count_tasks(node)==0
