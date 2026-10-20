"""Protocol/unit fixtures only; no fixture decision is production Authority."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import os

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generation_recovery_v1 as subject
from resolve_generation_batch_v1 import generation_snapshot


RID = 'gen_recovery_unit_001'


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return path


def failure():
    return {'schema_version':'generation-batch-v1.0','request_id':RID,'profile':'mix',
        'status':'generation_incomplete','generated_count':0,'contents':[],
        'rejected_generations':[{'scope':'transport_or_response','response_sha256':None}],
        'generation_attempts':[{'accepted_count':0}],'validation':{'passed':False}}


@pytest.fixture
def protocol(tmp_path):
    anchor = put(subject.request_root(tmp_path,RID)/'generation_batch_v1.json',failure())
    bindings = {}
    for key, relative, name in [('request_ref','generation_requests','generation_request_v1.json'),
                              ('source_plan_ref','production_plans','generation_source_plan_v1.json'),
                              ('final_plan_ref','content_plans','content_plan_v1_1_1.json')]:
        bindings[key]=subject.ref(tmp_path,put(tmp_path/'data'/relative/RID/name,{'request_id':RID}))
    bindings.update(generation_projection_sha256='1'*64,content_memory_sha256='2'*64,
        source_context_sha256='3'*64,current_authority_sha256='8'*64,live_content_ledger_ref=None,
        selected_concept_ids=['CONCEPT_001'], compatibility_binding_sha256='4'*64)
    intent={'schema_version':subject.INTENT,'request_id':RID,'operation_id':'a'*32,
        'anchor_ref':subject.ref(tmp_path,anchor),'parent_ref':subject.ref(tmp_path,anchor),
        'bindings':bindings,'actor':{'namespace':'b'*32,'user_id':1},
        'authorization':{'database_path':'unit-not-execution','session_fingerprint':'5'*64,'user_state_sha256':'6'*64},
        'authorization_context_digest':'7'*64}
    return tmp_path,anchor,intent


def admit(protocol, intent=None):
    root,anchor,value=protocol
    value=intent or value
    directory=subject.operation_root(root,RID,value['operation_id'])
    subject.publish(directory/'intent.json',value,subject.INTENT)
    return directory


def terminal(protocol,directory,outcome='outcome_unknown',batch=None):
    root,anchor,intent=protocol
    saved=subject.read(directory/'intent.json')
    value={'schema_version':subject.RESULT,'intent_ref':subject.ref(root,directory/'intent.json'),
        'parent_ref':saved['parent_ref'],'outcome':outcome,
        'candidate_ref':None,'batch_ref':subject.ref(root,batch) if batch else None,
        'review_pack_ref':None,'validation':{'ready_for_human_review':False}}
    subject.publish(directory/'result.json',value,subject.RESULT)
    return value


def test_original_zero_output_is_present_but_never_ready(protocol):
    root,anchor,_=protocol
    state=generation_snapshot(root,RID)
    assert state['artifact_present'] and not state['ready_for_human_review']
    assert state['recovery_state']=='retry_available' and state['can_retry']
    assert subject.graph(root,RID)['batch']==anchor


@pytest.mark.parametrize('mutation',[ 'unknown_schema','unknown_field','bad_operation','bad_sha','missing_parent','wrong_boolean'])
def test_strict_schema_and_typed_boolean(protocol,mutation):
    root,anchor,intent=protocol
    value=copy.deepcopy(intent)
    version=subject.INTENT
    if mutation=='unknown_schema':value['schema_version']='generation-recovery-intent-v99'
    if mutation=='unknown_field':value['force']=True
    if mutation=='bad_operation':value['operation_id']='../x'
    if mutation=='bad_sha':value['anchor_ref']['sha256']='bad'
    if mutation=='missing_parent':del value['parent_ref']
    if mutation=='wrong_boolean':
        directory=admit(protocol)
        value=terminal(protocol,directory)
        value['validation']['ready_for_human_review']=1
        version=subject.RESULT
    with pytest.raises(subject.RecoveryError):subject.check(value,version)


def test_same_operation_equivalent_publish_and_conflict(protocol):
    directory=admit(protocol)
    before=(directory/'intent.json').read_bytes()
    admit(protocol)
    assert (directory/'intent.json').read_bytes()==before
    changed=copy.deepcopy(protocol[2]);changed['bindings']['content_memory_sha256']='a'*64
    with pytest.raises(subject.RecoveryError,match='conflict'):admit(protocol,changed)


def test_pending_and_unknown_result_are_not_successful(protocol):
    directory=admit(protocol)
    assert subject.graph(protocol[0],RID)['pending']==protocol[2]
    assert generation_snapshot(protocol[0],RID)['recovery_state']=='pending'
    terminal(protocol,directory)
    state=generation_snapshot(protocol[0],RID)
    assert state['recovery_state']=='outcome_unknown' and not state['ready_for_human_review']


@pytest.mark.parametrize('fault',['fork','missing_parent','wrong_anchor','changed_ref','foreign_request','unknown_result','dispatch_mismatch','missing_intent'])
def test_invalid_graph_fails_closed(protocol,fault):
    root,anchor,intent=protocol
    value=copy.deepcopy(intent)
    if fault=='missing_parent':value['parent_ref']['sha256']='0'*64
    if fault=='wrong_anchor':value['anchor_ref']['sha256']='0'*64
    if fault=='foreign_request':value['request_id']='other'
    directory=admit(protocol,value)
    if fault=='fork':
        other=copy.deepcopy(intent);other['operation_id']='c'*32;admit(protocol,other)
    if fault=='changed_ref':put(root/intent['bindings']['request_ref']['path'],{'changed':True})
    if fault=='unknown_result':put(directory/'result.json',{'schema_version':'unknown'})
    if fault=='dispatch_mismatch':
        subject.publish(directory/'dispatch.json',{'schema_version':subject.DISPATCH,
            'intent_ref':{'path':'wrong','sha256':'0'*64}},subject.DISPATCH)
    if fault=='missing_intent':(directory/'intent.json').unlink();put(directory/'candidate.json',{})
    with pytest.raises((subject.RecoveryError,OSError)):subject.graph(root,RID)


def test_unpublished_atomic_temporary_is_not_an_operation(protocol):
    root,anchor,_=protocol
    directory=subject.operation_root(root,RID,'c'*32)
    directory.mkdir(parents=True)
    (directory/('.'+'d'*32+'.tmp')).write_text('partial',encoding='utf-8')
    assert subject.graph(root,RID)['head_ref']==subject.ref(root,anchor)
    assert subject.graph(root,RID)['pending'] is None


@pytest.mark.parametrize('name',['../outside','/absolute','data\\windows','data/../escape'])
def test_unsafe_reference_rejected(protocol,name):
    with pytest.raises(subject.RecoveryError):subject.resolve_ref(protocol[0],{'path':name,'sha256':'a'*64})


def test_junction_or_symlink_cannot_escape_the_isolated_runtime(tmp_path):
    root=tmp_path/'runtime';outside=tmp_path/'outside';root.mkdir();outside.mkdir()
    target=put(outside/'artifact.json',{'test_only':True})
    link=root/'linked'
    if os.name=='nt':
        import _winapi
        _winapi.CreateJunction(str(outside),str(link))
    else:
        link.symlink_to(outside,target_is_directory=True)
    try:
        with pytest.raises(subject.RecoveryError):
            subject.resolve_ref(root,{'path':'linked/artifact.json','sha256':subject.file_sha(target)})
    finally:
        if os.name=='nt':link.rmdir()
        else:link.unlink()


@pytest.mark.parametrize('field',['contents','status','profile','rejections','accepted'])
def test_retry_scope_is_only_zero_output_transport_failure(field):
    batch=failure()
    if field=='contents':batch['contents']=[{}]
    if field=='status':batch['status']='review_required'
    if field=='profile':batch['profile']='news'
    if field=='rejections':batch['rejected_generations'][0]['scope']='quality'
    if field=='accepted':batch['generation_attempts'][0]['accepted_count']=1
    assert not subject.transport_failure(batch)


def test_zero_output_response_failure_retains_its_response_sha_and_can_retry():
    batch=failure()
    batch['rejected_generations'][0]['response_sha256']='f'*64
    assert subject.transport_failure(batch)
    batch['validation']['passed']=True
    assert not subject.transport_failure(batch)


@pytest.mark.parametrize('name',['generation_human_review_v2.json','approved_generation_batch_v1.json','generation_batch_approval_receipt.json','generation_export_closure_v1.json'])
def test_human_or_closed_bundle_prevents_retry(protocol,name):
    put(subject.request_root(protocol[0],RID)/name,{})
    with pytest.raises(subject.RecoveryError):subject.require_unreviewed(protocol[0],RID)
    assert generation_snapshot(protocol[0],RID)['can_retry'] is False


@pytest.mark.parametrize('change',['namespace','disabled','password_reset','expired','revoked_session','borrowed_user','changed_user_state'])
def test_current_local_authorization_is_rechecked(tmp_path,change):
    path=tmp_path/'console.sqlite3'
    future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE console_principal_namespace(singleton INTEGER,namespace TEXT); CREATE TABLE users(id INTEGER,status TEXT,must_change_password INTEGER,updated_at TEXT); CREATE TABLE sessions(user_id INTEGER,token_hash TEXT,expires_at TEXT);')
        db.execute('INSERT INTO console_principal_namespace VALUES(1,?)',('a'*32,))
        db.execute("INSERT INTO users VALUES(1,'active',0,'original')")
        db.execute('INSERT INTO sessions VALUES(1,?,?)',('unit-session-hash',future))
    actor={'namespace':'a'*32,'user_id':1}
    fingerprint=hashlib.sha256(b'unit-session-hash').hexdigest()
    proof=subject.authorization(path,actor,fingerprint)
    intent={'actor':actor,'authorization':proof,'authorization_context_digest':subject.digest({'actor':actor,'authorization':proof})}
    subject.verify_authorization(intent)
    with sqlite3.connect(path) as db:
        if change=='namespace':db.execute('UPDATE console_principal_namespace SET namespace=?',('b'*32,))
        if change=='disabled':db.execute("UPDATE users SET status='disabled'")
        if change=='password_reset':db.execute('UPDATE users SET must_change_password=1')
        if change=='expired':db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
        if change=='revoked_session':db.execute('DELETE FROM sessions')
        if change=='changed_user_state':db.execute("UPDATE users SET updated_at='changed'")
    if change=='borrowed_user':intent['actor']={'namespace':'a'*32,'user_id':2}
    with pytest.raises(subject.RecoveryError):subject.verify_authorization(intent)


def test_readiness_requires_all_native_conditions():
    good={'status':'review_required','contents':[{'concept_ref':'C1'}],
        'validation':{'passed':True,'material_centers_preserved':True},
        'script_generation_contract':{'material_center_validation':{'passed':True}}}
    assert subject.ready_for_review(good,['C1'])
    for field in ['passed','material_centers_preserved']:
        bad=copy.deepcopy(good);bad['validation'][field]=False
        assert not subject.ready_for_review(bad,['C1'])
    assert not subject.ready_for_review(good,['OTHER'])
    assert not subject.ready_for_review(good,[])
    bad=copy.deepcopy(good);bad['script_generation_contract']['material_center_validation']['passed']=False
    assert not subject.ready_for_review(bad,['C1'])
