"""Independent permission domains; historical event bytes remain unchanged."""
import json
import pytest
from app.auth_service import provision_user
from app.database import connect
from app.case_library_access import principal
from app.profile_compatibility_gateway import manage_reviewer
from profile_compatibility_authorization_v1 import authorization, validate_grant_proof
from profile_compatibility_contract_v1_1 import CompatibilityError, CAPABILITY as MIX
from profile_compatibility_contract_v1_2 import CAPABILITY as NEWS, PATTERN_CAPABILITY as PATTERN
from conftest import login_and_change_password


def ready(settings,client):
    login_and_change_password(client)
    return principal(settings,1)


def grant(settings,capability,action='grant'):
    return manage_reviewer(settings,1,action=action,operator='isolated test administrator',
        reason='explicit independent review capability test',capability=capability)


def test_no_case_or_mix_inheritance_and_independent_parent_sequences(settings,client):
    actor=ready(settings,client)
    grant(settings,MIX)
    old=authorization(settings.database_path,actor)
    with connect(settings.database_path) as db:
        original=dict(db.execute('SELECT event_id,record_json FROM profile_compatibility_capability_events').fetchall())
    for cap in (NEWS,PATTERN):
        with pytest.raises(CompatibilityError):authorization(settings.database_path,actor,capability=cap)
        grant(settings,cap)
        value=authorization(settings.database_path,actor,capability=cap)
        assert value['capability']==cap and len(value['events'])==1
        assert value['events'][0]['record']['sequence']==1 and value['events'][0]['record']['parent_sha256'] is None
        with pytest.raises(CompatibilityError):validate_grant_proof(value)
    assert authorization(settings.database_path,actor)==old
    with connect(settings.database_path) as db:
        now=dict(db.execute('SELECT event_id,record_json FROM profile_compatibility_capability_events').fetchall())
    assert all(now[k]==v for k,v in original.items())


@pytest.mark.parametrize('capability',[NEWS,PATTERN])
def test_revocation_regrant_never_revives_old_intent_proof(settings,client,capability):
    actor=ready(settings,client);grant(settings,capability)
    old=authorization(settings.database_path,actor,capability=capability)
    grant(settings,capability,'revoke')
    with pytest.raises(CompatibilityError):authorization(settings.database_path,actor,capability=capability)
    grant(settings,capability)
    new=authorization(settings.database_path,actor,capability=capability)
    assert old!=new and len(new['events'])==3
    assert [x['record']['sequence'] for x in new['events']]==[1,2,3]
    validate_grant_proof(new,capability=capability)
    wrong=json.loads(json.dumps(new));wrong['capability']=MIX
    with pytest.raises(CompatibilityError):validate_grant_proof(wrong,capability=capability)
