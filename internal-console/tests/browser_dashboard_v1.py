"""Fresh DASH-1 offline ASGI nodes; fixtures stop only at model/acquisition boundaries."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi.testclient import TestClient
from app.auth_service import provision_user
from app.main import build_app
from conftest import settings as fixture_settings
from browser_brand_ui1 import prepare, fixture_notice, case_fixture_driver, customer_driver, PHONES, PASSWORD, call

REPO=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir',type=Path,required=True)
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--scenario',choices=['normal','empty','partial'],default='normal')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();root=args.workdir.resolve()
    project=next(p for p in REPO.parents if (p/'.git').is_dir())
    if not root.is_relative_to(project/'.local') or args.port in {8000,18021}: parser.error('New project-local isolated root/port required')
    if not args.resume:
        if root.exists(): parser.error('Fresh root required (or --resume)')
        root.mkdir(parents=True)
        if args.scenario=='empty':
            from app.config import Settings
            settings=Settings(repo_root=root,console_root=REPO/'internal-console',pipeline_root=root/'ops-pipeline',
                database_path=root/'console.sqlite3',python_executable=sys.executable)
            shutil.copytree(REPO/'ops-pipeline/scripts',settings.pipeline_root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        else:
            settings=fixture_settings.__wrapped__(root)
            shutil.copytree(REPO/'internal-console/tests/fixtures/customer_navigation_v1/data',settings.pipeline_root/'data',dirs_exist_ok=True)
            shutil.copy2(REPO/'ops-pipeline/speaker_prompt.md',settings.pipeline_root/'speaker_prompt.md')
            shutil.copytree(REPO/'internal-console/tests/fixtures/customer_speaker_e2',root/'internal-console/tests/fixtures/customer_speaker_e2')
    else:
        manifest=json.loads((root/'dashboard-node.json').read_text(encoding='utf-8'))
        if not manifest['fixture_only'] or manifest['source_worktree']!=str(REPO):parser.error('Wrong fixture node')
        from app.config import Settings
        settings=Settings(repo_root=root,console_root=REPO/'internal-console',pipeline_root=root/'ops-pipeline',
            database_path=root/'console.sqlite3',python_executable=sys.executable)
    settings=replace(settings,repo_root=root,console_root=REPO/'internal-console',
        pipeline_python_executable=str(REPO/'ops-pipeline/.venv/Scripts/python.exe'),
        case_analysis_worker_enabled=False,customer_analysis_worker_enabled=False,speaker_analysis_worker_enabled=False,
        background_worker_enabled=False,default_business_id=None,session_cookie_name=f'dash_fixture_{args.port}')
    if not args.resume:
        if args.scenario=='normal':prepare(settings,root)
        else:
            with TestClient(build_app(settings)) as client:
                for phone in PHONES:
                    provision_user(settings.database_path,phone)
                    login=call(client,'post','/api/auth/login',json={'phone':phone,'password':'123456'})
                    call(client,'post','/api/auth/change-password',headers={'X-CSRF-Token':login['csrf_token']},json={
                        'current_password':'123456','new_password':PASSWORD,'confirm_password':PASSWORD})
            if args.scenario=='partial':
                path=settings.pipeline_root/'data/generation_requests/gen_unreadable_fixture/generation_request_v1.json'
                path.parent.mkdir(parents=True);path.write_text('{ invalid synthetic source',encoding='utf-8')
        (root/'dashboard-node.json').write_text(json.dumps({'fixture_only':True,'source_worktree':str(REPO),
            'scenario':args.scenario,'port':args.port,'database':str(settings.database_path),
            'canonical_root':str(settings.pipeline_root),'remote_model_calls':0,'real_workers_enabled':False},indent=2),encoding='utf-8')
    application=build_app(settings);fixture_notice(application)
    @application.middleware('http')
    async def request_evidence(request,call_next):
        began=time.perf_counter()
        response=await call_next(request)
        with (root/'http-trace.jsonl').open('a',encoding='utf-8') as output:
            output.write(json.dumps({'at':time.time(),'method':request.method,'path':request.url.path,
                'query':request.url.query,'status':response.status_code,
                'elapsed_ms':round((time.perf_counter()-began)*1000,2)},ensure_ascii=False)+'\n')
        return response
    stop=threading.Event()
    threads=[]
    if args.scenario=='normal':
        threads=[threading.Thread(target=customer_driver,args=(settings,stop,.4,root),daemon=True),
                 threading.Thread(target=case_fixture_driver,args=(settings,stop,root),daemon=True)]
    for thread in threads:thread.start()
    try:uvicorn.run(application,host='127.0.0.1',port=args.port,workers=1,access_log=False)
    finally:
        stop.set()
        for thread in threads:thread.join(timeout=4)


if __name__=='__main__':main()
