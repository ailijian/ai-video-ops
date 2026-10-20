import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_contract_v1_2 import PROFILE,RULES,CONFIG,SCHEMAS,validate_contract
from production_profile_v1 import declared_news_profile_v1_2,initialize_news_profile_v1_2


def test_definition_has_no_registry_dependency_or_production_grant(tmp_path):
    template=tmp_path/'output/template.xlsx';template.parent.mkdir();template.write_bytes(b'isolated template identity')
    refs=initialize_news_profile_v1_2(tmp_path,template)
    from profile_compatibility_decisions_v1_1 import read,resolve_ref
    profile=read(resolve_ref(tmp_path,refs['profile_ref']))
    validate_contract(profile,PROFILE)
    assert profile['status']=='definition_only' and profile['automatic_production_promotion'] is False
    assert not {'registry_ref','coverage_ref','production_ready'} & profile.keys()
    for key,value in [('status','production_ready'),('automatic_production_promotion',True)]:
        changed=copy.deepcopy(profile);changed[key]=value
        with pytest.raises(CompatibilityError):validate_contract(changed,PROFILE)
    assert initialize_news_profile_v1_2(tmp_path,template)==refs


def test_unknown_schema_and_production_runtime_config_fail_closed():
    with pytest.raises(CompatibilityError):validate_contract({'schema_version':'news-v999'})
    config={'schema_version':CONFIG,'purpose':'production','control_root':'x','control_id':'a'*32,
        'reader_version':'profile-compatibility-reader-v1.2','profiles':['news']}
    with pytest.raises(CompatibilityError):validate_contract(config,CONFIG)
    assert 'production' not in SCHEMAS[RULES]['properties']['allowed_purposes']['const']
