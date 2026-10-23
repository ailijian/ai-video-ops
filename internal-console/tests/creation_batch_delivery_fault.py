"""Kill only at original C08 persistence boundaries; never replace any gate."""
import json,os,sys
from pathlib import Path
point,script,*arguments=sys.argv[1:]
root=Path(arguments[arguments.index('--pipeline-root')+1])
bid=arguments[arguments.index('--batch-id')+1]
sys.path.insert(0,str(root/'scripts'))
import creation_delivery_v1 as owner
original=owner.write_once
def write(path,value):
    result=original(path,value)
    version=value.get('schema_version')
    if (point=='prepared' and version=='creation-composite-delivery-prepared-v1.0'
            or point=='receipt' and version=='creation-composite-delivery-receipt-v1.0'
            or point=='complete' and version=='creation-composite-delivery-completion-v1.0'):
        os._exit(96)
    return result
owner.write_once=write
payload=json.load(sys.stdin);context=payload.pop('authorization_context')
result=owner.composite_export(root,bid,context,**payload)
print(json.dumps({'ok':True,'result':result}))
