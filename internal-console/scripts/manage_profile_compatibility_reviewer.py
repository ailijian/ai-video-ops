"""Trusted local Compatibility grant/revoke; never an HTTP management route."""
import argparse
import getpass
import json
import sys
from pathlib import Path

console_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(console_root))
sys.path.insert(0, str(console_root.parent / 'ops-pipeline/scripts'))

from app.config import Settings
from app.profile_compatibility_gateway import manage_reviewer


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--action', choices=['grant', 'revoke'], required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    result = manage_reviewer(Settings.from_environment(), args.user_id,
        action=args.action, operator=getpass.getuser(), reason=args.reason)
    print(json.dumps(result, ensure_ascii=False))
