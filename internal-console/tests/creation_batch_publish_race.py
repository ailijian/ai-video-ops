"""Only schedule a competing edit; both operations use original Native writers."""
import copy,json,sys,threading
from pathlib import Path
root=Path(sys.argv[1]);rid=sys.argv[2]
sys.path.insert(0,str(root/'scripts'))
from publish_copy_v1 import edit,draft,source
from human_review_operations_v1 import read
import creation_delivery_v1 as deliveries
from export_mix_excel_v1 import export_supplemental_delivery
incoming=json.load(sys.stdin);context=incoming['context'];reference=incoming['draft_ref']
payload=copy.deepcopy(draft(root,rid)[1]['payload'])
payload['items'][0]['publish_title']='本期介绍'+payload['items'][0]['publish_title']
entered=threading.Event();edited=threading.Event();errors=[]
def competitor():
    try:
        assert entered.wait(10)
        edit(root,rid,reference,payload,context)
        edited.set()
    except BaseException as exc:errors.append(type(exc).__name__)
thread=threading.Thread(target=competitor);thread.start()
original_export=deliveries.export
def scheduled_export(*args,**kwargs):
    original_core=kwargs['ensure_core']
    def core(src):
        entered.set()
        assert not edited.wait(.3),'A Publish edit committed between prevalidation and core admission'
        return original_core(src)
    return original_export(*args,**{**kwargs,'ensure_core':core})
deliveries.export=scheduled_export
try:
    delivered=export_supplemental_delivery(pipeline_root=root,request_id=rid,
        authorization_context=context,expected_draft_ref=reference)
    assert delivered['state']=='completed'
finally:thread.join(20)
assert not thread.is_alive() and not errors and edited.is_set(),errors
assert draft(root,rid)[1]['payload']==payload
ledger=read(root/'data/content_ledgers'/incoming['business_id']/'content_ledger_v1.json')
assert len(ledger['entries'])==1
assert len(list(deliveries.directory(source(root,rid)).glob('*/completion.json')))==1
print(json.dumps({'delivered':True,'competing_edit_serialized':True,'ledger_entries':1}))
