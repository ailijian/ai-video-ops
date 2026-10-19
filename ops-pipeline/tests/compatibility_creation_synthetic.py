"""Explicit external synthetic model transport; all native production Gates run."""
import hashlib
import json
import socket
import sys
from pathlib import Path


def response(payload):
    return {'payload': payload, 'response_sha256': hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            'usage': {}, 'elapsed_seconds': 0, 'finish_reason': 'stop'}


def plan_transport(prompt):
    context = json.loads(prompt.split('SAFE CONTENT PLANNING CONTEXT:\n', 1)[1])
    # One supported idea, no repeated candidates to fill the configured pool.
    return response({'candidates': [{
        'concept_id': 'CONCEPT_001', 'audience_need': '希望提前说明忌口的午间自取顾客，想了解下单时如何核对。',
        'content_job': '解释从核对忌口到标记餐盒的处理流程', 'primary_topic': '订单忌口核对流程',
        'primary_fact_refs': ['process_facts'], 'supporting_fact_refs': ['customer_pains', 'customer_use_cases'],
        'speaker_fact_refs': ['speaker_role_facts'], 'central_claim': '先核对忌口，再按单配菜，制作后标记餐盒',
        'central_claim_key': 'order_dietary_check_to_box_marking',
        'exclusive_anchor': {'kind': 'process', 'value': '先核对忌口，再按单配菜，制作后标记餐盒', 'fact_refs': ['process_facts']},
        'customer_story_ref': None, 'speaker_id': context.get('speaker', {}).get('speaker_id'),
        'opening_strategy': '从提前说明忌口的实际需要切入', 'narrative_mode': '逐步说明核对和制作流程',
        'visual_anchor': '核对订单与标记餐盒的工作过程', 'hero_shot_role': '展示核对订单的动作',
        'supporting_shot_roles': ['配菜与餐盒标记'], 'storyboard_shape': None,
        'why_publish': '让午间自取且有忌口需求的顾客理解下单核对、配菜与餐盒标记之间的关系。',
    }]})


def script_transport(prompt):
    context = json.loads(prompt.split('SAFE GENERATION CONTEXT:\n', 1)[1])
    items = []
    for slot in context['slots']:
        selected = slot.get('selected_content_plan') or {}
        items.append({'slot_id': slot['slot_id'], 'concept_ref': selected.get('concept_ref'),
            'central_claim': selected['central_claim'], 'central_claim_key': selected['central_claim_key'],
            'title': '忌口怎样核对到餐盒',
            'narration': '工作日午间想自取餐食，又希望提前说明忌口，下单时先把需要注意的地方说清楚。门店先核对忌口，再按单配菜，制作后标记餐盒。从下单核对到餐盒标记，这里说明的是餐食的处理流程。小周亲自负责核对订单，可以从自己的职责说明核对这一步。',
            'persona_fact_refs_used': ['process_facts', 'customer_pains', 'customer_use_cases'],
            'speaker_fact_refs_used': ['speaker_role_facts'],
            'claim_candidates': [{'text': selected['central_claim'], 'persona_fact_refs': ['process_facts'], 'speaker_fact_refs': []}],
            'customer_feedback_provenance': [], 'cta': {'present': False, 'text': None}})
    return response({'items': items})


if __name__ == '__main__':
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('External network forbidden in synthetic validation'))
    operation, root, request_id = sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3]
    sys.path.insert(0, str(root / 'scripts'))
    if operation == 'plan':
        from resolve_generation_content_plan_v1 import resolve_generation_content_plan
        result = resolve_generation_content_plan(pipeline_root=root, request_id=request_id,
            transport=plan_transport, model='isolated-synthetic-planner-no-network')
    elif operation in {'generate', 'generate-fail'}:
        from resolve_generation_batch_v1 import resolve_generation_batch
        def fail_transport(_):
            raise RuntimeError('Explicit synthetic external model transport interruption')
        result = resolve_generation_batch(pipeline_root=root, request_id=request_id,
            transport=fail_transport if operation == 'generate-fail' else script_transport,
            model='isolated-synthetic-writer-no-network')
    else:
        raise ValueError('Unknown isolated model boundary operation')
    print(json.dumps(result, ensure_ascii=False))
