from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.main import build_app
from app.database import connect
from app import creative_capacity
from conftest import login_and_change_password

BODY={'business_id':'customer_a','speaker_id':'speaker_a','novel_target':10}


def test_session_csrf_and_strict_dto(client,monkeypatch):
    endpoint='/api/create/capacity-inventory'
    assert client.post(endpoint,json=BODY).status_code==401
    csrf=login_and_change_password(client)
    assert client.post(endpoint,json=BODY).status_code==403
    monkeypatch.setattr(creative_capacity,'projection',lambda *a:{'authority':{'authorizes_execution':False}})
    result=client.post(endpoint,json=BODY,headers={'X-CSRF-Token':csrf})
    assert result.status_code==200 and 'private, no-store' in result.headers['cache-control']
    for delta in ({'novel_target':True},{'novel_target':41},{'business_id':'../customer'},{'approved':True}):
        assert client.post(endpoint,json={**BODY,**delta},headers={'X-CSRF-Token':csrf}).status_code==422


def test_rollout_default_denied_before_native_reader(client,settings,monkeypatch):
    csrf=login_and_change_password(client)
    monkeypatch.setattr(creative_capacity,'read_inventory',lambda **k:pytest.fail('must not read'))
    response=client.post('/api/create/capacity-inventory',json=BODY,headers={'X-CSRF-Token':csrf})
    assert response.status_code==403 and response.json()['detail']['code']=='NOVEL_NEWS_NOT_AVAILABLE'


def test_actor_revoked_during_read_fails_closed(client,settings,monkeypatch):
    settings=replace(settings,novel_news_rollout='on')
    # Existing logged-in session shares the same isolated auth DB.
    csrf=login_and_change_password(client)
    def revoke(**kw):
        with connect(settings.database_path) as db: db.execute("UPDATE users SET status='disabled' WHERE id=1")
        return {'private':'must not return'}
    monkeypatch.setattr(creative_capacity,'read_inventory',revoke)
    with TestClient(build_app(settings)) as enabled:
        enabled.cookies.update(client.cookies)
        response=enabled.post('/api/create/capacity-inventory',json=BODY,headers={'X-CSRF-Token':csrf})
    assert response.status_code==403 and 'must not return' not in response.text
