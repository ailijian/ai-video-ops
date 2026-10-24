"""Explicit external synthetic model transport; all native production Gates run."""
import hashlib
import json
import socket
import sys
import os
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


def history_plan_transport(prompt):
    result=plan_transport(prompt)
    candidate=result['payload']['candidates'][0]
    candidate['supporting_fact_refs']+=['pricing_facts','included_service_facts','differentiators']
    return response(result['payload'])


def history_script_transport(prompt):
    result=script_transport(prompt)
    for item in result['payload']['items']:
        item['narration']+='午餐套餐29元，仅限到店自取，不含配送。套餐含一份主食与两份蔬菜，门店提供密封餐盒。下单时单独核对忌口。'
        item['persona_fact_refs_used']+=['pricing_facts','included_service_facts','differentiators']
    return response(result['payload'])


def main():
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('External network forbidden in synthetic validation'))
    operation, root, request_id = sys.argv[1], Path(sys.argv[2]).resolve(), sys.argv[3]
    sys.path.insert(0, str(root / 'scripts'))
    if operation in {'plan','plan-news-history'}:
        from resolve_generation_content_plan_v1 import resolve_generation_content_plan
        result = resolve_generation_content_plan(pipeline_root=root, request_id=request_id,
            transport=history_plan_transport if operation=='plan-news-history' else plan_transport,
            model='isolated-synthetic-planner-no-network')
    elif operation in {'generate','generate-news-history', 'generate-fail', 'generate-slow', 'generate-memory-race'} or operation.startswith('generate-crash-'):
        import resolve_generation_batch_v1 as native
        import generation_recovery_v1 as recovery
        from resolve_generation_batch_v1 import resolve_generation_batch
        calls = root / 'data/metrics/generation_requests' / request_id / 'synthetic_transport_calls.jsonl'
        def count_call():
            calls.parent.mkdir(parents=True,exist_ok=True)
            with calls.open('a',encoding='utf-8') as handle:
                handle.write(json.dumps({'operation':operation})+'\n')
        def success_transport(prompt):
            count_call()
            if operation=='generate-memory-race':
                import subprocess
                subprocess.run([sys.executable,str(Path(__file__).with_name('delivery_memory_disturbance.py')),str(root),request_id],check=True)
            if operation=='generate-slow':
                import time
                time.sleep(40)  # Explicit external provider latency, browser running-state evidence.
            return history_script_transport(prompt) if operation=='generate-news-history' else script_transport(prompt)
        def fail_transport(_):
            count_call()
            raise RuntimeError('Explicit synthetic external model transport interruption')
        if operation.startswith('generate-crash-'):
            point = operation.removeprefix('generate-crash-')
            original_publish, original_candidate = recovery.publish, native.persist_candidate_batch
            original_batch, original_pack = recovery.write_once, recovery.publish_text
            def publish(path,*args,**kwargs):
                result = original_publish(path,*args,**kwargs)
                if (point=='dispatch' and path.name=='dispatch.json') or (point=='result' and path.name=='result.json'):
                    os._exit(91)
                return result
            def candidate(*args,**kwargs):
                if point=='response':os._exit(91)
                result=original_candidate(*args,**kwargs)
                if point=='candidate':os._exit(91)
                return result
            def batch(path,*args,**kwargs):
                result=original_batch(path,*args,**kwargs)
                if point=='batch' and path.name=='generation_batch_v1.json':os._exit(91)
                return result
            def pack(path,*args,**kwargs):
                result=original_pack(path,*args,**kwargs)
                if point=='pack':os._exit(91)
                return result
            recovery.publish, native.persist_candidate_batch = publish, candidate
            recovery.write_once, recovery.publish_text = batch, pack
        result = resolve_generation_batch(pipeline_root=root, request_id=request_id,
            transport=fail_transport if operation == 'generate-fail' else success_transport,
            model='isolated-synthetic-writer-no-network',
            **({'operation_id': sys.argv[4], 'intent_sha256': sys.argv[5]} if len(sys.argv) > 4 else {}))
    else:
        raise ValueError('Unknown isolated model boundary operation')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        # Preserve native typed failures across the synthetic transport boundary,
        # just as the real native CLI does; never return traceback/path text.
        if not getattr(exc, 'code', None):
            raise
        print(json.dumps({'ok': False, 'code': exc.code, 'message': str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
