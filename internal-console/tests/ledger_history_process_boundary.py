"""Native history crash injector; never fabricates Ledger or approval bytes."""
import json,os,sys
from pathlib import Path
root=Path(sys.argv[1]);rid=sys.argv[2];kind=sys.argv[3];window=sys.argv[4]
sys.path.insert(0,str(root/'scripts'))
import ledger_history_v1 as history
from profile_compatibility_decisions_v1_1 import read
payload=json.load(sys.stdin)
original_snapshot=history.snapshot
def snapshot(*args,**kwargs):
    result=original_snapshot(*args,**kwargs)
    if window=='snapshot_saved':os._exit(91)
    return result
history.snapshot=snapshot
original_write=history.write_once
def history_write(path,value,**kwargs):
    result=original_write(path,value,**kwargs)
    names={'transition_prepared':'event.json','event_sealed':'receipt.json','anchor_saved':'generation_export_anchor_evidence_v1.json'}
    if Path(path).name==names.get(window):os._exit(91)
    return result
history.write_once=history_write
if kind=='mix':
    import close_generation_export_v1 as owner
    original=owner.write_new_json
    def native_write(path,value):
        result=original(path,value)
        if ((window=='ledger_published' and Path(path).name=='content_ledger_v1.json') or
            (window=='closure_saved' and Path(path).name=='generation_export_closure_v1.json')):os._exit(91)
        return result
    owner.write_new_json=native_write
    intent=read(root/'data/generation_batches'/rid/'generation_export_intent_v1.json')
    result=owner.close_generation_export(pipeline_root=root,request_id=rid,excel_path=root/intent['output_path'],
        authorization_context=payload['authorization_context'])
else:
    import news_delivery_v1 as owner
    original=owner.write_new_json
    def native_write(path,value):
        result=original(path,value)
        if window=='closure_saved' and Path(path).name=='news_delivery_export_closure_v1.json':os._exit(91)
        return result
    owner.write_new_json=native_write
    result=owner.export_news_delivery(pipeline_root=root,request_id=rid,export_context=payload['export_context'])
print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
