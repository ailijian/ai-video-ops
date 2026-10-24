"""Crash at the durable response boundary after a synthetic RPC, not a Gate."""
import os
from pathlib import Path
import runpy
import sys

point, helper = sys.argv[1], Path(sys.argv[2])
sys.argv = sys.argv[2:]
sys.path.insert(0, str(helper.parent))
sys.path.insert(0, str(Path(sys.argv[2]) / 'scripts'))
import batch_provider_recovery_v1 as recovery

original = recovery.write_once


def publish(path, value):
    if Path(path).name == 'response.json' and point == 'before-response':
        os._exit(91)
    result = original(path, value)
    if Path(path).name == 'response.json' and point == 'after-response':
        os._exit(92)
    if Path(path).name == 'generated.json' and 'native_result' in Path(path).parts and point == 'initial-result':
        os._exit(94)
    return result


recovery.write_once = publish
if point == 'c3-result':
    import generation_recovery_v1 as native_recovery
    original_native_publish = native_recovery.publish
    def publish_result(path, value, version):
        result = original_native_publish(path, value, version)
        if Path(path).name == 'result.json':
            os._exit(93)
        return result
    native_recovery.publish = publish_result
runpy.run_path(str(helper), run_name='__main__')
