"""C01-C03 constraints for original Mix owners; snapshots confer no approval."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path
from human_review_operations_v1 import io_path, read, write_once

LEGACY_REQUEST = 'generation-request-v1.0'
STYLE_REQUEST = 'generation-request-v1.1'
INTENT = 'mix-style-intent-v1.0'
RULES = Path(__file__).with_name('creative_style_rules_v1.json')
CONTRACTS = Path(__file__).with_name('creative_style_contracts_v1.json')
PRODUCT_PATH = Path('docs/deliveries/creation-batch-ux-1/BASELINE.md')
STYLE_FIELDS = ('style_id','style_version','production_profile','definition','required_fact_roles',
    'required_speaker_roles','forbidden_claims','structure','acceptance_samples','allowed_quantities','cta_policy','target_duration_advisory')
VALUE_FIELDS = ('primary_products_or_services','product_or_service_facts','included_service_facts','pricing_facts')
NEED_FIELDS = ('core_audience','customer_pains','customer_use_cases')
CTA_PREFIX = 'neutral-service-inquiry-v1:'

class CreativeStyleError(RuntimeError):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def file_sha(path):
    return hashlib.sha256(io_path(path).read_bytes()).hexdigest()

def check(value,contract):
    # Adapt this bounded approved vocabulary to the existing Native validator;
    # no dependency or permissive second validation engine.
    from profile_compatibility_contract_v1_1 import validate
    schema=read(CONTRACTS)[contract]
    def expand(node):
        if '$ref' in node:
            prefix='#/$defs/'
            if not node['$ref'].startswith(prefix):raise ValueError('External schema reference')
            return expand(schema['$defs'][node['$ref'][len(prefix):]])
        if 'anyOf' in node:return {'oneOf':[expand(v) for v in node['anyOf']]}
        if isinstance(node.get('type'),list):return {'oneOf':[expand({**node,'type':kind}) for kind in node['type']]}
        allowed={'$schema','$defs','type','properties','required','additionalProperties','items','minItems','minLength','pattern','const','enum','minimum'}
        if set(node)-allowed:raise ValueError('Unsupported schema vocabulary')
        result={k:v for k,v in node.items() if k not in {'$schema','$defs'}}
        if 'properties' in result:result['properties']={k:expand(v) for k,v in result['properties'].items()}
        if 'items' in result:result['items']=expand(result['items'])
        return result
    try: validate(value,expand(schema))
    except Exception as exc:
        raise CreativeStyleError('CREATIVE_STYLE_SCHEMA_INVALID',f'Invalid {contract} contract') from exc
    return value

def artifact(path,owner,identifier,version):
    path=Path(path).resolve()
    return {'owner':owner,'id':str(identifier),'version':str(version),'path':str(path),'sha256':file_sha(path)}

def pinned(reference):
    try:
        path=Path(reference['path'])
        if not path.is_absolute() or file_sha(path)!=reference['sha256']: raise ValueError('Reference changed')
        return read(path)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise CreativeStyleError('CREATIVE_STYLE_SOURCE_CHANGED','Pinned Style source is missing or changed') from exc

def definition(style_id,*,executable=False):
    rules=read(RULES);rule=rules['styles'].get(style_id)
    if rule is None: raise CreativeStyleError('CREATIVE_STYLE_UNKNOWN','Unknown creative style')
    if executable and style_id not in rules['enabled_styles']:
        raise CreativeStyleError('CREATIVE_STYLE_NOT_ENABLED','Style review and qualification remain open')
    return rule

def active_qualification(root):
    from profile_compatibility_release_v1_1 import CONFIG,effective_runtime
    if not io_path(Path(root)/CONFIG).is_file():
        raise CreativeStyleError('CREATIVE_STYLE_QUALIFICATION_REQUIRED','An explicitly activated Native Compatibility Release is required')
    return effective_runtime(root)

def catalog_snapshot(root,*,publish=True):
    """C01 binds actual active Native scope and retained approved product bytes."""
    root=Path(root).resolve();active=active_qualification(root);rules=read(RULES)
    declared={v['path']:v for v in active['manifest']['source_files']}
    for name in ['creative_style_v1.py','creative_style_rules_v1.json','creative_style_contracts_v1.json']:
        relative='ops-pipeline/scripts/'+name
        if relative not in declared or declared[relative]['checkout_sha256']!=file_sha(RULES.with_name(name)):
            raise CreativeStyleError('CREATIVE_STYLE_QUALIFICATION_REQUIRED','Activated Release omits the exact executing Style consumer/contracts')
    source=root.parent/PRODUCT_PATH
    if not io_path(source).is_file() or file_sha(source)!=rules['product_rule_baseline_sha256']:
        raise CreativeStyleError('CREATIVE_STYLE_PRODUCT_RULE_CHANGED','Exact approved product input is required')
    retained=root/'data/creative_style_catalogs/product_rules'/(file_sha(source)+'.md')
    from generation_recovery_v1 import publish_text
    if publish: publish_text(retained,io_path(source).read_text(encoding='utf-8'))
    product_ref={'owner':'delivery-baseline','id':'creation-batch-ux-1','version':'1','path':str(retained),'sha256':file_sha(source)}
    patterns,decisions={},{}
    for head in active['graph']['heads'].values():
        target=head['target']
        if not head['effective'] or target['target_profile']!='mix': continue
        for ref,owner,identifier,version,dest in [
            (target['pattern_ref'],'native-pattern',target['pattern_id'],'pattern-v1.0',patterns),
            (head['effective'],'native-compatibility',head['effective']['sha256'],'1.1',decisions)]:
            path=active['bundle_root']/ref['path']
            if file_sha(path)!=ref['sha256']:
                raise CreativeStyleError('CREATIVE_STYLE_QUALIFICATION_REQUIRED','Qualified Native source changed')
            dest[ref['sha256']]=artifact(path,owner,identifier,version)
    if not patterns or not decisions:
        raise CreativeStyleError('CREATIVE_STYLE_QUALIFICATION_REQUIRED','No active Mix Pattern/Compatibility scope')
    release=active['binding']['release_ref']
    release_ref=artifact(root/release['path'],'native-release',active['manifest']['release_id'],active['manifest']['schema_version'])
    styles=[]
    for name in rules['enabled_styles']:
        item={key:copy.deepcopy(definition(name)[key]) for key in STYLE_FIELDS}
        item.update(approved_product_rule_ref=product_ref,pattern_scope_refs=list(patterns.values()),
            compatibility_scope_refs=list(decisions.values()),release_ref=release_ref)
        styles.append(item)
    catalog=check({'schema_version':'creative-style-catalog-v1.0','catalog_id':'native-mix-creative-styles',
        'catalog_version':rules['rule_set_version'],'styles':styles},'C01')
    path=root/'data/creative_style_catalogs'/digest(catalog)/'catalog.json'
    if publish: write_once(path,catalog)
    reference={'owner':'native-mix-style','id':catalog['catalog_id'],'version':catalog['catalog_version'],
        'path':str(path),'sha256':file_sha(path) if publish else hashlib.sha256(json.dumps(catalog,ensure_ascii=False,indent=2).encode()).hexdigest()}
    return reference,catalog

def catalog_for_admission(root):
    return catalog_snapshot(root)[0]

def admission_preflight(root,business_id,speaker_id,style_id,configuration,entry):
    """Read-only qualification; confirmation always rechecks under original locks."""
    from show_customer_status_v1 import resolve_current_persona,resolve_speaker_persona
    rule=definition(style_id,executable=True)
    payload=normalize_configuration(configuration,style_id)
    business=resolve_current_persona(root,business_id,'business')
    speaker=resolve_speaker_persona(root,business,speaker_id)
    validate_style_facts(style_id,rule,read(business['path']),read(speaker['path']))
    _,catalog=catalog_snapshot(root,publish=False)
    ledger=Path(root)/'data/content_ledgers'/business_id/'content_ledger_v1.json'
    snapshot={'business_sha256':file_sha(business['path']),'speaker_sha256':file_sha(speaker['path']),
        'catalog':catalog,'configuration':payload,'style_id':style_id,
        'ledger_sha256':file_sha(ledger) if io_path(ledger).is_file() else None}
    return {'schema_version':'mix-style-preflight-v1.0','style_id':style_id,'actual_target':1,
        'can_confirm':(entry.get('recommendation') or {}).get('can_continue') is True,
        'source_configuration_sha256':digest(snapshot),'no_mutation':True}

def identity(style_id,catalog_ref):
    catalog=check(pinned(catalog_ref),'C01')
    rule=next((r for r in catalog['styles'] if r['style_id']==style_id),None)
    if rule is None: raise CreativeStyleError('CREATIVE_STYLE_NOT_ENABLED','Style is outside pinned Catalog')
    return {'style_id':style_id,'style_version':rule['style_version'],'catalog_ref':catalog_ref,'definition_sha256':digest(rule)}

def request_rule(request):
    value=request['creative_style'];catalog=check(pinned(value['catalog_ref']),'C01')
    return next(r for r in catalog['styles'] if r['style_id']==value['style_id'])

def request_style(request):
    value=request.get('creative_style')
    if value is None and request.get('schema_version')!=STYLE_REQUEST:
        return None  # Historical generator accepts unversioned input; admission remains strict.
    if request.get('schema_version') not in {STYLE_REQUEST,'generation-request-v1.2'} or not isinstance(value,dict):
        raise CreativeStyleError('CREATIVE_STYLE_REQUEST_INVALID','Style requires exact versioned Request')
    if value.get('style_id') not in {'persona','story','conversion'} or value.get('style_version')!='1':
        raise CreativeStyleError('CREATIVE_STYLE_NOT_ENABLED','This Native reader has no enabled handler for the Style version')
    if value!=identity(value.get('style_id'),value.get('catalog_ref')):
        raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Style differs from pinned Catalog')
    rule=request_rule(request)
    if request.get('target_profile',request.get('profile'))!='mix' or type(request.get('quantity')) is not int or request['quantity'] not in rule['allowed_quantities']:
        raise CreativeStyleError('CREATIVE_STYLE_QUANTITY_UNSUPPORTED','This scope permits one Mix video only')
    if request.get('cta_intent')!=cta_intent_for_rule(rule):
        raise CreativeStyleError('CREATIVE_STYLE_CTA_SCOPE_INVALID','CTA differs from pinned Style policy')
    intent=check(pinned(request.get('style_intent_ref')),'C02');confirmed=check(pinned(intent['batch_intent_ref']),'C03')
    if request.get('batch_admission_ref'):
        from native_batch_v1 import validate_admission
        admitted=validate_admission(request['batch_admission_ref'],request=request)
        if intent['ordered_slots']!=admitted['ordered_slots']:
            raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Native Style Slots differ from original batch admission')
    if (intent['creative_style']!=value or intent['native_request_id']!=request.get('request_id')
        or intent['business_id']!=request.get('persona_id') or intent['target_quantity']!=request['quantity']
        or intent['business_ref']['id']!=request.get('persona_id')
        or confirmed['business_id']!=request.get('persona_id') or confirmed['actual_target']!=request['quantity']
        or intent['actor_intent']!=confirmed['actor_intent']
        or len(confirmed['slots'])!=request['quantity']
        or intent['ordered_slots']!=[s['slot_id'] for s in confirmed['slots']]
        or any(s['creative_style']!=value or s['production_profile']!='mix' or s['source_kind']!='novel_content'
               or s['business_type_id']!=value['style_id'] for s in confirmed['slots'])):
        raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Native Request and C02/C03 differ')
    for name,key in [('business_ref','business_persona_ref'),('speaker_ref','speaker_persona_ref')]:
        original=(request.get('lineage') or {}).get(key) or {}
        source=intent[name]
        if source['path']!=original.get('path') or source['sha256']!=original.get('file_sha256'):
            raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Style intent differs from Native fact lineage')
    return value

def request_schema_supported(request):
    if request.get('schema_version') not in {LEGACY_REQUEST,STYLE_REQUEST,'generation-request-v1.2'}: return False
    try:
        if request.get('schema_version')=='generation-request-v1.2':
            from native_batch_v1 import request_supported
            if not request_supported(request):return False
        elif request.get('batch_admission_ref') is not None:return False
        request_style(request);return True
    except (RuntimeError,KeyError,TypeError,ValueError,OSError,StopIteration): return False

def normalize_configuration(value,style_id):
    if value is not None and not isinstance(value,dict):
        raise CreativeStyleError('CREATIVE_STYLE_CONFIGURATION_INVALID','Configuration must be an object')
    value=copy.deepcopy(value) if value is not None else {'mode':'free','revision':0,
        'quantities':{k:int(k==style_id) for k in ('novel','repurpose','persona','story','conversion')}}
    quantities=value.get('quantities') or {}
    if not isinstance(quantities,dict) or set(quantities)!={'novel','repurpose','persona','story','conversion'} or any(type(v) is not int or v<0 for v in quantities.values()):
        raise CreativeStyleError('CREATIVE_STYLE_CONFIGURATION_INVALID','Each type needs an explicit non-negative integer')
    total=sum(quantities.values())
    if quantities.get(style_id)!=total or total not in definition(style_id,executable=True)['allowed_quantities']:
        raise CreativeStyleError('CREATIVE_STYLE_SINGLE_ONLY','Only an explicitly qualified single Style quantity can be admitted')
    mode,stage=value.get('mode'),value.get('stage')
    if not isinstance(mode,str) or mode not in {'stage','free'} or mode=='stage' and (not isinstance(stage,str) or stage not in {'launch','trust','steady'}):
        raise CreativeStyleError('CREATIVE_STYLE_CONFIGURATION_INVALID','Unknown stage or mode')
    if mode=='stage' and stage in {'launch','trust'} and (type(value.get('combinedTarget')) is not int or quantities['persona']+quantities['story']!=value['combinedTarget']):
        raise CreativeStyleError('CREATIVE_STYLE_CONFIGURATION_INVALID','Persona/story allocation differs from actual target')
    cycles=value.get('cycles') if mode=='stage' and stage=='steady' else None
    if mode=='stage' and stage=='steady' and (type(cycles) is not int or cycles<1 or value.get('cyclesConfirmed') is not True):
        raise CreativeStyleError('CREATIVE_STYLE_CONFIGURATION_INVALID','Explicit finite cycle confirmation required')
    revision=value.get('revision',0)
    if type(revision) is not int or revision<0:
        raise CreativeStyleError('CREATIVE_STYLE_CONFIGURATION_INVALID','Invalid draft revision')
    return {'mode':mode,'operating_stage':stage if mode=='stage' else None,'explicit_cycles':cycles,
        'quantities':quantities,'draft_revision':revision+1}

def known(persona,field):
    fact=(persona.get('facts') or {}).get(field) or {}
    return isinstance(fact,dict) and fact.get('state')=='known' and fact.get('value') not in (None,'',[],{})

def values(persona,fields):
    result=[]
    for field in fields:
        if known(persona,field):
            raw=persona['facts'][field]['value'];result.extend((field,str(v)) for v in (raw if isinstance(raw,list) else [raw]))
    return result

def event_values(business,rule):
    return [(field,value) for field,value in values(business,rule['required_fact_roles'])
            if re.search(r'有一次|那次|当时|曾经|某次',value)]

def cta_intent_for_rule(rule):
    policy=rule['cta_policy']
    if rule['style_id']=='conversion':
        if not policy.startswith(CTA_PREFIX) or not policy[len(CTA_PREFIX):].strip():
            raise CreativeStyleError('CREATIVE_STYLE_CTA_SCOPE_INVALID','Unknown or empty versioned inquiry policy')
        return 'service_inquiry'
    if policy!='none':raise CreativeStyleError('CREATIVE_STYLE_CTA_SCOPE_INVALID','Unexpected CTA policy for Style version')
    return 'none'

def validate_style_facts(name,rule,business,speaker):
    from customer_constraints_v1 import truth_projection
    business=truth_projection(business)
    if not speaker or speaker.get('persona_scope')!='speaker' or not speaker.get('lifecycle',{}).get('approved'):
        raise CreativeStyleError('CREATIVE_STYLE_SPEAKER_REQUIRED','Approved applicable Speaker required')
    if name=='persona' and not known(speaker,'speaker_role_facts'):
        raise CreativeStyleError('CREATIVE_STYLE_FIRST_PERSON_UNSUPPORTED','Sourced personal practice required; topic permission alone is insufficient')
    if name=='story' and not event_values(business,rule):
        raise CreativeStyleError('CREATIVE_STYLE_EVENT_REQUIRED','Known actual event required')
    if name=='conversion' and (not values(business,VALUE_FIELDS) or not values(business,NEED_FIELDS)):
        raise CreativeStyleError('CREATIVE_STYLE_VALUE_REQUIRED','Approved service value and applicable need required')

def prepare_intents(root,request_id,style_id,business,speaker,context,operation_id,configuration=None,*,ordered_slots=None):
    from delivery_receipt_recovery_v1 import identity as principal_identity
    principal_identity(context);rule=definition(style_id,executable=True)
    validate_style_facts(style_id,rule,read(business['path']),read(speaker['path']))
    root=Path(root).resolve();catalog_ref=catalog_for_admission(root);style=identity(style_id,catalog_ref)
    rule=next(r for r in pinned(catalog_ref)['styles'] if r['style_id']==style_id)
    payload=normalize_configuration(configuration,style_id)
    payload_sha=digest({'business_id':business['persona_id'],'speaker_id':speaker['persona_id'],'style':style,'configuration':payload})
    directory=root/'data/creation_batch_intents'/request_id
    b_ref=artifact(business['path'],'native-business',business['persona_id'],business['revision'])
    s_ref=artifact(speaker['path'],'native-speaker',speaker['persona_id'],speaker['revision'])
    intent_path=directory/'style_intent.json'
    if io_path(intent_path).is_file():
        existing=check(read(intent_path),'C02');old_permission=pinned(existing['actor_intent']['permission_snapshot'])
        if (existing['actor_intent']['payload_sha256']!=payload_sha or existing['business_ref']!=b_ref or existing['speaker_ref']!=s_ref
            or ordered_slots is not None and existing['ordered_slots']!=list(ordered_slots)
            or old_permission['actor']!=context['actor'] or old_permission['authorization']['user_state_sha256']!=context['authorization']['user_state_sha256']):
            raise CreativeStyleError('CREATIVE_STYLE_INTENT_CONFLICT','Original intent or principal differs')
        return style,artifact(intent_path,'native-mix-request',request_id,INTENT),payload
    permission=directory/'permission_snapshot.json'
    if io_path(permission).is_file():
        original=read(permission)
        from delivery_receipt_recovery_v1 import CONTEXT
        from profile_compatibility_contract_v1_1 import validate
        try:
            validate(original,CONTEXT)
            if original['actor']!=context['actor'] or any(original['authorization'][key]!=context['authorization'][key]
                    for key in ['user_state_sha256','database_path']):
                raise ValueError('Stable authorization changed')
        except (RuntimeError,ValueError,KeyError,TypeError) as exc:
            raise CreativeStyleError('CREATIVE_STYLE_INTENT_CONFLICT','Original permission snapshot differs from current stable principal') from exc
    else:
        write_once(permission,context)
    actor={'actor_id':str(context['actor']['user_id']),'permission_snapshot':artifact(permission,'console-authorization',context['actor']['user_id'],'1'),
        'operation_id':operation_id,'payload_sha256':payload_sha}
    sources=[*rule['pattern_scope_refs'],*rule['compatibility_scope_refs'],rule['release_ref']]
    quantity=payload['quantities'][style_id]
    slots=list(ordered_slots) if ordered_slots is not None else [request_id+f'-S{i:03d}' for i in range(1,quantity+1)]
    if len(slots)!=quantity or len(set(slots))!=quantity:
        raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Ordered Slot scope differs from confirmed quantity')
    batch=check({'schema_version':'creation-batch-intent-v1.0','batch_id':request_id,'business_id':business['persona_id'],
        'draft_revision':payload['draft_revision'],'mode':payload['mode'],'operating_stage':payload['operating_stage'],'explicit_cycles':payload['explicit_cycles'],
        'slots':[{'slot_id':slot,'production_profile':'mix','creative_style':style,'source_kind':'novel_content','source_refs':sources,'business_type_id':style_id} for slot in slots],
        'actual_target':quantity,'context_refs':[b_ref,s_ref,*sources],'explicit_confirmation':True,'actor_intent':actor},'C03')
    batch_path=directory/'confirmed_intent.json';write_once(batch_path,batch)
    intent=check({'schema_version':INTENT,'business_id':business['persona_id'],
        'batch_intent_ref':artifact(batch_path,'creation-configuration',request_id,batch['schema_version']),
        'native_request_id':request_id,'creative_style':style,'business_ref':b_ref,'speaker_ref':s_ref,'ordered_slots':slots,
        'target_quantity':quantity,'source_refs':sources,'actor_intent':actor},'C02')
    write_once(intent_path,intent)
    return style,artifact(intent_path,'native-mix-request',request_id,INTENT),payload

def validate_facts(request,business,speaker):
    style=request_style(request)
    if style: validate_style_facts(style['style_id'],request_rule(request),business,speaker)

def model_policy(request):
    style=request_style(request)
    if not style:return None
    rule=request_rule(request)
    return {'style_id':style['style_id'],'style_version':style['style_version'],'structure':rule['structure'],
        'generation_rule':rule['definition'],'forbidden_claims':rule['forbidden_claims'],'cta_policy':rule['cta_policy'],
        'permitted_cta':rule['cta_policy'][len(CTA_PREFIX):] if style['style_id']=='conversion' else None}

def persona_anchor(text):
    return re.sub(r'本人|我们|我|咱们|[，。！？、\s]','',str(text))

def validate_concept(request,concept,speaker,business=None):
    name=(request_style(request) or {}).get('style_id')
    if not name:return
    if name=='story':
        refs=concept.get('primary_fact_refs') or []
        if not any(field in refs and value in str(concept.get('central_claim') or '') for field,value in event_values(business or {},request_rule(request))):
            raise CreativeStyleError('CREATIVE_STYLE_EVENT_REQUIRED','Selected Story Concept must center its exact approved event')
        return
    if name=='conversion':
        primary=concept.get('primary_fact_refs') or []
        refs=primary+(concept.get('supporting_fact_refs') or [])
        if (not any(field in primary and value in str(concept.get('central_claim') or '') for field,value in values(business or {},VALUE_FIELDS))
                or not any(field in refs for field,_ in values(business or {},NEED_FIELDS))):
            raise CreativeStyleError('CREATIVE_STYLE_VALUE_REQUIRED','Conversion Concept must bind an approved value and applicable need')
        return
    claim=persona_anchor(concept.get('central_claim'));refs=concept.get('speaker_fact_refs') or []
    anchors=[persona_anchor(v) for field,v in values(speaker or {},['speaker_role_facts']) if field in refs]
    if not any(len(a)>=6 and a in claim for a in anchors):
        raise CreativeStyleError('CREATIVE_STYLE_PERSONA_CENTER_REQUIRED','Selected Concept must center sourced personal practice, not a generic process')

def validate_item(item,request,business,speaker):
    style=request_style(request)
    if not style:return
    validate_facts(request,business,speaker)
    if style['style_id']=='persona':
        validate_concept(request,{'central_claim':item.get('central_claim'),'speaker_fact_refs':item.get('speaker_fact_refs_used')},speaker)
        text=str(item.get('narration') or '');anchors=[persona_anchor(v) for _,v in values(speaker,['speaker_role_facts'])]
        if not re.search(r'我|咱们',text) or not any(a in persona_anchor(text) for a in anchors):
            raise CreativeStyleError('CREATIVE_STYLE_FIRST_PERSON_UNSUPPORTED','Persona must explain the referenced personal practice')
    elif style['style_id']=='story':
        from customer_constraints_v1 import truth_projection
        business=truth_projection(business)
        refs=item.get('persona_fact_refs_used') or []
        text=str(item.get('narration') or '')
        events=[value for field,value in event_values(business,request_rule(request)) if field in refs
                and value in text and value in str(item.get('central_claim') or '')]
        if not events:raise CreativeStyleError('CREATIVE_STYLE_EVENT_REQUIRED','Story must preserve the exact approved event and its fact reference')
        if re.search(r'我|咱们',text) and not any(event in value for event in events for _,value in values(speaker,('speaker_role_facts','founder_or_operator_story','brand_story'))):
            raise CreativeStyleError('CREATIVE_STYLE_FIRST_PERSON_UNSUPPORTED','Business event alone does not authorize a personal experience claim')
    elif style['style_id']=='conversion':
        from customer_constraints_v1 import truth_projection
        business=truth_projection(business);rule=request_rule(request)
        allowed=rule['cta_policy'][len(CTA_PREFIX):];cta=item.get('cta') or {}
        refs=item.get('persona_fact_refs_used') or [];text=str(item.get('narration') or '')
        validate_concept(request,{'central_claim':item.get('central_claim'),'primary_fact_refs':refs,'supporting_fact_refs':refs},speaker,business)
        if (cta.get('present') is not True or cta.get('text')!=allowed or allowed not in text
                or not any(field in refs and value in text for field,value in values(business,VALUE_FIELDS))
                or not any(field in refs and value in text for field,value in values(business,NEED_FIELDS))):
            raise CreativeStyleError('CREATIVE_STYLE_CTA_SCOPE_INVALID','Conversion must retain approved value, need, conditions and the versioned neutral inquiry')

def bind_batch(batch,request,business,speaker,selected_concepts=None):
    style=request_style(request)
    if not style:return
    slots=pinned(request['style_intent_ref'])['ordered_slots']
    if len(batch.get('contents') or [])>len(slots):raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Output exceeds confirmed Slots')
    selected=[c['concept_id'] for c in selected_concepts] if selected_concepts is not None else []
    if len(slots)>1 and (not selected or len(selected)!=len(set(selected)) or len(selected)>len(slots)):
        raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Multi-Slot output requires its exact final Concept order')
    mapping=dict(zip(selected,slots))
    for item in batch.get('contents') or []:
        slot=mapping.get(item.get('concept_ref')) if selected else slots[0]
        if slot is None:raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Content has no original Concept/Slot mapping')
        validate_item(item,request,business,speaker);item.update(creative_style=copy.deepcopy(style),logical_slot_id=slot)
    batch.update(creative_style=copy.deepcopy(style),style_intent_ref=request['style_intent_ref'])

def validate_batch(batch,contents=None):
    ref=(batch.get('lineage') or {}).get('request') or {};path=Path(str(ref.get('path') or ''))
    labelled=batch.get('creative_style') is not None or any(i.get('creative_style') is not None for i in batch.get('contents') or [])
    if not io_path(path).is_file():
        if labelled:raise CreativeStyleError('CREATIVE_STYLE_SOURCE_CHANGED','Style Request is missing')
        return
    request=read(path);style=request_style(request)
    if not style:
        if labelled:raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Historical content cannot acquire Style labels')
        return
    if file_sha(path)!=ref.get('sha256') or batch.get('creative_style')!=style or batch.get('style_intent_ref')!=request['style_intent_ref']:
        raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Batch differs from exact Style Request')
    sources={key:pinned((batch.get('lineage') or {})[key]) for key in ['persona','speaker_persona']}
    slots=pinned(request['style_intent_ref'])['ordered_slots']
    selected=[]
    if len(slots)>1:
        plan=pinned((batch.get('lineage') or {})['final_content_plan_v1_1_1'])
        selected=[c['concept_id'] for c in plan['selected_concepts']]
    mapping=dict(zip(selected,slots));seen=set()
    for item in ((batch.get('contents') or []) if contents is None else contents):
        slot=item.get('logical_slot_id')
        if (item.get('creative_style')!=style or slot not in slots or slot in seen
                or selected and mapping.get(item.get('concept_ref'))!=slot):
            raise CreativeStyleError('CREATIVE_STYLE_IDENTITY_MISMATCH','Content lost original Style/Slot identity')
        seen.add(slot)
        validate_item(item,request,sources['persona'],sources['speaker_persona'])
