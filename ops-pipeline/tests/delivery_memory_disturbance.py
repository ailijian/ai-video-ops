"""Independent NEGATIVE test disturbance. Never writes an approval/exposure."""
from pathlib import Path
import sys,json,os,hashlib
root=Path(sys.argv[1]).resolve();rid=sys.argv[2]
sys.path.insert(0,str(root/'scripts'))
from profile_compatibility_release_v1_1 import CONFIG
assert json.loads((root/CONFIG).read_text(encoding='utf-8'))['purpose']=='isolated-validation'
from close_generation_export_v1 import _empty_ledger
request=json.loads((root/'data/generation_requests'/rid/'generation_request_v1.json').read_text(encoding='utf-8'))
path=root/'data/content_ledgers'/request['persona_id']/'content_ledger_v1.json'
assert not path.exists(),'Do not modify an existing canonical Ledger'
path.parent.mkdir(parents=True,exist_ok=True)
value=_empty_ledger(business_id=request['persona_id'],created_at=request['created_at'])
assert value['entries']==[]
with path.open('x',encoding='utf-8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2)
trace=root/'data/metrics/generation_requests'/rid/'negative_independent_memory_disturbance.json'
trace.write_text(json.dumps({'pid':os.getpid(),'negative_test_only':True,'approval_created':False,
    'ledger_entries':0,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}),encoding='utf-8')
