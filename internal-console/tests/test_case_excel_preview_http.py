import hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import build_app
from app.case_excel_preview import MAX_FILE
from app.database import connect
from conftest import login_and_change_password
from test_case_excel_preview_v03 import TEMPLATE, VECTORS, workbook, invalid_deflate_workbook


def state(settings):
    files={str(p.relative_to(settings.pipeline_root)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in settings.pipeline_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    with connect(settings.database_path) as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in {'sessions','users','auth_events','sqlite_sequence'}]
        rows={t:[tuple(row) for row in db.execute('SELECT * FROM "'+t+'"')] for t in tables}
    return files,rows


def test_preview_requires_session_csrf_and_password_change(client):
    route='/api/case-excel/preview';body=TEMPLATE.read_bytes();headers={'Content-Type':'application/octet-stream'}
    assert client.post(route,content=body,headers=headers).status_code==401
    client.post('/api/auth/login',json={'phone':'13800000000','password':'123456'})
    assert client.post(route,content=body,headers=headers).status_code==403
    csrf=login_and_change_password(client)
    assert client.post(route,content=body,headers=headers).status_code==403
    assert client.post(route,content=body,headers={**headers,'X-CSRF-Token':csrf}).status_code==200


def test_upload_row_issues_replay_and_no_business_write(client,settings):
    csrf=login_and_change_password(client);headers={'Content-Type':'application/octet-stream','X-CSRF-Token':csrf}
    before=state(settings)
    body=workbook([VECTORS[0]['case_row'],VECTORS[5]['case_row']])
    responses=[client.post('/api/case-excel/preview',content=body,headers=headers) for _ in range(2)]
    assert all(r.status_code==200 and {'private','no-store'} <= set(r.headers['cache-control'].replace(' ','').split(',')) for r in responses)
    result=responses[0].json()['preview'];assert result==responses[1].json()['preview']
    assert len(result['rows'])==2 and any(i['code']=='OTHER_NOTE_REQUIRED' for i in result['issues'])
    assert result['file_sha256']==hashlib.sha256(body).hexdigest()
    assert not any(result['authority'].values())
    assert state(settings)==before


def test_preview_rejects_bad_and_overlarge_input_without_writes(client,settings):
    csrf=login_and_change_password(client);headers={'Content-Type':'application/octet-stream','X-CSRF-Token':csrf}
    before=state(settings)
    for body,status in [(b'',422),(b'not a workbook',422),(b'x'*(MAX_FILE+1),413)]:
        response=client.post('/api/case-excel/preview',content=body,headers=headers)
        assert response.status_code==status and {'private','no-store'} <= set(response.headers['cache-control'].replace(' ','').split(','))
    assert client.post('/api/case-excel/preview',content=b'{}',headers={**headers,'Content-Type':'application/json'}).status_code==415
    assert state(settings)==before


def test_chunked_body_cannot_bypass_size_bound(client):
    csrf=login_and_change_password(client)
    response=client.post('/api/case-excel/preview',content=iter([b'x'*MAX_FILE,b'y']),headers={'Content-Type':'application/octet-stream','X-CSRF-Token':csrf})
    assert response.status_code==413


def test_corrupt_deflate_returns_safe_error_without_business_writes(client, settings):
    csrf = login_and_change_password(client)
    before = state(settings)
    response = client.post('/api/case-excel/preview', content=invalid_deflate_workbook(), headers={
        'Content-Type': 'application/octet-stream', 'X-CSRF-Token': csrf})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'ZIP_INVALID_OR_CRC'
    assert 'private, no-store' in response.headers['cache-control']
    assert 'decompressing' not in response.text
    assert state(settings) == before


def test_invalid_declared_length_is_bounded_before_integer_conversion(client):
    csrf=login_and_change_password(client)
    for length,status in [('x',422),('-1',422),('9'*5000,413)]:
        response=client.post('/api/case-excel/preview',content=b'x',headers={
            'Content-Type':'application/octet-stream','X-CSRF-Token':csrf,'Content-Length':length})
        assert response.status_code==status


def test_other_session_cannot_read_previous_workbook(client,settings):
    csrf=login_and_change_password(client)
    response=client.post('/api/case-excel/preview',content=TEMPLATE.read_bytes(),headers={'Content-Type':'application/octet-stream','X-CSRF-Token':csrf})
    assert response.status_code==200
    with TestClient(build_app(settings)) as other:
        assert other.get('/api/case-excel/preview').status_code in {404,405}
        assert other.post('/api/case-excel/preview',content=b'x').status_code==401
