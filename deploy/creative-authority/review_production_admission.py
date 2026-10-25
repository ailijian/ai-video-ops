"""Trusted offline Human production-scope preview/confirm. Never grants roles."""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ops-pipeline/scripts'))
from profile_compatibility_contract_v1_1 import CompatibilityError,REF,validate,safe_relative
from profile_compatibility_decisions_v1_1 import read
from production_admission_v1 import prepare,confirm
from human_review_operations_v1 import io_path


def read_news_validation_refs(path):
    """The CLI input is a pair of refs, not an Authority object document."""
    if path is None:return None
    value=json.loads(io_path(path).read_text(encoding='utf-8'))
    if not isinstance(value,list) or len(value)!=2:
        raise CompatibilityError('Both Native News validation references are required as a JSON array')
    for item in value:
        validate(item,REF)
        safe_relative(item['path'])
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preview','confirm','withdraw-preview'])
    parser.add_argument('--pipeline-root',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--repo-root',type=Path,required=True)
    parser.add_argument('--user-id',type=int,required=True)
    parser.add_argument('--operation-id',required=True)
    parser.add_argument('--scope',type=Path)
    parser.add_argument('--news-validation-refs',type=Path)
    parser.add_argument('--reason')
    parser.add_argument('--expected-preview-sha256')
    args=parser.parse_args()
    if not args.database.is_file():parser.error('Existing Console database is required')
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as db:
        node=db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
    if not node:parser.error('Existing stable Console namespace is required')
    actor={'namespace':node[0],'user_id':args.user_id}
    try:
        if args.action=='confirm':
            if not args.expected_preview_sha256:parser.error('Confirm requires the exact displayed preview SHA')
            result=confirm(args.pipeline_root,args.database,actor,args.operation_id,
                args.expected_preview_sha256,args.repo_root)
        else:
            if not args.reason or args.action=='preview' and not args.scope:
                parser.error('Preview requires an explicit reason and scope')
            result=prepare(args.pipeline_root,args.database,actor,args.operation_id,
                read(args.scope) if args.scope else None,args.repo_root,reason=args.reason,
                action='approve' if args.action=='preview' else 'withdraw',
                news_validation_refs=read_news_validation_refs(args.news_validation_refs))
    except (RuntimeError,ValueError,OSError) as error:
        print(json.dumps({'ok':False,'code':getattr(error,'code','PRODUCTION_ADMISSION_BLOCKED'),
            'message':str(error)},ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps({'ok':True,**result},ensure_ascii=False))


if __name__=='__main__':main()
