"""Test-only external transport/crash boundary. Native owners are not mocked."""
import json
import os
import sys
import time
from pathlib import Path

project, root, rid, command, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
sys.path.insert(0, str(root / 'scripts'))
import publish_copy_v1 as owner
import creation_delivery_v1 as delivery
from publish_copy_sources_v1 import source
payload = json.load(sys.stdin)
log = root / 'data/metrics' / rid / 'publish_copy_calls.jsonl'

def transport(prompt):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'operation_id': payload['operation_id'], 'mode': mode}) + '\n')
        handle.flush(); os.fsync(handle.fileno())
    if mode == 'sent_without_response': os._exit(91)
    if mode == 'late_response':
        control = log.parent / 'allow_publish_late_response'
        deadline = time.monotonic() + 45
        while not control.exists() and time.monotonic() < deadline: time.sleep(.05)
    data = json.loads(prompt[prompt.index('\n')+1:]); items = []
    for original in data['items']:
        units = original['units']; title = units[0]['text'] if units else original['title']
        text = '\n'.join(u['text'] for u in units) if units else original['narration']
        topics = [topic for topic in ['午餐套餐','到店自取','忌口','密封餐盒','主食','蔬菜','香菜','顾客','店主','门店',
                                    '餐盒','库存','营业时间','纸质菜单']
                  if topic in text or topic in title][:3]
        item = {'target_id': original['target_id'], 'source_version_sha256': data['source_version_sha256'],
                'publish_title': title, 'publish_body': text, 'topics': topics}
        if data['mode'] != 'mix':
            groups=([[0],[1,2],[3,4],[5],[6]] if len(units)==7 else
                    [[0],[1,2],[3],[4],[5,6],[7]] if len(units)==8 else [[i] for i in range(len(units))])
            item['production_headlines'] = [{'order': n, 'text': '，'.join(units[i]['text'] for i in group),
                'source_unit_ids': [units[i]['unit_id'] for i in group],
                'mapping_kind': 'merge' if len(group)>1 else 'extract'} for n,group in enumerate(groups,1)]
        items.append(item)
    return {'payload': {'items': items}}

original_write = owner.write_once
def write(path, value, **kwargs):
    name = Path(path).name
    if mode == 'before_intent' and name == 'intent.json': os._exit(91)
    result = original_write(path, value, **kwargs)
    if mode == 'selection_response_failure' and 'effective-version-event' in value.get('schema_version',''):
        raise RuntimeError('Synthetic response failure after canonical publication')
    windows = {'after_intent': 'intent.json', 'dispatch_before_send': 'dispatch.json',
               'prepared_before_draft': 'response.json', 'draft_before_result': '.draft',
               'result_before_task': 'result.json', 'intent_before_stage': 'intent.json',
               'prepared_before_output': 'prepared.json', 'receipt_before_completion': 'receipt.json',
               'completion_before_selection': 'completion.json', 'selection_before_response': '.event'}
    match = windows.get(mode)
    if match == name or match == '.draft' and value.get('schema_version') == 'publish-copy-draft-v1.0' or match == '.event' and 'effective-version-event' in value.get('schema_version',''):
        os._exit(91)
    return result
owner.write_once = write; delivery.write_once = write
original_record = owner._record
def record(*args, **kwargs):
    if mode == 'response_before_save' and args[3] == 'response': os._exit(91)
    return original_record(*args, **kwargs)
owner._record = record
original_link = os.link
def link(src, dst, *args, **kwargs):
    result = original_link(src, dst, *args, **kwargs)
    if mode == 'output_before_receipt' and '/output/deliveries/' in str(dst).replace('\\','/'):
        os._exit(91)
    if mode == 'stage_before_prepared' and Path(dst).name == 'staged.xlsx': os._exit(91)
    return result
os.link = link

try:
    if command == 'run':
        result = owner.run(root, rid, payload['operation_id'], payload['authorization_context'], transport=transport, task_id=payload.get('task_id'))
    elif command == 'prepare':
        path, value = owner.prepare(root, rid, payload['authorization_context'], expected_parent=payload.get('expected_parent'))
        result = {'operation_id': value['operation_id']}
    else: result = owner.export_delivery(root, rid, payload['authorization_context'], payload.get('expected_draft_ref'))
    print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
except Exception as exc:
    print(json.dumps({'ok':False,'code':getattr(exc,'code','BOUNDARY_FAILURE')},ensure_ascii=False))
    import traceback; traceback.print_exc(file=sys.stderr)
    sys.exit(1)
