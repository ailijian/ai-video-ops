"""Read failures are business 4xx; never a write, fabricated empty data or 503."""
import hashlib
import pytest
from conftest import login_and_change_password
from test_customer_speaker_smart_intake_v1 import settings


@pytest.mark.parametrize('path,status,code', [
    ('/api/customers/not-a-customer',422,'INVALID_BUSINESS_ID'),
    ('/api/customers/customer_missing',404,'CUSTOMER_NOT_FOUND'),
    ('/api/customers/customer_missing/speakers/bad.id',422,'INVALID_SPEAKER_ID'),
    ('/api/customers/customer_missing/speakers/speaker_missing',404,'SPEAKER_NOT_FOUND'),
])
def test_customer_speaker_missing_read_is_business_error(client,settings,path,status,code):
    login_and_change_password(client)
    hashes=lambda:{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in settings.pipeline_root.rglob('*.json')}
    before=hashes()
    result=client.get(path)
    assert result.status_code==status,result.text
    assert result.json()['detail']['code']==code
    assert result.json()['detail']['next_action']
    assert hashes()==before


def test_speaker_read_under_other_business_keeps_lineage_gate(client,settings):
    from test_customer_speaker_revision_v1 import approved_customer,approved_speaker
    csrf=login_and_change_password(client)
    business=approved_customer(client,settings,csrf)
    speaker=approved_speaker(client,settings,csrf,business)
    hashes=lambda:{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in settings.pipeline_root.rglob('*.json')}
    before=hashes()
    result=client.get(f'/api/customers/customer_other/speakers/{speaker}')
    assert result.status_code==409,result.text
    assert result.json()['detail']['code']=='SPEAKER_BUSINESS_LINEAGE_MISMATCH'
    assert 'speaker_persona' not in result.json()
    assert hashes()==before
