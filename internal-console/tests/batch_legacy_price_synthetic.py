"""Only external legacy Mix transport is synthetic, with approved price facts."""
import json
from pathlib import Path
import socket
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'ops-pipeline/tests'))
from compatibility_creation_synthetic import plan_transport, script_transport, response


def plan(prompt):
    context = json.loads(prompt.split('SAFE CONTENT PLANNING CONTEXT:\n', 1)[1])
    price = context['business_persona']['facts']['pricing_facts'][0]
    included = context['business_persona']['facts']['included_service_facts'][0]
    result = plan_transport(prompt)
    result['payload']['candidates'][0].update(primary_topic='午餐套餐价格与自取条件',
        audience_need='有工作日午间自取需求的住户，希望知道午餐套餐价格和不含配送的适用条件',
        content_job='解释已批准套餐价格、包含项目与自取及配送的适用条件',
        primary_fact_refs=['pricing_facts', 'included_service_facts'], supporting_fact_refs=['customer_pains', 'customer_use_cases'],
        central_claim=price+'；'+included, central_claim_key='approved_lunch_price_and_collection_conditions',
        primary_fact_atom_refs=['external-provider-invalid-primary-atom'],
        exclusive_anchor={'kind':'price', 'value':price, 'fact_refs':['pricing_facts']},
        why_publish='让附近需要午间自取的住户明确套餐价格、包含项目和配送边界，再决定是否适合自己的需求。')
    return response(result['payload'])


def generate(prompt):
    result = script_transport(prompt)
    for item in result['payload']['items']:
        item.update(title='午餐套餐价格与自取条件',
            narration='工作日午间想自取餐食，希望提前说明忌口。'+item['central_claim']+'套餐含一份主食与两份蔬菜，门店提供密封餐盒。',
            persona_fact_refs_used=['pricing_facts', 'included_service_facts', 'customer_pains', 'customer_use_cases'],
            speaker_fact_refs_used=[], claim_candidates=[{'text':item['central_claim'], 'persona_fact_refs':['pricing_facts'], 'speaker_fact_refs':[]}])
    return response(result['payload'])


if __name__ == '__main__':
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('External network forbidden'))
    operation, root, rid = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    sys.path.insert(0, str(root / 'scripts'))
    if operation == 'plan':
        from resolve_generation_content_plan_v1 import resolve_generation_content_plan
        value = resolve_generation_content_plan(pipeline_root=root, request_id=rid, transport=plan, model='synthetic-legacy-price')
    else:
        from resolve_generation_batch_v1 import resolve_generation_batch
        value = resolve_generation_batch(pipeline_root=root, request_id=rid, transport=generate, model='synthetic-legacy-price')
    print(json.dumps(value, ensure_ascii=False))
