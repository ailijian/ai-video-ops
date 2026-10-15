"""Trusted local operations grant/revoke. Never invoked from an HTTP route."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.case_library_access import manage_reviewer

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id',type=int,required=True)
    parser.add_argument('--action',choices=['grant','revoke'],required=True)
    parser.add_argument('--reason',required=True)
    args=parser.parse_args()
    result=manage_reviewer(Settings.from_environment(),args.user_id,action=args.action,
                           operator=getpass.getuser(),reason=args.reason)
    print(f"{result['action']} user_id={result['user_id']} event={result['event_id']} sha256={result['event_sha256']}")
