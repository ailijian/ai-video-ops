"""Only synthetic external transport waits; Native owners are untouched."""
import runpy
import sys
import time
from pathlib import Path

helper = Path(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, str(helper.parent))
namespace = runpy.run_path(str(helper), run_name='synthetic_boundary')
original = namespace['plan']
root = Path(sys.argv[2])

def slow(prompt):
    marker = root/'data/metrics/batch_inflight_probe'
    marker.mkdir(parents=True, exist_ok=True)
    (marker/'entered').write_text('external-dispatch', encoding='utf-8')
    deadline = time.monotonic()+30
    while not (marker/'release').is_file():
        if time.monotonic()>deadline:
            raise TimeoutError('Synthetic provider wait expired')
        time.sleep(0.05)
    return original(prompt)

namespace['main'].__globals__['plan'] = slow
namespace['main']()
