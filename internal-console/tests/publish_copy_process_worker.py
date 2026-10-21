"""Real Task runner process; synthetic provider and crash injector only."""
import json
import os
import subprocess
import sys
from pathlib import Path
config, tid, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
value = json.loads(config.read_text('utf-8')); project = Path(value.pop('executing_project'))
for key in ('repo_root','console_root','pipeline_root','database_path'): value[key] = Path(value[key])
value['novel_news_validation_phones'] = tuple(value['novel_news_validation_phones'])
value.update(task_lease_seconds=2, task_heartbeat_seconds=1)
sys.path.insert(0,str(project/'internal-console'));sys.path.insert(0,str(project/'ops-pipeline/scripts'))
from app.config import Settings
from app.background_task_service import BackgroundTaskRunner
import app.background_task_service as task_owner
original = subprocess.run
def boundary(command,*args,**kwargs):
    if len(command)>2 and Path(command[1]).name == 'publish_copy_v1.py' and command[2] in {'run','export'}:
        rid = command[command.index('--request-id')+1]
        command = [command[0],str(project/'internal-console/tests/publish_copy_process_boundary.py'),str(project),str(value['pipeline_root']),rid,command[2],mode]
        result = original(command,*args,**kwargs)
        if result.returncode == 91: os._exit(92)
        return result
    return original(command,*args,**kwargs)
subprocess.run = boundary
if mode == 'late_response':
    update = task_owner.update_task
    def update_task(*args,**kwargs):
        if kwargs.get('status') == 'running' and kwargs.get('worker_id'): return
        return update(*args,**kwargs)
    task_owner.update_task = update_task
runner = BackgroundTaskRunner(Settings(**value)); runner._run(tid); runner.close()
