"""Crash only after genuine native owner persistence; no approval bypass."""
import sys, os, importlib, runpy
from pathlib import Path
point, script, *args = sys.argv[1:]
sys.path.insert(0,str(Path(script).parent))
module=importlib.import_module(Path(script).stem)
if point in {'review','approved','human_receipt'}:
    original=module.write_or_validate_json
    target={'review':'generation_human_review_v2.json','approved':'approved_generation_batch_v1.json',
            'human_receipt':'generation_batch_approval_receipt.json'}[point]
    def persist(path,*a,**kw):
        result=original(path,*a,**kw)
        if Path(path).name==target:os._exit(91)
        return result
    module.write_or_validate_json=persist
elif point=='xlsx':
    original=module.export_mix_excel
    def export(*a,**kw):
        original(*a,**kw)
        os._exit(91)
    module.export_mix_excel=export
elif point=='export_intent':
    original=module.prepare_mix_export
    def prepare(*a,**kw):
        original(*a,**kw);os._exit(91)
    module.prepare_mix_export=prepare
elif point=='publication':
    original=module.partial.publish
    def publish(path,*a,**kw):
        result=original(path,*a,**kw)
        if Path(path).name=='generation_export_publication_v1.json':os._exit(91)
        return result
    module.partial.publish=publish
elif point in {'ledger','closure'}:
    original=module.write_new_json
    def persist(path,*a,**kw):
        result=original(path,*a,**kw)
        if (point=='closure' and Path(path).name=='generation_export_closure_v1.json') or (point=='ledger' and 'content_ledgers' in Path(path).parts):os._exit(91)
        return result
    module.write_new_json=persist
sys.argv=[script,*args]
module.main()
if point=='export_receipt':os._exit(91)
