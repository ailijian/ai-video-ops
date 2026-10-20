"""Shared contracts only. Native Review/Export remain the sole receipt writers."""
from pathlib import Path
import sqlite3

import generation_recovery_v1 as recovery
from human_review_operations_v1 import digest, file_sha, read, write_once
from profile_compatibility_contract_v1_1 import ACTOR, REF, HASH, TEXT, OPERATION, ID, obj, array, validate

HUMAN = 'generation-human-review-intent-v1.0'
EXPORT = 'mix-export-intent-v1.0'
PUBLICATION = 'mix-export-publication-v1.0'
EXPORT_RECEIPT = 'mix-excel-export-receipt-v1.1'
AUTH = obj({'database_path': TEXT, 'session_fingerprint': HASH, 'user_state_sha256': HASH})
CONTEXT = obj({'actor': ACTOR, 'authorization': AUTH})
SOURCES = obj({'request_ref': REF, 'source_plan_ref': REF, 'batch_ref': REF,
    'current_authority_sha256': HASH, 'compatibility_binding_sha256': HASH})
STRING={'type':'string'}
REVIEW_INPUT=obj({'schema_version':{'const':'generation-batch-review-input-v2.0'},'reviewer':TEXT,'note':STRING,
    'items':array({'oneOf':[
        obj({'content_id':ID,'decision':{'enum':['approved','rejected']},'note':STRING}),
        obj({'content_id':ID,'decision':{'const':'revised'},'note':STRING,'revised_title':TEXT,
            'revised_narration':TEXT,'meaning_preserved':{'const':True},'new_facts_added':{'const':False}})]},1)})
SCHEMAS = {
    HUMAN: obj({'schema_version': {'const': HUMAN}, 'request_id': ID, 'operation_id': OPERATION,
        'actor': ACTOR, 'authorization': AUTH, 'sources': SOURCES, 'review_input_sha256': HASH,
        'reviewed_at':TEXT,'review_sha256':HASH,
        'review_input':REVIEW_INPUT,
        'legacy_review_ref': {'oneOf':[{'type':'null'},REF]}}),
    EXPORT: obj({'schema_version': {'const': EXPORT}, 'request_id': ID, 'business_id': ID,
        'operation_id': OPERATION, 'actor': ACTOR, 'authorization': AUTH, 'sources': SOURCES,
        'approved_batch_ref': REF, 'approval_receipt_ref': REF, 'template_ref': REF,
        'output_path': TEXT, 'exporter_version': TEXT, 'mode': {'const':'mix'}}),
    PUBLICATION: obj({'schema_version': {'const': PUBLICATION}, 'intent_ref': REF,
        'output_path': TEXT, 'output_sha256': HASH}),
}
SCHEMAS[EXPORT_RECEIPT]=obj({'schema_version':{'const':EXPORT_RECEIPT},'exporter_version':TEXT,
    'fixture_only':{'const':False},'batch_path':TEXT,'batch_sha256':HASH,'template_path':TEXT,
    'template_sha256':HASH,'output_path':TEXT,'output_sha256':HASH,'exported_row_count':{'type':'integer','minimum':1},
    'row_4_headers':{'type':'array','items':TEXT,'minItems':2,'maxItems':2},'first_data_row':{'const':5},
    'internal_metadata_columns_added':{'const':False},'source_template_modified':{'const':False},
    'validation_passed':{'const':True},'export_intent_ref':REF,'publication_ref':REF})
ERRORS = ('DELIVERY_AUTHORIZATION_REQUIRED','DELIVERY_ACTOR_CONFLICT','DELIVERY_SOURCE_CHANGED',
    'DELIVERY_INTENT_CONFLICT','DELIVERY_SCHEMA_INVALID','HUMAN_BUNDLE_INVALID',
    'EXPORT_LEGACY_UNBOUND_ORPHAN','EXPORT_PUBLICATION_INVALID')

class ReceiptRecoveryError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message); self.code=code

def check(value, version):
    try: validate(value, SCHEMAS[version])
    except (RuntimeError, KeyError, ValueError, TypeError) as exc:
        raise ReceiptRecoveryError('DELIVERY_SCHEMA_INVALID','Unknown or malformed receipt recovery contract') from exc
    return value

def publish(path, value, version):
    check(value,version)
    try: write_once(path,value)
    except RuntimeError as exc:
        raise ReceiptRecoveryError('DELIVERY_INTENT_CONFLICT','Immutable delivery intent differs') from exc

def identity(context, intent=None):
    try:
        validate(context,CONTEXT)
        current=recovery.authorization(context['authorization']['database_path'],context['actor'],
            context['authorization']['session_fingerprint'])
        if current!=context['authorization']: raise ValueError('Authorization changed')
    except (RuntimeError,KeyError,ValueError,TypeError) as exc:
        raise ReceiptRecoveryError('DELIVERY_AUTHORIZATION_REQUIRED','A current trusted Console principal and Session are required') from exc
    if intent and (intent['actor']!=context['actor'] or
            intent['authorization']['user_state_sha256']!=current['user_state_sha256'] or
            intent['authorization']['database_path']!=current['database_path']):
        raise ReceiptRecoveryError('DELIVERY_ACTOR_CONFLICT','Original stable reviewer or authorization state differs')
    return current

def actor_phone(context):
    identity(context)
    with sqlite3.connect(Path(context['authorization']['database_path']).as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT phone FROM users WHERE id=?',(context['actor']['user_id'],)).fetchone()
    return str(row[0])

def source_snapshot(root, batch_path):
    """Exact current native source, without treating a partial Human bundle as history."""
    from resolve_generation_content_plan_v1 import read_request_and_source_plan
    from show_customer_status_v1 import resolve_current_persona, resolve_speaker_persona
    root=Path(root).resolve();batch_path=Path(batch_path).resolve();batch=read(batch_path)
    rid=batch['request_id'];request_path,request,source_path,plan=read_request_and_source_plan(root,rid)
    from profile_compatibility_release_v1_1 import CONFIG,effective_runtime
    if (root/CONFIG).is_file():effective_runtime(root,pinned=plan.get('profile_compatibility_v1_1'))
    business=resolve_current_persona(root,request['persona_id'],'business')
    speaker=resolve_speaker_persona(root,business,request['speaker_persona']) if request.get('speaker_persona') else None
    lineage=request.get('lineage') or {}
    if (business['file_sha256']!=(lineage.get('business_persona_ref') or {}).get('file_sha256') or
        speaker and speaker['file_sha256']!=(lineage.get('speaker_persona_ref') or {}).get('file_sha256')):
        raise ReceiptRecoveryError('DELIVERY_SOURCE_CHANGED','Current approved Persona differs from the original Request')
    def refs(value):
        if isinstance(value,dict):
            expected=value.get('sha256') or value.get('file_sha256')
            if value.get('path') and expected:yield value['path'],expected
            for child in value.values():yield from refs(child)
        elif isinstance(value,list):
            for child in value:yield from refs(child)
    for name,expected in refs(batch.get('lineage') or {}):
        p=Path(name).resolve()
        if not p.is_relative_to(root) or not p.is_file() or file_sha(p)!=expected:
            raise ReceiptRecoveryError('DELIVERY_SOURCE_CHANGED','Frozen source lineage changed')
    return {'request_ref':recovery.ref(root,request_path),'source_plan_ref':recovery.ref(root,source_path),
        'batch_ref':recovery.ref(root,batch_path),'current_authority_sha256':digest({'business':business['file_sha256'],
            'speaker':speaker['file_sha256'] if speaker else None,'constraints':business.get('production_constraints')}),
        'compatibility_binding_sha256':digest(plan.get('profile_compatibility_v1_1'))}

def human_admission(root, batch_path, normalized_input, context, canonical_review=None):
    import uuid
    root=Path(root).resolve();batch=read(batch_path);rid=batch['request_id']
    directory=recovery.request_root(root,rid);path=directory/'generation_human_review_intent_v1.json'
    existing=check(read(path),HUMAN) if path.is_file() else None
    proof=identity(context,existing)
    if normalized_input['reviewer']!=actor_phone(context):
        raise ReceiptRecoveryError('DELIVERY_ACTOR_CONFLICT','Reviewer label must match the trusted current principal')
    sources=source_snapshot(root,batch_path)
    if existing:
        if existing['sources']!=sources or existing['review_input_sha256']!=digest(normalized_input):
            raise ReceiptRecoveryError('DELIVERY_INTENT_CONFLICT','Original Human input or exact source differs')
        persisted=directory/'generation_human_review_v2.json'
        if persisted.is_file() and file_sha(persisted)!=existing['review_sha256']:
            raise ReceiptRecoveryError('DELIVERY_INTENT_CONFLICT','Persisted Human decision bytes changed')
        if canonical_review is not None:
            import hashlib,json
            expected=hashlib.sha256(json.dumps(canonical_review,ensure_ascii=False,indent=2).encode()).hexdigest()
            if canonical_review.get('reviewed_at')!=existing['reviewed_at'] or expected!=existing['review_sha256']:
                raise ReceiptRecoveryError('DELIVERY_INTENT_CONFLICT','Native Human decision differs from the frozen operation')
        return existing
    legacy=directory/'generation_human_review_v2.json'
    if legacy.is_file():
        # Called only by a new explicit authenticated submit, never by a Reader.
        old=read(legacy)
        from review_generation_batch_v2 import _review_equivalent
        if not _review_equivalent(old,normalized_input,request_id=rid,batch_sha256=file_sha(batch_path)):
            raise ReceiptRecoveryError('DELIVERY_ACTOR_CONFLICT','Legacy Human decision cannot be attributed to this explicit reconfirmation')
    if (directory/'generation_batch_approval_receipt.json').is_file():return None
    if canonical_review is None:return None  # Authenticated read admission only.
    import hashlib,json
    intent={'schema_version':HUMAN,'request_id':rid,'operation_id':uuid.uuid4().hex,'actor':context['actor'],
        'authorization':proof,'sources':sources,'review_input_sha256':digest(normalized_input),
        'review_input':normalized_input,
        'reviewed_at':canonical_review['reviewed_at'],
        'review_sha256':file_sha(legacy) if legacy.is_file() else hashlib.sha256(json.dumps(canonical_review,ensure_ascii=False,indent=2).encode()).hexdigest(),
        'legacy_review_ref':recovery.ref(root,legacy) if legacy.is_file() else None}
    publish(path,intent,HUMAN);return intent

def human_state(directory):
    """Projection only. No partial artifact is Human Approval."""
    directory=Path(directory);review=directory/'generation_human_review_v2.json'
    approved=directory/'approved_generation_batch_v1.json';rejected=directory/'reviewed_generation_batch_v1.json'
    receipt=directory/'generation_batch_approval_receipt.json'
    result={'state':'no_human_review','completed':False,'approved':False,'can_resume':False}
    intent_path=directory/'generation_human_review_intent_v1.json'
    intent=check(read(intent_path),HUMAN) if intent_path.is_file() else None
    if intent:
        if digest(intent['review_input'])!=intent['review_input_sha256'] or review.is_file() and file_sha(review)!=intent['review_sha256']:
            raise ReceiptRecoveryError('HUMAN_BUNDLE_INVALID','Human operation and persisted decision differ')
        if not review.is_file() and not any(p.exists() for p in [approved,rejected,receipt]):
            return {**result,'state':'human_review_pending','can_resume':True,
                'resume_items':intent['review_input']['items'],'resume_note':intent['review_input']['note']}
    if receipt.is_file():
        value=read(receipt);output=approved if approved.is_file() else rejected
        bound=value.get('approved_batch') or value.get('reviewed_batch') or {}
        if (not output.is_file() or value.get('schema_version')!='generation-batch-approval-receipt-v1.0' or
                value.get('human_gate') is not True or value.get('request_id')!=directory.name or
                bound.get('sha256')!=file_sha(output) or Path(bound.get('path') or '').resolve()!=output.resolve()):
            raise ReceiptRecoveryError('HUMAN_BUNDLE_INVALID','Human receipt does not validate its complete bundle')
        source=value.get('source_batch') or {};source_path=Path(source.get('path') or '')
        if not source_path.is_file() or file_sha(source_path)!=source.get('sha256'):
            raise ReceiptRecoveryError('HUMAN_BUNDLE_INVALID','Approved source SHA differs')
        review_ref=value.get('review_file') or {};historical=Path(review_ref.get('path') or '')
        if (historical.is_file() and file_sha(historical)!=review_ref.get('sha256')) or (intent and not review.is_file()):
            raise ReceiptRecoveryError('HUMAN_BUNDLE_INVALID','Human decision SHA differs')
        return {**result,'state':'human_review_complete','completed':True,'approved':value.get('status')=='approved','can_resume':False}
    if not any(p.exists() for p in [review,approved,rejected,receipt]):return result
    if not review.is_file():raise ReceiptRecoveryError('HUMAN_BUNDLE_INVALID','Human decision is missing')
    decision=read(review)
    if decision.get('schema_version')!='generation-batch-review-v2.0':
        raise ReceiptRecoveryError('HUMAN_BUNDLE_INVALID','Unknown Human Review schema')
    result.update(state='human_review_pending',can_resume=True,resume_items=decision.get('items') or [],resume_note=decision.get('note') or '')
    output=approved if approved.is_file() else rejected
    if output.is_file():result['state']='human_receipt_pending'
    return result

def export_paths(root,rid):
    directory=recovery.request_root(root,rid)
    return directory/'generation_export_intent_v1.json',directory/'generation_export_publication_v1.json'

def validate_publication(root,intent_path,output_path):
    intent=check(read(intent_path),EXPORT);_,path=export_paths(root,intent['request_id'])
    if Path(intent_path).resolve()!=export_paths(root,intent['request_id'])[0].resolve():
        raise ReceiptRecoveryError('EXPORT_PUBLICATION_INVALID','Intent does not belong to the canonical Request')
    if not path.is_file():raise ReceiptRecoveryError('EXPORT_PUBLICATION_INVALID','Export publication witness is missing')
    publication=check(read(path),PUBLICATION)
    if (publication['intent_ref']!=recovery.ref(root,intent_path) or
        publication['output_path']!=intent['output_path'] or
        Path(output_path).resolve()!=(Path(root)/intent['output_path']).resolve() or
        publication['output_sha256']!=file_sha(output_path)):
        raise ReceiptRecoveryError('EXPORT_PUBLICATION_INVALID','Workbook differs from the source-bound published file')
    return publication

def validate_export_receipt(root,receipt,output,*,request_id=None):
    version=receipt.get('schema_version')
    if request_id and export_paths(root,request_id)[0].is_file() and version!=EXPORT_RECEIPT:
        raise ReceiptRecoveryError('DELIVERY_SCHEMA_INVALID','A bound Request cannot downgrade its Export Receipt')
    if version=='mix-excel-export-receipt-v1.0':
        batch=Path(receipt.get('batch_path') or '')
        if batch.is_file() and export_paths(root,str(read(batch).get('request_id') or ''))[0].is_file():
            raise ReceiptRecoveryError('DELIVERY_SCHEMA_INVALID','A bound export cannot downgrade to a legacy Receipt')
        return  # Exact historical reader retained.
    if version!=EXPORT_RECEIPT:raise ReceiptRecoveryError('DELIVERY_SCHEMA_INVALID','Unknown Export Receipt version')
    check(receipt,EXPORT_RECEIPT)
    intent_path=recovery.resolve_ref(root,receipt.get('export_intent_ref'))
    intent=check(read(intent_path),EXPORT)
    if request_id and intent['request_id']!=request_id:
        raise ReceiptRecoveryError('EXPORT_PUBLICATION_INVALID','Export Receipt belongs to another Request')
    publication=validate_publication(root,intent_path,output)
    _,publication_path=export_paths(root,intent['request_id'])
    if (receipt.get('publication_ref')!=recovery.ref(root,publication_path) or
        receipt.get('batch_sha256')!=intent['approved_batch_ref']['sha256'] or
        Path(receipt['batch_path']).resolve()!=recovery.resolve_ref(root,intent['approved_batch_ref']) or
        Path(receipt['template_path']).resolve()!=(Path(root)/intent['template_ref']['path']).resolve() or
        receipt['template_sha256']!=intent['template_ref']['sha256'] or
        receipt['exporter_version']!=intent['exporter_version'] or
        Path(receipt['output_path']).resolve()!=Path(output).resolve() or
        receipt['row_4_headers']!=['视频制作标题','视频制作口播内容'] or
        receipt.get('output_sha256')!=publication['output_sha256'] or receipt.get('validation_passed') is not True):
        raise ReceiptRecoveryError('EXPORT_PUBLICATION_INVALID','Receipt does not bind the exact native publication')
