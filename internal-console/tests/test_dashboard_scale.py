"""Synthetic scale: real local indexing/SQL/resolvers, no model or runtime DB."""
from collections import Counter
import json
import os
from pathlib import Path
import time

import pytest

from app import dashboard_projection as home
from app.customer_gateway import prepare_customer_onboarding_request
from app.speaker_gateway import prepare_speaker_onboarding_request
from conftest import login_and_change_password
from test_dashboard_projection import task


@pytest.mark.parametrize('size,executions,history',[(0,0,0),(5,20,10),(120,1000,300)])
def test_real_aggregation_scale(client,settings,monkeypatch,size,executions,history):
    login_and_change_password(client)
    # Keep the existing validated Business + Speaker baseline. New records are
    # genuine saved drafts admitted by the same gateway, not fake KPI numbers.
    for index in range(size):
        prepare_customer_onboarding_request(settings,customer_name=f'完全虚构规模样本 {index}',industry=None,materials='',
            save_only=True,submission_key=f'dashboard-scale-{index}',created_by_user_id=1,created_by_phone='13800000000')
    if size:
        for index in range(3):
            prepare_speaker_onboarding_request(settings,business_id='fixture_business_001',
                speaker_name=f'虚构规模出镜人 {index}',public_role='虚构门店员工',speaker_type='generic',
                materials='仅为离线测试准备的虚构人物资料。',forbidden_claims=[],created_by={'user_id':1,'phone':'13800000000'})
    for index in range(executions):
        task(settings,f'scale-{index}',status='queued' if index%5==0 else 'running' if index%5==1 else 'failed' if index%5==2 else 'completed')
    for index in range(history):
        request_id=f'gen_dash_history_{index:05d}'
        path=settings.pipeline_root/'data/generation_requests'/request_id/'generation_request_v1.json'
        path.parent.mkdir(parents=True)
        # This is the existing immutable terminal-request contract covered by
        # Pipeline's direct-terminal lifecycle test. It is not completion proof
        # for a work/video, and the Dashboard intentionally never counts it so.
        path.write_text(json.dumps({'schema_version':'generation-request-v1.0','request_id':request_id,
            'persona_id':'fixture_business_001','speaker_persona':'fixture_speaker_001','target_profile':'mix',
            'quantity':1,'created_at':'2026-10-01T00:00:00Z','lifecycle':{'status':'completed'}}),encoding='utf-8')
    reads=Counter();original=Path.read_text
    def counted(path,*a,**k):
        if path.is_relative_to(settings.pipeline_root):reads[path.relative_to(settings.pipeline_root).as_posix()]+=1
        return original(path,*a,**k)
    monkeypatch.setattr(Path,'read_text',counted)
    began=time.perf_counter();data=home.dashboard(settings,1);elapsed=time.perf_counter()-began
    assert data['metrics']['customers']['value']==size+1
    assert data['metrics']['running']['value']==sum(i%5 in {0,1} for i in range(executions))
    assert data['completed_works']['value'] is None
    assert not any(a.get('request_id','').startswith('gen_dash_history_') for a in data['attention'])
    assert elapsed<10, f'Lightweight aggregation exceeded 10 seconds: {elapsed}'
    # One request scan shared by every metric/list; terminal history not repeatedly
    # reclassified for four KPI cards.
    for index in range(history):
        key=f'data/generation_requests/gen_dash_history_{index:05d}/generation_request_v1.json'
        assert reads[key]==2  # identity read + existing effective-lifecycle owner
    evidence={'customers':size+1,'tasks':executions,'terminal_requests':history,'elapsed_ms':round(elapsed*1000,2),
        'json_text_reads':sum(reads.values()),'most_repeated_files':reads.most_common(8),'payload_bytes':len(json.dumps(data,ensure_ascii=False).encode())}
    directory=os.environ.get('AIVO_VERIFICATION_ARTIFACTS')
    if directory:
        Path(directory,f'dashboard-scale-{size}.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))
