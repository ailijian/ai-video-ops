"""REC-01 test-only external synthetic boundary and process crash injection.

All business writers, validation, authentication and Task owners remain native.
This script is not installed as a runtime model fallback.
"""
import json
import os
import sys
import time
from pathlib import Path

project, root, rid, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
sys.path.insert(0, str(root / 'scripts'))
sys.path.insert(0, str(project / 'internal-console/tests'))
import novel_news_v1 as owner
import novel_news_generation_recovery_v1 as attempt_owner
import profile_compatibility_decisions_v1_1 as persistence
from news_qualification_transport import novel_transport

payload = json.load(sys.stdin)
log = root / 'data/metrics' / rid / 'rec01_calls.jsonl'
control = root / 'data/metrics' / rid / 'allow_late_response'


def transport(prompt):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'operation_id': payload['operation_id'], 'mode': mode}) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    if mode == 'sent_without_response':
        os._exit(91)
    if mode == 'late_response':
        deadline = time.monotonic() + 60
        while not control.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
    return novel_transport(prompt)


original_record = attempt_owner.record
original_write = persistence.write_once

if mode in {'before_intent', 'after_intent'}:
    def intent_write(path, value, **kwargs):
        if Path(path).name == 'intent.json' and mode == 'before_intent':
            os._exit(91)
        result = original_write(path, value, **kwargs)
        if Path(path).name == 'intent.json':
            os._exit(91)
        return result
    attempt_owner.write_once = intent_write
    owner.prepare_novel_news_generation(pipeline_root=root, request_id=rid,
        authorization_context=payload['authorization_context'])
    raise AssertionError('Expected admission interruption')


def record(*args, **kwargs):
    kind = args[3]
    if mode == 'response_before_save' and kind == 'response':
        os._exit(91)
    result = original_record(*args, **kwargs)
    if (mode, kind) in {('dispatch_before_send', 'dispatch'), ('prepared_before_plan', 'response'),
                         ('result_before_task', 'result')}:
        os._exit(91)
    return result


def write(path, value, **kwargs):
    result = original_write(path, value, **kwargs)
    if mode == 'plan_before_result' and Path(path).name == 'novel_news_beat_plan_v1.json':
        os._exit(91)
    return result


attempt_owner.record = record
persistence.write_once = write
try:
    result = owner.generate_novel_news_plan(pipeline_root=root, request_id=rid, transport=transport, **payload)
    print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
except RuntimeError as exc:
    print(json.dumps({'ok': False, 'code': getattr(exc, 'code', 'SYNTHETIC_BOUNDARY_FAILED')}))
    raise SystemExit(2)
