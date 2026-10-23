"""Only the external Novel response is synthetic; original Native CLI inputs."""
import argparse
import json
from pathlib import Path
import socket
import sys

parser = argparse.ArgumentParser()
parser.add_argument('operation', choices=['generate'])
parser.add_argument('--pipeline-root', type=Path, required=True)
parser.add_argument('--request-id', required=True)
parser.add_argument('--actor')
args = parser.parse_args()
sys.path.insert(0, str(args.pipeline_root / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))
from novel_news_v1 import generate_novel_news_plan
from news_qualification_transport import novel_transport


def transport(prompt):
    path = args.pipeline_root / 'data/metrics' / args.request_id / 'batch_novel_calls.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'provider':'synthetic', 'operation':'novel_generation'})+'\n')
    return novel_transport(prompt)


socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('External network forbidden'))
try:
    result = generate_novel_news_plan(pipeline_root=args.pipeline_root, request_id=args.request_id,
        generated_by=args.actor, transport=transport, **json.loads(sys.stdin.read()))
    print(json.dumps({'ok':True, 'result':result}, ensure_ascii=False))
except RuntimeError as exc:
    if not getattr(exc, 'code', None):
        raise
    print(json.dumps({'ok':False, 'code':exc.code, 'message':str(exc)}, ensure_ascii=False))
    raise SystemExit(2)
