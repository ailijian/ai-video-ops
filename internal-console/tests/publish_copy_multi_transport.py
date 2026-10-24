"""Two distinct fictional processes supplied only at the external model boundary."""
import copy,json,sys,socket
from pathlib import Path
root=Path(sys.argv[2]).resolve();sys.path.insert(0,str(root/'scripts'))
project=Path(__file__).resolve().parents[2];sys.path.insert(0,str(project/'ops-pipeline/tests'))
from compatibility_creation_synthetic import response,plan_transport
CLAIMS=['先核对忌口，再按单配菜，制作后标记餐盒',
        '顾客到店后先核对订单标识，再核对餐盒标记，最后交付密封餐盒']
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('No external network in synthetic transport'))
def plans(prompt):
    base=plan_transport(prompt)['payload']['candidates'][0];items=[]
    for i,claim in enumerate(CLAIMS):
        item=copy.deepcopy(base);item.update(concept_id=f'CONCEPT_{i+1:03d}',central_claim=claim,
            central_claim_key=['dietary_order_preparation','pickup_order_identity_handover'][i],
            primary_topic=['下单时如何核对忌口','到店后如何核对订单交付'][i],
            audience_need=['有忌口需求的顾客想知道下单前应当说明什么','到店自取顾客想知道如何核对订单标识并领取餐盒'][i],
            content_job=['解释核对忌口到配菜标记的制作流程','解释到店核对标识与交付餐盒的领取流程'][i],
            exclusive_anchor={'kind':'process','value':claim,'fact_refs':['process_facts']},
            why_publish=['让顾客了解忌口信息如何进入配菜与餐盒标记的流程。','让顾客了解到店后订单标识核对与餐盒交付的关系。'][i])
        items.append(item)
    return response({'candidates':items})
def scripts(prompt):
    context=json.loads(prompt.split('SAFE GENERATION CONTEXT:\n',1)[1]);items=[]
    for slot in context['slots']:
        selected=slot['selected_content_plan'];claim=selected['central_claim']
        item={'slot_id':slot['slot_id'],'concept_ref':selected['concept_ref'],
            'central_claim':claim,'central_claim_key':selected['central_claim_key'],
            'title':selected['primary_topic'],'narration':
                ('下单时需要说明忌口，门店的处理流程是：'+claim+'。这里核对的是忌口要求与配菜、餐盒标记的关系。小周亲自负责核对订单，可以说明自己负责的核对步骤。'
                 if claim==CLAIMS[0] else '顾客到店自取时，领取流程是：'+claim+'。这里说明订单标识、餐盒标记与交付之间的关系。小周亲自负责核对订单，可以说明到店后核对这一步。'),
            'persona_fact_refs_used':['process_facts','customer_pains','customer_use_cases'],'speaker_fact_refs_used':['speaker_role_facts'],
            'claim_candidates':[{'text':claim,'persona_fact_refs':['process_facts'],'speaker_fact_refs':[]}],
            'customer_feedback_provenance':[],'cta':{'present':False,'text':None}}
        items.append(item)
    return response({'items':items})
try:
    if sys.argv[1]=='plan-news-history':
        from resolve_generation_content_plan_v1 import resolve_generation_content_plan
        result=resolve_generation_content_plan(pipeline_root=root,request_id=sys.argv[3],transport=plans,model='synthetic-no-network')
    else:
        from resolve_generation_batch_v1 import resolve_generation_batch
        result=resolve_generation_batch(pipeline_root=root,request_id=sys.argv[3],transport=scripts,model='synthetic-no-network')
    print(json.dumps(result,ensure_ascii=False))
except RuntimeError as exc:
    print(json.dumps({'ok':False,'code':getattr(exc,'code','SYNTHETIC_TEST_FAILURE'),'message':str(exc)},ensure_ascii=False));raise SystemExit(2)
