"""Only model text is synthetic; explicitly communicate four approved source units."""
from pathlib import Path
import sys,json

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops-pipeline/tests'))
import creative_style_synthetic as provider

original_plan=provider.plan
def plan(prompt):
    result=original_plan(prompt)
    for candidate in result['payload']['candidates']:
        candidate['supporting_fact_refs'].append('differentiators')
    return result

original_generate=provider.generate
def generate(prompt):
    result=original_generate(prompt)
    for item in result['payload']['items']:
        item['narration']+='下单时单独核对忌口。'
        item['persona_fact_refs_used'].append('differentiators')
        for claim in item['claim_candidates']:
            claim['persona_fact_refs']=list(item['persona_fact_refs_used'])
    return result

provider.plan=plan;provider.generate=generate
try:provider.main()
except RuntimeError as exc:
    if not getattr(exc,'code',None):raise
    print(json.dumps({'ok':False,'code':exc.code,'message':str(exc)},ensure_ascii=False))
    raise SystemExit(2) from exc
