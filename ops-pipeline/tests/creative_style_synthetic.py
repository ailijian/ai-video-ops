"""Only the external provider transport is synthetic; every Native Gate executes."""
import json
import copy
import hashlib
import socket
import sys
from pathlib import Path

from compatibility_creation_synthetic import plan_transport, script_transport, response


def plan(prompt):
    context = json.loads(prompt.split('SAFE CONTENT PLANNING CONTEXT:\n', 1)[1])
    calls=Path(sys.argv[2])/'data/metrics/generation_requests'/sys.argv[3]/'style_synthetic_planning_calls.jsonl'
    calls.parent.mkdir(parents=True,exist_ok=True)
    with calls.open('a',encoding='utf-8') as handle:handle.write(json.dumps({'provider':'synthetic','operation':'content_plan',
        'pending_count':len(context.get('pending_content_intents',[])),
        'communicated_count':len(context['historical_content_memory'])})+'\n')
    name=context['request']['creative_style_policy']['style_id']
    result = plan_transport(prompt)
    candidate = result['payload']['candidates'][0]
    if name=='persona':candidate.update(primary_topic='本人负责的订单核对', content_job='解释本人核对订单的实际职责与具体依据',
        primary_fact_refs=['process_facts'], supporting_fact_refs=['customer_pains'],
        central_claim='我亲自负责核对订单：先核对忌口，再按单配菜，制作后标记餐盒', central_claim_key='speaker_personal_order_check_practice',
        exclusive_anchor={'kind':'process','value':'先核对忌口，再按单配菜，制作后标记餐盒','fact_refs':['process_facts']},
        why_publish='解释出镜人小周本人的订单核对职责及核对忌口的具体操作，职责范围不代表结果保证。')
    if name=='persona' and len(context.get('speaker_persona',{}).get('facts',{}).get('speaker_role_facts',[]))>1:
        held={v['central_claim'] for v in context.get('pending_content_intents',[])}
        result['payload']['candidates']=[]
        for index,value in enumerate(context['speaker_persona']['facts']['speaker_role_facts'],1):
            if value in held:continue
            item=copy.deepcopy(candidate)
            item.update(concept_id=f'CONCEPT_{index:03d}',central_claim=value,
                central_claim_key='personal_practice_'+hashlib.sha256(value.encode()).hexdigest()[:12],
                primary_fact_refs=['process_facts'],supporting_fact_refs=['founder_or_operator_story'],
                primary_topic=value[:18],content_job='解释我本人已提供的经营实践：'+value,
                audience_need='附近需要午餐的住户，希望了解店主这项明确的日常实践：'+value,
                exclusive_anchor={'kind':'process','value':value,'fact_refs':['process_facts']},
                why_publish='说明真实出镜人本人提供并确认的经营实践及其具体依据：'+value)
            result['payload']['candidates'].append(item)
    elif name=='story':
        held={v['central_claim'] for v in context.get('pending_content_intents', [])}
        events=[v for v in context['business_persona']['facts']['founder_or_operator_story'] if ('有一次' in v or '曾经' in v) and v not in held]
        if not events:
            result['payload']['candidates']=[]
            return response(result['payload'])
        event=events[0]
        candidate.update(primary_topic='一次忌口订单的处理经过',content_job='讲清一次实际订单的处理安排与经过',
            primary_fact_refs=['founder_or_operator_story'],supporting_fact_refs=['process_facts'],central_claim=event,
            central_claim_key='recorded_dietary_order_event',narrative_mode='有来源的事件经过',
            exclusive_anchor={'kind':'specific_event','value':event,'fact_refs':['founder_or_operator_story']},
            why_publish='通过客户已批准的具体事件解释该次订单从备注、核对到配菜与标记餐盒的安排。')
        if len(events)>1:
            candidates=[]
            for index,event in enumerate(events,1):
                item=copy.deepcopy(candidate)
                item.update(concept_id=f'CONCEPT_{index:03d}',central_claim=event,
                    central_claim_key='recorded_event_'+hashlib.sha256(event.encode()).hexdigest()[:12],
                    primary_topic=event[:18],content_job='解释这次真实事件中的具体安排与经过：'+event,
                    audience_need='附近需要午餐的住户，希望理解这次已记录事件：'+event,
                    exclusive_anchor={'kind':'specific_event','value':event,'fact_refs':['founder_or_operator_story']},
                    why_publish='帮助附近需要午餐的住户了解这次已记录的行为、经过和来源支持的结果：'+event)
                candidates.append(item)
            result['payload']['candidates']=candidates
    elif name=='conversion':
        price=context['business_persona']['facts']['pricing_facts'][0]
        candidate.update(primary_topic='套餐价格与自取条件',content_job='说明已批准的价格、服务范围和咨询前的选择条件',
            primary_fact_refs=['pricing_facts'],supporting_fact_refs=['included_service_facts','customer_pains','customer_use_cases'],
            central_claim=price,central_claim_key='approved_meal_price_collection_conditions',narrative_mode='服务价值、适用条件与中性咨询',
            exclusive_anchor={'kind':'price','value':price,'fact_refs':['pricing_facts']},
            why_publish='为有午间自取需求的顾客提供价格、包含项目和配送边界，再引导咨询适用条件。')
        if len(context['business_persona']['facts']['pricing_facts'])>1:
            result['payload']['candidates']=[]
            held=[v['central_claim'] for v in context.get('pending_content_intents',[])]
            for index,value in enumerate(context['business_persona']['facts']['pricing_facts'],1):
                if any(value in claim for claim in held):continue
                item=copy.deepcopy(candidate)
                item.update(concept_id=f'CONCEPT_{index:03d}',central_claim=value,
                    central_claim_key='approved_price_'+hashlib.sha256(value.encode()).hexdigest()[:12],
                    primary_topic=value[:18],content_job='说明这项已批准餐食价值的价格与适用条件：'+value,
                    audience_need='附近需要午餐的住户，希望核对这项已批准餐食的购买条件：'+value,
                    why_publish='帮助附近需要午餐的住户理解这项已批准餐食的价格、适用场景与点单边界：'+value,
                    exclusive_anchor={'kind':'price','value':value,'fact_refs':['pricing_facts']})
                result['payload']['candidates'].append(item)
    elif name!='persona':raise ValueError('Unsupported synthetic Style')
    return response(result['payload'])


def generate(prompt):
    calls=Path(sys.argv[2])/'data/metrics/generation_requests'/sys.argv[3]/'style_synthetic_provider_calls.jsonl'
    calls.parent.mkdir(parents=True,exist_ok=True)
    with calls.open('a',encoding='utf-8') as handle:handle.write(json.dumps({'provider':'synthetic','operation':sys.argv[1]})+'\n')
    context = json.loads(prompt.split('SAFE GENERATION CONTEXT:\n', 1)[1])
    name=context['request']['creative_style_policy']['style_id']
    result = script_transport(prompt)
    for item in result['payload']['items']:
        if name=='persona':
            item.update(title='我负责的订单核对环节', narration='我亲自负责核对订单。我想把自己负责的环节讲清楚：先核对忌口，再按单配菜，制作后标记餐盒。这里介绍我本人的核对职责和门店已经明确的制作流程。',
                persona_fact_refs_used=['process_facts'], speaker_fact_refs_used=['speaker_role_facts'])
            if len(context.get('speaker',{}).get('facts',{}).get('speaker_role_facts',[]))>1:
                value=item['central_claim']
                item.update(title=value[:18].rstrip('，。'),narration=value,
                    persona_fact_refs_used=['process_facts','founder_or_operator_story'])
        elif name=='story':
            item.update(title=item['central_claim'][:18].rstrip('，。'),narration=item['central_claim'],
                persona_fact_refs_used=['founder_or_operator_story'],speaker_fact_refs_used=[])
        elif name=='conversion':
            cta=context['request']['creative_style_policy']['permitted_cta']
            value=item['central_claim']
            item.update(title=value[:18].rstrip('，。'),narration=value+'。午间在附近自取，希望提前说明忌口。套餐含一份主食与两份蔬菜，门店提供密封餐盒。'+cta+'本条适用范围：'+value+'。',
                persona_fact_refs_used=['pricing_facts','included_service_facts','customer_pains','customer_use_cases'],speaker_fact_refs_used=[],
                cta={'present':True,'text':cta})
        item['claim_candidates']=[{'text':item['central_claim'],'persona_fact_refs':item['persona_fact_refs_used'],'speaker_fact_refs':item['speaker_fact_refs_used']}]
    return response(result['payload'])


def invalid_generate(prompt):
    result=generate(prompt)
    for item in result['payload']['items']:
        context=json.loads(prompt.split('SAFE GENERATION CONTEXT:\n',1)[1])
        name=context['request']['creative_style_policy']['style_id']
        if name=='persona':item['narration']='小周亲自负责核对订单。先核对忌口，再按单配菜，制作后标记餐盒。这里说明核对和制作的实际流程。'
        elif name=='story':item['narration']='先核对忌口，再按单配菜，制作后标记餐盒。'
        else:
            item['narration']=item['narration'].replace(item['cta']['text'],'');item['cta']={'present':False,'text':None}
    return response(result['payload'])


def partial_generate(prompt):
    result = generate(prompt)
    result['payload']['items'] = result['payload']['items'][1:]
    return response(result['payload'])


def invalid_response(prompt):
    generate(prompt)  # Count this external call; no Native validator is patched.
    from generate_mix_scripts_v1 import RemoteAttemptError
    raise RemoteAttemptError('Synthetic remote response is truncated JSON', {
        'error_type':'truncated_json_response', 'response_sha256':hashlib.sha256(b'{incomplete').hexdigest(),
        'finish_reason':'length', 'usage':{}, 'elapsed_seconds':0, 'artifact_written':False})


def main():
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('External network forbidden'))
    operation, root, rid = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    sys.path.insert(0, str(root / 'scripts'))
    if operation == 'plan':
        from resolve_generation_content_plan_v1 import resolve_generation_content_plan
        result = resolve_generation_content_plan(pipeline_root=root, request_id=rid, transport=plan, model='synthetic-style-planner')
    else:
        from resolve_generation_batch_v1 import resolve_generation_batch
        result = resolve_generation_batch(pipeline_root=root, request_id=rid,
            transport=invalid_generate if operation=='generate-invalid-persona' else partial_generate if operation=='generate-partial'
                else invalid_response if operation=='generate-invalid-response' else generate,
            model='synthetic-style-writer',
            **({'operation_id':sys.argv[4], 'intent_sha256':sys.argv[5]} if len(sys.argv)>4 else {}))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        if not getattr(exc, 'code', None): raise
        print(json.dumps({'ok':False,'code':exc.code,'message':str(exc)},ensure_ascii=False))
        raise SystemExit(2) from exc
