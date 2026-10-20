"""Test-only process interruption in the original Native export writer."""
import json
import sys
from pathlib import Path

root, rid, kind, window = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, str(root / 'scripts'))
payload = json.load(sys.stdin)
if kind == 'novel':
    import novel_news_v1 as owner
    name = '_write_new'
    receipt = owner._paths(root, rid)['receipt']
    closure = owner._paths(root, rid)['closure']
else:
    import news_delivery_v1 as owner
    name = 'write_new_json'
    receipt = owner._request_root(root, rid) / 'news_dynamic_excel_export_receipt_v1.json'
    closure = owner._request_root(root, rid) / 'news_delivery_export_closure_v1.json'
original = getattr(owner, name)
def fault(path, value):
    if Path(path) == receipt and window == 'published':
        raise OSError('Injected before Export Receipt')
    result = original(path, value)
    if (Path(path) == receipt and window == 'receipt') or (Path(path) == closure and window == 'closure'):
        raise OSError('Injected after Export Receipt')
    return result
setattr(owner, name, fault)
try:
    function = owner.export_novel_news if kind == 'novel' else owner.export_news_delivery
    function(pipeline_root=root, request_id=rid, export_context=payload['export_context'])
    raise AssertionError('Expected native export interruption')
except OSError:
    print(json.dumps({'ok': False, 'code': 'NEWS_EXPORT_INTERRUPTED'}))
    raise SystemExit(2)
