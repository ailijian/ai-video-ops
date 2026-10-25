"""Production contract components; fixtures never establish real production approval."""
import copy
import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_profile_compatibility_v1_1 import compat,grant,execute,request
from test_profile_compatibility_release_v1_1 import committed_source_snapshot
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_release_v1_1 import configure_runtime,effective_runtime
from profile_compatibility_decisions_v1_1 import read,file_sha
import production_admission_v1 as admission

PROJECT=Path(__file__).resolve().parents[2]


def scope(**changes):
    return {'schema_version':admission.SCOPE,'profiles':['mix'],
        'creative_styles':['persona'],'news_reuse_intents':[],'maximum_videos':5,
        'real_model_execution_authorized':True,'real_model_quality':'not_validated',
        'dispatch_per_business':1,'unknown_retry':'explicit-native-only',**changes}


@pytest.mark.parametrize('change',[
    {'maximum_videos':0},{'maximum_videos':6},{'maximum_videos':True},
    {'creative_styles':[]},{'creative_styles':['unknown']},{'creative_styles':['persona','persona']},
    {'profiles':['news']},{'news_reuse_intents':['novel_content']},
    {'real_model_quality':'verified'},{'dispatch_per_business':2},{'unexpected':True},
    {'real_model_execution_authorized':False},
])
def test_production_scope_rejects_unreviewed_expansion(change):
    with pytest.raises(CompatibilityError):admission.check(scope(**change),admission.SCOPE)


def test_production_schemas_are_real_draft_2020_12_and_boolean_strict():
    import profile_compatibility_contract_v1_3 as contract
    for schema in [*admission.SCHEMAS.values(),*contract.SCHEMAS.values()]:
        Draft202012Validator.check_schema(schema)
    Draft202012Validator(admission.SCOPE_SCHEMA).validate(scope())
    for bad in [1,'true',None]:
        with pytest.raises(Exception):
            admission.check(scope(real_model_execution_authorized=bad),admission.SCOPE)


def test_cli_reads_the_native_news_reference_array_and_rejects_objects(tmp_path):
    path=PROJECT/'deploy/creative-authority/review_production_admission.py'
    spec=importlib.util.spec_from_file_location('admission_cli',path)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    refs=[{'path':'data/qualification/novel.json','sha256':'a'*64},
          {'path':'data/qualification/repurpose.json','sha256':'b'*64}]
    source=tmp_path/'refs.json';source.write_text(json.dumps(refs),encoding='utf-8')
    assert cli.read_news_validation_refs(source)==refs
    assert cli.read_news_validation_refs(None) is None
    for bad in ({'refs':refs},refs[:1],refs+[refs[0]],[{'path':'../escape','sha256':'a'*64},refs[1]]):
        source.write_text(json.dumps(bad),encoding='utf-8')
        with pytest.raises(CompatibilityError):cli.read_news_validation_refs(source)


@pytest.mark.parametrize('version',['1','2','production-1'])
@pytest.mark.parametrize('count',[3,4,5])
def test_grouping_keeps_native_quantity_bounds_and_stable_slot_identity(monkeypatch,version,count):
    # Pure grouping unit. Native admission is exercised separately, without
    # mocking its Human, source, permission or Request owners.
    import native_batch_v1 as native
    slots=[{'slot_id':'batch-S'+str(n),'production_profile':'mix',
        'creative_style':{'style_id':'persona'},'source_kind':'native_mix'} for n in range(count)]
    monkeypatch.setattr(native,'intent',lambda *args:(None,{'slots':slots,'business_id':'fixture_business'}))
    monkeypatch.setattr(native,'batch_policy',lambda *args:{'policy_version':version,'mix_style_quantities':[1,2]})
    first=native.groups(Path('unused-unit-root'),'fixture_batch')
    # v1 identities are historical; preserving them does not authorize K>2.
    expected=[count] if version=='1' else [2]*(count//2)+([1] if count%2 else [])
    assert [len(g['slots']) for g in first]==expected
    assert [s['slot_id'] for g in first for s in g['slots']]==[s['slot_id'] for s in slots]
    assert len({g['request_id'] for g in first})==len(first)
    assert native.groups(Path('unused-unit-root'),'fixture_batch')==first


def test_native_production_release_is_exact_withdrawable_and_not_an_isolated_flag(compat,tmp_path,monkeypatch):
    _,settings,_,actor,targets=compat
    grant(settings)
    execute(settings,actor,[request(target) for target in targets])
    root=settings.pipeline_root
    repo,owner=committed_source_snapshot(PROJECT,tmp_path/'src',complete=True)
    protected={p:p.read_bytes() for directory in ('data/cases','data/fingerprints','data/patterns/approved')
        for p in (root/directory).rglob('*') if p.is_file()}
    op=uuid.uuid4().hex
    preview=admission.prepare(root,settings.database_path,actor,op,scope(),repo,reason='Fictional component Human scope review')
    assert admission.head(root) is None
    with pytest.raises(CompatibilityError):
        admission.confirm(root,settings.database_path,actor,op,'0'*64,repo)
    receipt=admission.confirm(root,settings.database_path,actor,op,preview['preview_ref']['sha256'],repo)
    assert admission.confirm(root,settings.database_path,actor,op,preview['preview_ref']['sha256'],repo)['recovered']
    package=owner.build_release(root,tmp_path/'pkg',repo,contract_version='1.3',purpose='production',
        production_admission_ref=receipt['decision_ref'])
    runtime=tmp_path/'runtime'
    configure_runtime(runtime,root,purpose='production',contract_version='1.3',profiles=['mix'])
    staged=owner.stage_release_v1_1(package,runtime,repo)
    activation=uuid.uuid4().hex
    import profile_compatibility_release_v1_1 as release
    original_replace=release.os.replace
    with monkeypatch.context() as fault:
        def interrupted(source,destination):
            if str(destination).endswith('active.json'):raise OSError('Injected activation pointer interruption')
            return original_replace(source,destination)
        fault.setattr(release.os,'replace',interrupted)
        with pytest.raises(OSError):owner.activate_release_v1_1(runtime,repo,staged,activation)
    owner.activate_release_v1_1(runtime,repo,staged,activation)
    active=effective_runtime(runtime)
    assert active['registry']['profiles']['mix']['status']=='production_ready'
    assert admission.batch_policy(active)['maximum_logical_slots']==5
    admission.require_selection(active,profile='mix',style='persona',execution=True)
    for kwargs in ({'profile':'news','reuse_intent':'novel_content'},{'profile':'mix','style':'story'}):
        with pytest.raises(CompatibilityError):admission.require_selection(active,**kwargs)
    from native_batch_v1 import policy_qualification
    assert policy_qualification(runtime)['manifest']['purpose']=='production'
    from news_export_recovery_v1 import bound_source_paths
    archived=active['binding']
    original_paths=bound_source_paths(runtime,archived,historical=True)
    successor=owner.build_release(root,tmp_path/'successor',repo,contract_version='1.3',purpose='production',
        production_admission_ref=receipt['decision_ref'],parent_release=staged)
    next_release=owner.stage_release_v1_1(successor,runtime,repo)
    owner.activate_release_v1_1(runtime,repo,next_release,uuid.uuid4().hex)
    with pytest.raises(CompatibilityError):effective_runtime(runtime,pinned=archived)
    assert bound_source_paths(runtime,archived,historical=True)==original_paths
    historical_manifest=runtime/archived['release_ref']['path'];bytes_before=historical_manifest.read_bytes()
    try:
        historical_manifest.write_bytes(bytes_before+b' ')
        with pytest.raises(CompatibilityError):bound_source_paths(runtime,archived,historical=True)
    finally:historical_manifest.write_bytes(bytes_before)
    with pytest.raises(CompatibilityError):
        owner.build_release(root,tmp_path/'bad',repo,contract_version='1.3',purpose='isolated-validation',
            production_admission_ref=receipt['decision_ref'])
    immutable=file_sha(package/'manifest.json')
    withdrawal=uuid.uuid4().hex
    pre=admission.prepare(root,settings.database_path,actor,withdrawal,None,repo,reason='Explicit component withdrawal',action='withdraw')
    admission.confirm(root,settings.database_path,actor,withdrawal,pre['preview_ref']['sha256'],repo)
    with pytest.raises(CompatibilityError):effective_runtime(runtime)
    assert bound_source_paths(runtime,archived,historical=True)==original_paths
    with pytest.raises(CompatibilityError):
        owner.activate_release_v1_1(runtime,repo,staged,uuid.uuid4().hex)
    assert immutable==file_sha(package/'manifest.json')
    assert all(p.read_bytes()==value for p,value in protected.items())


def test_revoked_review_and_changed_sources_do_not_complete_prepared_admission(compat,tmp_path):
    _,settings,_,actor,targets=compat
    grant(settings)
    execute(settings,actor,[request(target) for target in targets])
    root=settings.pipeline_root
    repo,_=committed_source_snapshot(PROJECT,tmp_path/'src',complete=True)
    op=uuid.uuid4().hex
    pre=admission.prepare(root,settings.database_path,actor,op,scope(),repo,reason='Exact component source check')
    source=root/targets[0]['case_ref']['path'];old=source.read_bytes()
    try:
        source.write_bytes(old+b' ')
        with pytest.raises(CompatibilityError):admission.confirm(root,settings.database_path,actor,op,pre['preview_ref']['sha256'],repo)
    finally:source.write_bytes(old)
    from app.profile_compatibility_gateway import manage_reviewer
    manage_reviewer(settings,actor['user_id'],action='revoke',operator='isolated-test',reason='Explicit review revocation')
    with pytest.raises(CompatibilityError):admission.confirm(root,settings.database_path,actor,op,pre['preview_ref']['sha256'],repo)
    manage_reviewer(settings,actor['user_id'],action='grant',operator='isolated-test',reason='New grant must not reuse an old preview')
    with pytest.raises(CompatibilityError):admission.confirm(root,settings.database_path,actor,op,pre['preview_ref']['sha256'],repo)
    assert admission.head(root) is None


def test_missing_release_has_safe_actionable_http_error_without_native_writes(client,settings):
    from conftest import login_and_change_password
    csrf=login_and_change_password(client)
    response=client.post('/api/create/batches/preview',headers={'X-CSRF-Token':csrf},json={
        'business_id':'fixture_business_001','speaker_id':'fixture_speaker_001',
        'operation_id':'production_missing_qualification','configuration':{
            'mode':'free','stage':'launch','revision':0,'combinedTarget':0,
            'cycles':1,'cyclesConfirmed':False,'repurposeEnabled':False,
            'repurposeSourceIds':[],'quantities':{'novel':0,'repurpose':0,'persona':1,'story':0,'conversion':0}}})
    assert response.status_code==409,response.text
    detail=response.json()['detail']
    assert detail['code']=='CREATIVE_STYLE_QUALIFICATION_REQUIRED'
    assert '正式版本' in detail['message'] and '管理员' in detail['next_action']
    assert 'ops-pipeline' not in response.text and '.json' not in response.text
    assert not list(settings.pipeline_root.glob('data/creation_batches/*/intent.json'))
