"""Schema/rule evidence only: fake refs below are NOT Native qualification."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import creative_style_v1 as style
from human_review_operations_v1 import write_once


def fact(value):return {'state':'known','value':value}


def unit_request(tmp_path,name='persona',quantity=1):
    business={'facts':{'founder_or_operator_story':fact(['负责人小周亲自负责核对订单','有一次顾客说明忌口，店主核对后按单制作。']),
        'process_facts':fact(['先核对忌口，再制作']),'pricing_facts':fact(['午餐套餐29元，仅限到店自取，不含配送']),
        'primary_products_or_services':fact(['供应按单制作的餐食']),'customer_pains':fact(['希望提前说明忌口'])}}
    speaker={'persona_scope':'speaker','lifecycle':{'approved':True},'facts':{'speaker_role_facts':fact(['本人亲自负责核对订单'])}}
    def ref(name,value):
        p=tmp_path/name;write_once(p,value)
        return style.artifact(p,'schema-unit-NOT-native',name,'1')
    b=ref('business.json',business);b['id']='unit-business'
    s=ref('speaker.json',speaker);proof=ref('source.json',{'kind':'schema-unit-only'})
    rule={key:copy.deepcopy(style.definition(name)[key]) for key in style.STYLE_FIELDS}
    rule.update(approved_product_rule_ref=proof,pattern_scope_refs=[proof],compatibility_scope_refs=[proof],release_ref=proof)
    catalog=style.check({'schema_version':'creative-style-catalog-v1.0','catalog_id':'schema-unit-only','catalog_version':'1','styles':[rule]},'C01')
    catalog_ref=ref('catalog.json',catalog);identity=style.identity(name,catalog_ref)
    actor={'actor_id':'unit','permission_snapshot':proof,'operation_id':'unit-op','payload_sha256':'0'*64}
    slot={'slot_id':'unit-S001','production_profile':'mix','creative_style':identity,'source_kind':'novel_content','source_refs':[proof],'business_type_id':name}
    c3=style.check({'schema_version':'creation-batch-intent-v1.0','batch_id':'unit','business_id':'unit-business','draft_revision':1,
        'mode':'free','operating_stage':None,'explicit_cycles':None,'slots':[{**slot,'slot_id':f'unit-S{i:03d}'} for i in range(1,quantity+1)],'actual_target':quantity,'context_refs':[b,s,proof],
        'explicit_confirmation':True,'actor_intent':actor},'C03')
    c3ref=ref('confirmed.json',c3)
    c2=style.check({'schema_version':style.INTENT,'business_id':'unit-business','batch_intent_ref':c3ref,'native_request_id':'unit',
        'creative_style':identity,'business_ref':b,'speaker_ref':s,'ordered_slots':[f'unit-S{i:03d}' for i in range(1,quantity+1)],'target_quantity':quantity,'source_refs':[proof],'actor_intent':actor},'C02')
    c2ref=ref('intent.json',c2)
    request={'schema_version':style.STYLE_REQUEST,'request_id':'unit','persona_id':'unit-business','profile':'mix','target_profile':'mix',
        'quantity':quantity,'creative_style':identity,'style_intent_ref':c2ref,'cta_intent':style.cta_intent_for_rule(rule),
        'lineage':{'business_persona_ref':{'path':b['path'],'file_sha256':b['sha256']},
                   'speaker_persona_ref':{'path':s['path'],'file_sha256':s['sha256']}}}
    return request,business,speaker


def test_approved_c01_c02_c03_shapes_and_strict_request(tmp_path):
    r,_,_=unit_request(tmp_path);assert style.request_schema_supported(r)
    catalog=style.pinned(r['creative_style']['catalog_ref'])
    assert isinstance(catalog['catalog_version'],str) and isinstance(catalog['styles'],list)
    with pytest.raises(style.CreativeStyleError):style.check({**catalog,'catalog_version':1},'C01')
    for mutation in [dict(schema_version=style.LEGACY_REQUEST),dict(quantity=20),dict(cta_intent='other'),
        dict(creative_style={**r['creative_style'],'definition_sha256':'0'*64})]:
        assert not style.request_schema_supported({**r,**mutation})


def test_historical_generator_inputs_remain_separate_from_strict_admission():
    legacy={'request_id':'old-unversioned','profile':'mix','quantity':10,'cta_intent':'optional'}
    assert style.request_style(legacy) is None and style.model_policy(legacy) is None
    assert not style.request_schema_supported(legacy)
    assert style.request_schema_supported({**legacy,'schema_version':style.LEGACY_REQUEST})


def test_enabled_styles_remain_catalog_versioned_and_unknown_styles_fail():
    for name in ['story','conversion']:
        assert style.definition(name,executable=True)['style_id']==name
    with pytest.raises(style.CreativeStyleError) as e:style.definition('unregistered',executable=True)
    assert e.value.code=='CREATIVE_STYLE_UNKNOWN'


def test_persona_requires_actual_sourced_concept_not_first_person_suffix(tmp_path):
    r,b,s=unit_request(tmp_path)
    item={'central_claim':'我亲自负责核对订单','narration':'我亲自负责核对订单。这里解释核对忌口的具体操作。',
        'speaker_fact_refs_used':['speaker_role_facts']}
    style.validate_item(item,r,b,s)
    with pytest.raises(style.CreativeStyleError) as e:style.validate_item({**item,'central_claim':'先核对忌口，再按单制作'},r,b,s)
    assert e.value.code=='CREATIVE_STYLE_PERSONA_CENTER_REQUIRED'
    with pytest.raises(style.CreativeStyleError):style.validate_item({**item,'narration':'门店核对忌口，再按单制作。'},r,b,s)
    s['facts']={'first_person_allowed_topics':fact(['订单核对'])}
    with pytest.raises(style.CreativeStyleError):style.validate_facts(r,b,s)


@pytest.mark.parametrize('name',['story','conversion'])
def test_distinct_story_and_conversion_rules_require_real_sources_and_output(tmp_path,name):
    r,b,s=unit_request(tmp_path,name);assert style.request_schema_supported(r)
    if name=='story':
        event=b['facts']['founder_or_operator_story']['value'][1]
        item={'central_claim':event,'narration':event,'persona_fact_refs_used':['founder_or_operator_story']}
        style.validate_item(item,r,b,s)
        with pytest.raises(style.CreativeStyleError):style.validate_item({**item,'narration':'普通制作流程'},r,b,s)
        with pytest.raises(style.CreativeStyleError):style.validate_item({**item,'narration':'我记得，'+event},r,b,s)
        b['facts']['founder_or_operator_story']=fact(['本人负责核对订单'])
        with pytest.raises(style.CreativeStyleError):style.validate_facts(r,b,s)
    else:
        cta=style.model_policy(r)['permitted_cta'];value=b['facts']['pricing_facts']['value'][0]
        item={'central_claim':value,'narration':'希望提前说明忌口。'+value+cta,
              'persona_fact_refs_used':['pricing_facts','customer_pains'],'cta':{'present':True,'text':cta}}
        style.validate_item(item,r,b,s)
        with pytest.raises(style.CreativeStyleError):style.validate_item({**item,'cta':{'present':True,'text':'未获准的购买号召'}},r,b,s)
        with pytest.raises(style.CreativeStyleError):style.validate_item({**item,'narration':value+cta},r,b,s)
        b['facts']['customer_pains']={'state':'unknown','value':[]}
        with pytest.raises(style.CreativeStyleError):style.validate_facts(r,b,s)


def test_historical_catalog_lookup_does_not_read_current_rules(tmp_path,monkeypatch):
    r,b,s=unit_request(tmp_path);original=style.model_policy(r)
    changed=tmp_path/'new-rules.json';write_once(changed,{'enabled_styles':[],'styles':{},'rule_set_version':'2'})
    monkeypatch.setattr(style,'RULES',changed)
    assert style.request_schema_supported(r) and style.model_policy(r)==original
    style.validate_facts(r,b,s)


def test_stable_slot_exists_before_concept_and_survives_binding(tmp_path):
    r,b,s=unit_request(tmp_path)
    item={'content_id':'original-C001','concept_ref':'CONCEPT_001','central_claim':'我亲自负责核对订单',
        'narration':'我亲自负责核对订单。','speaker_fact_refs_used':['speaker_role_facts']}
    batch={'contents':[item]};style.bind_batch(batch,r,b,s)
    assert item['logical_slot_id']=='unit-S001' and item['creative_style']==r['creative_style']


def test_zero_multiple_or_unconfirmed_configuration_cannot_execute():
    q={key:0 for key in ['novel','repurpose','persona','story','conversion']}
    for value in [{'mode':'free','quantities':q},{'mode':'free','quantities':{**q,'persona':3}},
        {'mode':'stage','stage':'steady','cycles':1,'cyclesConfirmed':False,'quantities':{**q,'persona':1}}]:
        with pytest.raises(style.CreativeStyleError):style.normalize_configuration(value,'persona')
    assert style.normalize_configuration(None,'persona')['quantities']['persona']==1


def test_multi_style_slots_follow_final_concepts_not_response_order(tmp_path):
    r,b,s=unit_request(tmp_path,quantity=2)
    item={'content_id':'original-C002','concept_ref':'CONCEPT_002','central_claim':'我亲自负责核对订单',
          'narration':'我亲自负责核对订单。','speaker_fact_refs_used':['speaker_role_facts']}
    batch={'contents':[item]}
    style.bind_batch(batch,r,b,s,[{'concept_id':'CONCEPT_001'},{'concept_id':'CONCEPT_002'}])
    assert item['logical_slot_id']=='unit-S002'


@pytest.mark.parametrize('quantities',[1,True,'persona',['novel','repurpose','persona','story','conversion'],None])
def test_malformed_nested_configuration_has_typed_rejection(quantities):
    with pytest.raises(style.CreativeStyleError) as e:style.normalize_configuration({'mode':'free','quantities':quantities},'persona')
    assert e.value.code=='CREATIVE_STYLE_CONFIGURATION_INVALID'


def test_cross_business_intent_cannot_be_reinterpreted(tmp_path):
    r,_,_=unit_request(tmp_path)
    assert not style.request_schema_supported({**r,'persona_id':'another-business'})


def test_historical_generator_functions_refuse_style_before_dispatch(tmp_path):
    import generate_mix_scripts_v1 as native
    r,_,_=unit_request(tmp_path)
    for invoke in [lambda:native.generate_batch({'request':r}),
                   lambda:native.generate_selective_revision_batch({'request':r},tmp_path/'missing-batch',tmp_path/'missing-review')]:
        with pytest.raises(style.CreativeStyleError) as e:invoke()
        assert e.value.code=='CREATIVE_STYLE_ENTRY_UNSUPPORTED'
