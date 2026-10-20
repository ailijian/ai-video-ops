"""Contract/unit evidence only; native ASGI Golden proves the Human gates."""
import copy,hashlib,sqlite3,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import delivery_receipt_recovery_v1 as subject
import generation_recovery_v1 as recovery

@pytest.fixture
def context(tmp_path):
    path=tmp_path/'auth.sqlite3';token_hash='c'*64;namespace='d'*32
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE console_principal_namespace(singleton INTEGER,namespace TEXT);CREATE TABLE users(id INTEGER,status TEXT,must_change_password INTEGER,updated_at TEXT,phone TEXT);CREATE TABLE sessions(user_id INTEGER,token_hash TEXT,expires_at TEXT);')
        db.execute('INSERT INTO console_principal_namespace VALUES(1,?)',(namespace,))
        db.execute("INSERT INTO users VALUES(1,'active',0,'original-state','13900000001')")
        db.execute('INSERT INTO sessions VALUES(1,?,?)',(token_hash,(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
    actor={'namespace':namespace,'user_id':1}
    return {'actor':actor,'authorization':recovery.authorization(path,actor,hashlib.sha256(token_hash.encode()).hexdigest())}

def human(context):
    ref={'path':'data/fictional/unit-source.json','sha256':'a'*64}
    review={'schema_version':'generation-batch-review-input-v2.0','reviewer':'13900000001','note':'',
        'items':[{'content_id':'gen_fixture-C001','decision':'approved','note':''}]}
    return {'schema_version':subject.HUMAN,'request_id':'gen_fixture','operation_id':'a'*32,**context,
        'sources':{'request_ref':ref,'source_plan_ref':ref,'batch_ref':ref,'current_authority_sha256':'b'*64,'compatibility_binding_sha256':'c'*64},
        'review_input':review,'review_input_sha256':subject.digest(review),'reviewed_at':'2026-10-19T00:00:00Z',
        'review_sha256':'e'*64,'legacy_review_ref':None}

@pytest.mark.parametrize('mutation',['schema','actor_bool','unknown_force','missing_sha','changed_decision','op_path'])
def test_strict_human_intent_contract(context,mutation):
    value=human(context);subject.check(value,subject.HUMAN)
    if mutation=='schema':value['schema_version']='generation-human-review-intent-v99'
    elif mutation=='actor_bool':value['actor']['user_id']=True
    elif mutation=='unknown_force':value['force']=True
    elif mutation=='missing_sha':value.pop('review_sha256')
    elif mutation=='changed_decision':value['review_input']['items'][0]['decision']='automatic_approve'
    elif mutation=='op_path':value['operation_id']='../../another-request'
    with pytest.raises(subject.ReceiptRecoveryError):subject.check(value,subject.HUMAN)

@pytest.mark.parametrize('change',['session_revoked','user_disabled','regrant_new_epoch','borrowed_principal','database_changed'])
def test_current_local_authorization_and_original_stable_identity(context,tmp_path,change):
    intent=human(context);original=copy.deepcopy(intent)
    subject.identity(context,intent)
    path=context['authorization']['database_path']
    if change=='borrowed_principal':context={**context,'actor':{**context['actor'],'namespace':'f'*32}}
    elif change=='database_changed':context={**context,'authorization':{**context['authorization'],'database_path':str(tmp_path/'missing.sqlite3')}}
    else:
        with sqlite3.connect(path) as db:
            if change=='session_revoked':db.execute('DELETE FROM sessions')
            elif change=='user_disabled':db.execute("UPDATE users SET status='disabled'")
            else:
                db.execute("UPDATE users SET status='disabled',updated_at='revocation'")
                db.execute("UPDATE users SET status='active',updated_at='new-explicit-grant'")
        if change=='regrant_new_epoch':
            context={**context,'authorization':recovery.authorization(path,context['actor'],context['authorization']['session_fingerprint'])}
    with pytest.raises(subject.ReceiptRecoveryError):subject.identity(context,intent)
    assert intent==original

def test_legacy_orphan_is_never_adopted_by_a_new_export(context,tmp_path):
    from export_mix_excel_v1 import prepare_mix_export
    output=tmp_path/'output/orphan.xlsx';output.parent.mkdir();output.write_bytes(b'unknown historical file')
    old=output.read_bytes()
    with pytest.raises(subject.ReceiptRecoveryError) as error:
        prepare_mix_export(pipeline_root=tmp_path,request_id='gen_fixture',batch_path=tmp_path/'approved.json',
            template_path=tmp_path/'output/素材混剪&数字人口播混剪文案导入模板.xlsx',output_path=output,authorization_context=context)
    assert error.value.code=='EXPORT_LEGACY_UNBOUND_ORPHAN'
    assert output.read_bytes()==old and not subject.export_paths(tmp_path,'gen_fixture')[0].exists()

def test_unknown_export_reader_never_falls_back(tmp_path):
    with pytest.raises(subject.ReceiptRecoveryError):
        subject.validate_export_receipt(tmp_path,{'schema_version':'mix-excel-export-receipt-v99'},tmp_path/'output.xlsx')

def test_bound_request_cannot_downgrade_through_a_missing_or_foreign_batch_path(tmp_path):
    intent,_=subject.export_paths(tmp_path,'gen_fixture');intent.parent.mkdir(parents=True)
    intent.write_text('{}',encoding='utf-8')  # Presence fence precedes any malformed-intent parsing.
    with pytest.raises(subject.ReceiptRecoveryError) as error:
        subject.validate_export_receipt(tmp_path,{'schema_version':'mix-excel-export-receipt-v1.0',
            'batch_path':str(tmp_path/'missing-foreign-approved.json')},tmp_path/'output.xlsx',request_id='gen_fixture')
    assert error.value.code=='DELIVERY_SCHEMA_INVALID'

def test_planned_human_intent_is_not_an_approval(context,tmp_path):
    directory=tmp_path/'gen_fixture';directory.mkdir();value=human(context)
    subject.publish(directory/'generation_human_review_intent_v1.json',value,subject.HUMAN)
    state=subject.human_state(directory)
    assert state['state']=='human_review_pending' and state['can_resume']
    assert not state['completed'] and not state['approved']
    assert state['resume_items']==value['review_input']['items']

def test_legacy_review_requires_explicit_current_reconfirmation(context,tmp_path,monkeypatch):
    # Admission helper only: no Approved Batch or Receipt is fabricated here.
    import json
    rid='gen_fixture';directory=recovery.request_root(tmp_path,rid);directory.mkdir(parents=True)
    batch=directory/'generation_batch_v1.json';batch.write_text(json.dumps({'request_id':rid}),encoding='utf-8')
    value=human(context);normalized=value['review_input']
    review={'schema_version':'generation-batch-review-v2.0','request_id':rid,'batch_sha256':subject.file_sha(batch),
        'reviewer':normalized['reviewer'],'note':normalized['note'],'items':normalized['items'],
        'reviewed_at':value['reviewed_at'],'decision':'review_items'}
    path=directory/'generation_human_review_v2.json';path.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    before=path.read_bytes();intent_path=directory/'generation_human_review_intent_v1.json'
    assert not subject.human_state(directory)['approved'] and not intent_path.exists()
    with pytest.raises(subject.ReceiptRecoveryError):subject.human_admission(tmp_path,batch,normalized,None,review)
    monkeypatch.setattr(subject,'source_snapshot',lambda *_:value['sources'])
    changed={**normalized,'note':'a different original decision'}
    with pytest.raises(subject.ReceiptRecoveryError):subject.human_admission(tmp_path,batch,changed,context,review)
    result=subject.human_admission(tmp_path,batch,normalized,context,review)
    assert result['legacy_review_ref']==recovery.ref(tmp_path,path)
    assert path.read_bytes()==before and not (directory/'generation_batch_approval_receipt.json').exists()
