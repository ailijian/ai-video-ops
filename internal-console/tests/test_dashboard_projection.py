"""DASH-1 metrics/actions are grounded in real gateways and narrow source failures."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from app import dashboard_projection as home
from app.database import connect
from app.task_service import submit_task, update_task, STANDARD_BACKGROUND
from conftest import login_and_change_password
from test_case_library_security_v1 import node, ready, approve, CASE_ID


def hashes(root):
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.json')}


def test_formal_http_auth_validation_and_canonical_read_only(client,settings):
    assert client.get('/api/dashboard').status_code==401
    login_and_change_password(client)
    before=hashes(settings.pipeline_root)
    response=client.get('/api/dashboard')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['projection_only']
    assert data['metrics']['customers']['value']==1
    assert data['completed_works']['value'] is None
    assert 'no-store' in response.headers['cache-control']
    for query in ('page=0','page_size=51','section=private'):
        assert client.get('/api/dashboard?'+query).status_code==422
    assert hashes(settings.pipeline_root)==before
    assert 'raw_answers' not in response.text and 'transcript_safe_semantic' not in response.text


def test_r1_r2_and_speaker_drafts_are_not_extra_customers(client,settings):
    login_and_change_password(client)
    data=client.get('/api/dashboard').json()
    assert data['metrics']['customers']['value']==1
    # The baseline already contains a Business and Speaker Persona. Additional
    # revisions remain the same stable identity, not additional customers.
    root=settings.pipeline_root/'data/personas/fixture_business_001'
    original=next(root.glob('revision_*/persona_v1.json'))
    new=root/'revision_9999/persona_v1.json';new.parent.mkdir()
    new.write_bytes(original.read_bytes())
    assert home._identity_index(settings)[0]=={'fixture_business_001'}


def isolated_sources(monkeypatch):
    monkeypatch.setattr(home,'_customer_work',lambda s:(set(),{},{},[],False))
    monkeypatch.setattr(home,'creation_record_index',lambda s:{})
    monkeypatch.setattr(home,'_case_work',lambda *a:[])
    monkeypatch.setattr(home,'is_reviewer',lambda *a:False)


def task(settings,identity,*,status='queued',subject='fictional_customer',kind='content_generation',payload=None):
    value=submit_task(settings.database_path,task_type=kind,subject_ref=subject,
        task_id_prefix='dash-fixture',stage='等待开始',
        operation_identity=identity,execution_lane=STANDARD_BACKGROUND,payload=payload or {},created_by_user_id=1,
        queue_max=5000,gpu_pending_per_user_max=5000)
    if status!='queued':update_task(settings.database_path,value['task_id'],status=status)
    return value


def test_all_scoped_active_tasks_not_recent_ten_or_fifty(client,settings,monkeypatch):
    login_and_change_password(client); isolated_sources(monkeypatch)
    for index in range(65):task(settings,f'active-{index}')
    for index in range(5):task(settings,f'finished-{index}',status='completed')
    for index in range(5):task(settings,f'failed-{index}',status='failed')
    data=home.dashboard(settings,1,section='running',page_size=50)
    assert data['metrics']['running']['value']==65
    assert data['list']['total']==65 and len(data['list']['items'])==50
    second=home.dashboard(settings,1,section='running',page=2,page_size=50)
    assert len(second['list']['items'])==15
    assert not {r['task_id'] for r in data['list']['items']} & {r['task_id'] for r in second['list']['items']}


def test_retry_new_execution_supersedes_old_failed_action(client,settings,monkeypatch):
    login_and_change_password(client); isolated_sources(monkeypatch)
    customer={'display_name':'虚构客户','status':'analysis_pending','latest_intake_id':'intake_0001'}
    monkeypatch.setattr(home,'_customer_work',lambda s:({'fictional_customer'},{'fictional_customer':customer},{},[],False))
    old=task(settings,'customer_analysis:fictional_customer',status='failed',kind='customer_analysis',payload={'intake_id':'intake_0001'})
    assert home.dashboard(settings,1)['metrics']['pending']['value']==1
    new=task(settings,'customer_analysis:fictional_customer',kind='customer_analysis',payload={'intake_id':'intake_0001'})
    assert old['task_id']!=new['task_id']
    data=home.dashboard(settings,1)
    assert data['metrics']['pending']['value']==0 and data['metrics']['running']['value']==1
    assert data['recent'][0]['action']['url']==f"/tasks/{new['task_id']}"


@pytest.mark.parametrize('source',['customers','requests','tasks','cases'])
def test_missing_sources_are_unknown_not_zero(client,settings,monkeypatch,source):
    login_and_change_password(client);isolated_sources(monkeypatch)
    attr={'customers':'_customer_work','requests':'creation_record_index','tasks':'dashboard_tasks','cases':'_case_work'}[source]
    def failed(*a,**k):raise OSError('synthetic unavailable source')
    monkeypatch.setattr(home,attr,failed)
    data=home.dashboard(settings,1)
    assert data['partial'] and not data['sources'][source]['available']
    assert data['metrics']['pending']['value'] is None
    if source=='tasks':assert data['metrics']['running']['value'] is None
    if source=='customers':assert data['metrics']['customers']['value'] is None
    assert data['completed_works']['value'] is None
    if source=='requests':
        assert home.dashboard(settings,1,section='running')['list']['complete']
        assert home.dashboard(settings,1,section='materials')['list']['complete']
        assert not home.dashboard(settings,1,section='recent')['list']['complete']


def test_empty_is_real_zero_without_unknown_completion(client,settings,monkeypatch):
    login_and_change_password(client);isolated_sources(monkeypatch)
    data=home.dashboard(settings,1)
    assert not data['partial']
    assert all(v['value']==0 for v in data['metrics'].values())
    assert data['attention']==[] and data['recent']==[]
    assert not data['completed_works']['available'] and data['completed_works']['value'] is None


@pytest.mark.parametrize('instant,day,start,end',[
    ('2026-09-30T15:59:59+00:00','2026-09-30','2026-09-01','2026-10-01'),
    ('2026-09-30T16:00:00+00:00','2026-10-01','2026-10-01','2026-11-01'),
    ('2026-12-31T16:00:00+00:00','2027-01-01','2027-01-01','2027-02-01'),
])
def test_shanghai_day_month_boundaries(instant,day,start,end):
    value=home.business_period(datetime.fromisoformat(instant))
    assert value['today']==day
    assert value['month_start_inclusive'].startswith(start)
    assert value['month_end_exclusive'].startswith(end)
    assert value['month_start_inclusive'].endswith('+08:00')


def test_submitter_waiting_platform_review_is_not_their_approval_action(node):
    _,task,_,decisions,_,_=ready(node)
    a,_,_=node[1]['A'];b,_,_=node[1]['B'];c,_,_=node[1]['C'];d,_,_=node[1]['D']
    for client in (a,b,d):
        data=client.get('/api/dashboard').json()
        assert not any(r['kind']=='case_review' for r in data['attention'])
    for client in (b,d):
        body=client.get('/api/dashboard?section=recent').text
        assert task['task_id'] not in body and CASE_ID not in body
    data=c.get('/api/dashboard').json()
    assert any(r['kind']=='case_review' and r['action']['url']==f'/cases/{CASE_ID}' for r in data['attention'])
    approve(node,decisions)
    assert not any(r['kind']=='case_review' for r in c.get('/api/dashboard').json()['attention'])
    assert b.get(f'/api/cases/{CASE_ID}').status_code==404


def test_case_reviewer_revoke_removes_actions_same_session(node):
    ready(node)
    from app.case_library_access import manage_reviewer
    c,_,_=node[1]['C']
    assert c.get('/api/dashboard').json()['capabilities']['case_library_reviewer']
    manage_reviewer(node[0],3,action='revoke',operator='synthetic operator',reason='DASH revoke test')
    data=c.get('/api/dashboard').json()
    assert not data['capabilities']['case_library_reviewer']
    assert not any(r['kind']=='case_review' for r in data['attention'])


def test_same_request_review_failure_and_recovery_count_once(client,settings,monkeypatch):
    login_and_change_password(client);isolated_sources(monkeypatch)
    monkeypatch.setattr(home,'_customer_work',lambda s:({'fictional_customer'},{'fictional_customer':{'display_name':'虚构客户','status':'approved'}},{},[],False))
    record={'record_id':'generation:gen_fixture','request_id':'gen_fixture','business_id':'fictional_customer','profile':'mix',
        'stage':'GENERATE_SCRIPTS','status':'active','label':'继续创作','action_required':True,
        'url':'/create?business_id=fictional_customer&request_id=gen_fixture&profile=mix','updated_at':'2026-10-01T10:00:00Z'}
    monkeypatch.setattr(home,'creation_record_index',lambda s:{'fictional_customer':[record]})
    work=task(settings,'script_generation:gen_fixture',status='failed',subject='gen_fixture',payload={'operation':'script_generation','business_id':'fictional_customer'})
    data=home.dashboard(settings,1)
    assert data['metrics']['pending']['value']==1
    assert data['attention'][0]['action']['url']==f"/tasks/{work['task_id']}"
    assert not any(r.get('request_id')=='gen_fixture' for r in data['recent'])
    recent=home.dashboard(settings,1,section='recent')['list']['items']
    assert len([r for r in recent if r.get('request_id')=='gen_fixture'])==1
    assert recent[0]['action']['url']==record['url']
    update_task(settings.database_path,work['task_id'],status='queued')
    assert home.dashboard(settings,1)['metrics']['pending']['value']==0
    record.update(action_required=False,status='exported')
    update_task(settings.database_path,work['task_id'],status='failed')
    assert home.dashboard(settings,1)['metrics']['pending']['value']==0


def test_dashboard_does_not_create_requests_or_retry_tasks(client,settings):
    login_and_change_password(client)
    before=hashes(settings.pipeline_root)
    with connect(settings.database_path) as db: tasks_before=[tuple(r) for r in db.execute('SELECT * FROM tasks')]
    for query in ('','?section=attention','?section=recent','?section=running'):
        assert client.get('/api/dashboard'+query).status_code==200
    assert hashes(settings.pipeline_root)==before
    with connect(settings.database_path) as db: assert [tuple(r) for r in db.execute('SELECT * FROM tasks')]==tasks_before


def test_readable_old_attempt_does_not_advertise_current_classification(monkeypatch,settings):
    # A historical Attempt may be readable, while the current classification
    # writer targets a different Attempt. No dead or unauthorized action link.
    monkeypatch.setattr(home,'can_read_private_case',lambda s,u,c:False)
    tasks=[{'task_type':'case_analysis','task_id':'case_old_attempt','subject_ref':'7999999999999999999',
            'status':'awaiting_review','created_at':'2026-10-01T00:00:00Z','payload':{}}]
    assert home._case_work(settings,1,False,tasks)==[]


def test_task_sql_failure_preserves_other_sections(client,settings,monkeypatch):
    import sqlite3
    login_and_change_password(client)
    def unavailable(*a,**k): raise sqlite3.OperationalError('synthetic missing task source')
    monkeypatch.setattr(home,'connect',unavailable)
    response=client.get('/api/dashboard')
    assert response.status_code==200
    data=response.json()
    assert data['metrics']['customers']['value']==1
    assert data['metrics']['running']['value'] is None
    assert data['metrics']['pending']['value'] is None


def test_recent_merges_customer_execution_and_avoids_visible_priority_context(client,settings,monkeypatch):
    login_and_change_password(client);isolated_sources(monkeypatch)
    customer={'display_name':'虚构长名称客户','status':'fact_review_required','submitted_at':'2026-10-01T10:00:00Z'}
    pending=home._item('business_fact_review:fictional_customer:current','business_fact_review',customer['display_name'],
        '客户事实仍需人工核对。','核对资料','/customers/fictional_customer','fact_review_required',customer['submitted_at'],30,
        business_id='fictional_customer')
    monkeypatch.setattr(home,'_customer_work',lambda s:({'fictional_customer'},{'fictional_customer':customer},{},[pending],False))
    first=task(settings,'old-analysis',status='completed',kind='customer_analysis')
    second=task(settings,'new-analysis',status='awaiting_review',kind='customer_analysis')
    overview=home.dashboard(settings,1)
    assert overview['metrics']['pending']['value']==overview['metrics']['materials']['value']==1
    assert '待处理事项中' in overview['metrics']['materials']['note']
    assert not overview['recent'] and overview['recent_omitted_attention']==1
    recent=home.dashboard(settings,1,section='recent')['list']
    assert recent['total']==1
    item=recent['items'][0]
    assert item['business_id']=='fictional_customer' and item['action']['url']=='/customers/fictional_customer'
    assert item['updated_at']>=home._timestamp(customer['submitted_at'])
    assert first['task_id']!=second['task_id']  # history preserved, presentation merged
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM tasks WHERE task_id IN (?,?)',(first['task_id'],second['task_id'])).fetchone()[0]==2


def test_recent_order_and_pages_keep_all_contexts(client,settings,monkeypatch):
    login_and_change_password(client);isolated_sources(monkeypatch)
    customers={f'fictional_{i}':{'display_name':f'虚构客户{i}','status':'approved','submitted_at':f'2026-10-0{i+1}T00:00:00Z'} for i in range(7)}
    monkeypatch.setattr(home,'_customer_work',lambda s:(set(customers),customers,{},[],False))
    one=home.dashboard(settings,1,section='recent',page_size=3)['list']
    two=home.dashboard(settings,1,section='recent',page_size=3,page=2)['list']
    three=home.dashboard(settings,1,section='recent',page_size=3,page=3)['list']
    rows=one['items']+two['items']+three['items']
    assert one['total']==two['total']==three['total']==7
    assert [r['updated_at'] for r in rows]==sorted((r['updated_at'] for r in rows),reverse=True)
    assert len({home._work_context(r) for r in rows})==7


def test_submission_title_uses_authorized_original_caption_and_safe_fallback(node,monkeypatch):
    _,task,candidate,_,_,_=ready(node)
    case=json.loads(candidate.read_text(encoding='utf-8'))
    expected=home._source_caption(home._case_metadata(case),max_length=110)
    assert expected
    assert home._submission_title(node[0],1,CASE_ID,task['task_id'])==expected
    def forbidden(*a,**k): raise AssertionError('Private metadata read outside authorized Attempt')
    monkeypatch.setattr(home,'_case_metadata',forbidden)
    assert home._submission_title(node[0],2,CASE_ID,task['task_id'])=='未命名的视频投稿'
    monkeypatch.setattr(home,'_case_metadata',lambda *a:{})
    assert home._submission_title(node[0],1,CASE_ID,task['task_id'])=='未命名的视频投稿'
