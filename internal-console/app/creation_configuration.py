"""Per-operator editable drafts, never evidence of production eligibility."""
import hashlib
import json
import uuid
from .canonical_gateway import CanonicalOperationError
from .database import transaction
from .customer_gateway import get_customer_detail
from .path_safety import validate_identifier

TYPES={'novel','repurpose','persona','story','conversion'}
FIELDS={'mode','stage','quantities','combinedTarget','cycles','cyclesConfirmed','repurposeEnabled','repurposeSourceIds','revision','previewRevision'}

def invalid(code='CREATIVE_STYLE_DRAFT_INVALID'):
    raise CanonicalOperationError(code,'配置草稿需要重新核对。','请读取最新草稿，明确数量后重新保存。')

def validate_payload(payload):
    if not isinstance(payload,dict) or set(payload)!={'speaker_id','configuration'}:invalid()
    state=payload['configuration']
    if (not isinstance(state,dict) or set(state)-FIELDS or not isinstance(state.get('mode'),str)
            or state['mode'] not in {'stage','free'} or not isinstance(state.get('stage'),str)
            or state['stage'] not in {'launch','trust','steady'}):invalid()
    quantities=state.get('quantities')
    if not isinstance(quantities,dict) or set(quantities)!=TYPES:invalid()
    def integer(value):return type(value) is int and 0<=value<=9007199254740991
    if any(value is not None and not integer(value) for value in quantities.values()):invalid()
    if any(state.get(key) is not None and not integer(state[key]) for key in ['combinedTarget','cycles']):invalid()
    if not integer(state.get('revision')) or any(type(state.get(key)) is not bool for key in ['cyclesConfirmed','repurposeEnabled']):invalid()
    selected=state.get('repurposeSourceIds',[])
    if not isinstance(selected,list) or len(selected)>40 or any(not isinstance(v,str) for v in selected) or len(set(selected))!=len(selected):invalid()
    for source_id in selected:
        try:validate_identifier(source_id)
        except ValueError:invalid()
    speaker=payload['speaker_id']
    if not isinstance(speaker,str) or len(speaker)>128:invalid()
    if speaker:
        try:validate_identifier(speaker)
        except ValueError:invalid()
    return {'speaker_id':speaker,'configuration':{**state,'previewRevision':None}}

def draft(settings,user_id,business_id,*,payload=None,expected_revision=None):
    try:validate_identifier(business_id)
    except ValueError:invalid()
    # Verify the exact customer exists. A draft does not require or confer eligibility.
    get_customer_detail(settings,business_id)
    if payload is not None:
        payload=validate_payload(payload)
        raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        sha=hashlib.sha256(raw.encode()).hexdigest()
    with transaction(settings.database_path,immediate=payload is not None) as connection:
        row=connection.execute('SELECT * FROM creation_configuration_drafts WHERE user_id=? AND business_id=?',(user_id,business_id)).fetchone()
        if payload is not None and (row is None or row['payload_sha256']!=sha):
            if type(expected_revision) is not int or expected_revision!=(row['revision'] if row else 0):invalid('CREATIVE_STYLE_DRAFT_CONFLICT')
            connection.execute('INSERT INTO creation_configuration_drafts VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,business_id) DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json,payload_sha256=excluded.payload_sha256,operation_id=excluded.operation_id',
                (user_id,business_id,expected_revision+1,raw,sha,'config_'+uuid.uuid4().hex))
            row=connection.execute('SELECT * FROM creation_configuration_drafts WHERE user_id=? AND business_id=?',(user_id,business_id)).fetchone()
        if not row:return {'draft':None,'revision':0}
        return {'draft':json.loads(row['payload_json']),'revision':row['revision'],'operation_id':row['operation_id']}
