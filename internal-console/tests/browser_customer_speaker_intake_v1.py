"""Isolated current ASGI + real auth/CSRF + serial synthetic extraction driver.

Never targets runtime Authority. No network/model/GPU calls. Canonical analysis,
review, approval and task admission/recovery remain the production implementations.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse, Response
from app.auth_service import provision_user
from app.config import Settings
from app.main import build_app
from app.task_service import (
    claim_task,
    get_task,
    iter_queued_tasks,
    recover_expired_tasks,
    update_task,
)
from app.customer_task_service import CustomerTaskRunner
from app.speaker_task_service import SpeakerTaskRunner
from conftest import settings as fixture_settings

PHONES = ("19900001201", "19900001202")
PASSWORD = "OfflineReview2026!"


def structured_form_outputs(text):
    """Literal fixture projection of numbered forms; never a production extractor.

    Caller supplies privacy-projected text. Only explicitly labelled answers are
    copied, with exact source quotes; no semantic classification or inference.
    """
    import re

    def answers(block):
        headings = list(re.finditer(r"(?m)^\s*(\d{1,2})[.．、]\s*[^\n]*\n", block))
        return {
            int(match[1]): block[match.start():headings[i + 1].start() if i + 1 < len(headings) else len(block)].strip()
            for i, match in enumerate(headings)
        }

    def label(block, key):
        match = re.search(r"(?m)^\s*[-•]?\s*" + re.escape(key) + r"\s*[:：]\s*([^\n]+)", block)
        return (match[1].strip(), match[0].strip()) if match else (None, None)

    business = re.search(r"第一部分\s*[:：]\s*品牌与业务[^\n]*\n(.*?)(?=第二部分\s*[:：]|\Z)", text, re.S)
    facts, people = [], []
    if business:
        for number, topic in [(2, "primary_service"), (3, "core_audience"), (8, "differentiator")]:
            quote = answers(business[1]).get(number)
            if quote:
                value = quote.split("\n", 1)[1].strip()
                if value:
                    facts.append({"topic": topic, "value": [value], "evidence_quote": quote})
    people_section = re.search(r"第二部分\s*[:：]\s*视频人物[^\n]*\n(.*?)(?=第三部分\s*[:：]|\Z)", text, re.S)
    if people_section:
        # Match the standalone heading, never the explanatory sentence above it.
        for block in re.split(r"(?m)^\s*视频人物资料\s*$", people_section[1])[1:]:
            name, name_quote = label(block, "姓名")
            role, role_quote = label(block, "和品牌的关系")
            if not name or not role:
                continue
            own = answers(block)
            _, responsibility = label(block, "平时主要负责")
            personal = ([responsibility] if responsibility else []) + [own[n] for n in (2, 3, 4, 5) if n in own]
            people.append({"name": name, "public_role": role, "speaker_type_hint": "generic",
                "candidate_status": "explicit_speaker", "evidence_quotes": [name_quote, role_quote],
                "personal_material_quotes": personal, "explicit_forbidden_claims": []})
    # Speaker Draft receives only selected personal quotes, not the whole form.
    personal_facts = []
    if not business and not people_section:
        own = answers(text)
        for number, topic in [(2, "speaker_practice"), (3, "speaker_allowed_topics")]:
            quote = own.get(number)
            if quote and "\n" in quote:
                value = quote.split("\n", 1)[1].strip()
                if value:
                    personal_facts.append({"topic": topic, "value": [value], "evidence_quote": quote})
    return {"recognized": bool(business or people_section), "facts": facts,
        "speaker_candidates": people, "personal_facts": personal_facts}


def add_fixture_notice(application):
    """Mark this manual harness in every SPA view; production app is untouched."""
    @application.get("/isolated-fixture-notice.js", include_in_schema=False)
    def fixture_notice_script():
        # Same-origin script preserves the real application's CSP restrictions.
        return Response("""
const markFixture = () => {
  const main = document.querySelector('#app main');
  if (!main || main.querySelector('[data-isolated-fixture]')) return;
  const note = document.createElement('aside');
  note.dataset.isolatedFixture = ''; note.setAttribute('role', 'note');
  note.style.cssText = 'padding:12px;margin-bottom:16px;border:1px solid #b9cbbf;border-radius:8px;background:#edf3ee;color:#28533e;font-size:13px';
  note.textContent = '隔离验收：规则模拟解析，仅支持结构化表单与预置样本，不代表真实 AI 分析。';
  main.prepend(note);
};
new MutationObserver(markFixture).observe(document.getElementById('app'), {childList:true,subtree:true});
markFixture();
""", media_type="application/javascript", headers={"Cache-Control": "no-store"})

    # Register before build_app's SPA catch-all, without changing production routes.
    application.router.routes.insert(0, application.router.routes.pop())

    @application.middleware("http")
    async def fixture_notice(request, call_next):
        response = await call_next(request)
        if "text/html" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        notice = '<script src="/isolated-fixture-notice.js"></script>'
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return HTMLResponse(body.replace(b"</body>", notice.encode() + b"</body>"),
            status_code=response.status_code, headers=headers)


def inject_review_interruption(settings, root):
    """Test-only filesystem fault after durable receipt; no Human Gate is mocked."""
    from app import customer_gateway
    run = customer_gateway._run_json_command
    code = r'''
import sys,runpy
from pathlib import Path
script,marker,*args=sys.argv[1:]
sys.path.insert(0,str(Path(script).parent))
import customer_fact_review_v1 as owner
original=owner.write_atomic_json
def interrupted(path,value):
    if path.name=='customer_fact_review_v1.json' and not Path(marker).exists():
        Path(marker).parent.mkdir(parents=True,exist_ok=True)
        Path(marker).write_text('explicit fictional I/O fault after receipt',encoding='utf-8')
        raise OSError('SYNTHETIC_REVIEW_INTERRUPTION_AFTER_RECEIPT')
    return original(path,value)
owner.write_atomic_json=interrupted
sys.argv=[script,*args]
owner.main()
'''
    def controlled_run(configuration, command, **kwargs):
        if len(command) > 2 and Path(command[1]).name == "customer_fact_review_v1.py" and "--review" in command:
            request = json.loads(Path(command[command.index("--review") + 1]).read_text(encoding="utf-8"))
            intake = configuration.pipeline_root / "data/customer_intakes" / request["business_id"] / request["intake_id"] / "customer_intake_v1.json"
            if "[E2_UX_REVIEW_INTERRUPT_ONCE]" in intake.read_text(encoding="utf-8"):
                marker = root / "fixture-checkpoints" / request["business_id"] / "review-interrupted-once"
                command = [command[0], "-X", "utf8", "-c", code, command[1], str(marker), *command[2:]]
        return run(configuration, command, **kwargs)
    customer_gateway._run_json_command = controlled_run


# The only simulated boundary is remote extraction. All artifacts are generated
# by the existing canonical validators from saved source + safe projection.
EXTRACT_CODE = inspect.getsource(structured_form_outputs) + r"""
import json,sys,runpy,socket,copy,hashlib
from pathlib import Path
root,repo,kind,request_path=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4])
def denied(*args,**kwargs): raise AssertionError('Remote Model Calls=0; offline provider boundary')
socket.socket.connect=denied
socket.create_connection=denied
socket.getaddrinfo=denied
sys.path.insert(0,str(root/'scripts'))
request=json.loads(request_path.read_text(encoding='utf-8'))
fixture=json.loads((repo/'internal-console/tests/fixtures/customer_speaker_e2/synthetic_outputs.json').read_text(encoding='utf-8'))
def legacy_literal_fixture(text):
    # Preserve one previously verified fictional form, with DOB already hidden.
    # No arbitrary customer form is treated as understood by a fixed extractor.
    return hashlib.sha256(text.encode()).hexdigest()=='f1d774b43c3c26c1263dd33a7ef41ab71a5b19176799b2c1decda2b289e2a43b'
def golden(text,mode):
    if mode=='speaker':
        if all(f['evidence_quote'] in text for f in fixture['speaker']['facts']):
            return copy.deepcopy(fixture['speaker'])
        return None
    if fixture['marker'] not in text: return None
    required=[f['evidence_quote'] for f in fixture['business']['facts']]+[c['evidence_quote'] for c in fixture['business']['constraints'] if not ('[E2_UX_NORMAL]' in text and c['constraint_type']=='identity_conflict')]
    if '[E2_UX_NORMAL]' in text and any(c['evidence_quote'] in text for c in fixture['business']['constraints'] if c['constraint_type']=='identity_conflict'):
        raise RuntimeError('UNSUPPORTED_OFFLINE_FIXTURE: normal fixture cannot conceal identity conflict')
    if not all(q in text for q in required): raise RuntimeError('UNSUPPORTED_OFFLINE_FIXTURE: incomplete Golden source')
    result=copy.deepcopy(fixture[mode])
    if '[E2_UX_NORMAL]' in text and mode=='business':
        result['constraints']=[c for c in result['constraints'] if c['constraint_type']!='identity_conflict']
        for constraint in result['constraints']:
            if constraint['constraint_type']=='conditional_fact': constraint['blocked_terms']=['具体服务']
        extras=[('customer_use_case','周边商圈的同事安排商务聚餐，希望菜单份量清楚，交流环境适合谈话。'),
            ('customer_pain','有忌口的客人会先询问是否可以调整，餐厅确认后再安排。')]
        if not all(quote in text for _,quote in extras): raise RuntimeError('UNSUPPORTED_OFFLINE_FIXTURE: missing UX Golden source')
        result['facts'] += [{'topic':topic,'value':[quote],'evidence_quote':quote} for topic,quote in extras]
    if mode=='business' and '[SYNTHETIC_HISTORICAL_OMISSION]' in text and (request.get('source_lineage')or{}).get('operation')!='saved_source_recovery':
        result['facts']=[];result['constraints']=[]
    if mode=='discovery' and '[SYNTHETIC_NO_TYPE]' in text:
        result['speaker_candidates'][0]['speaker_type_hint']=None
    return result
if kind=='speaker_analysis':
    import speaker_onboarding_analysis_v1 as speaker
    def personal(privacy):
        text=privacy['projection']['materials_safe_semantic']
        fixed=golden(text,'speaker')
        if fixed is not None: return fixed
        structured=structured_form_outputs(text)['personal_facts']
        if structured and '我亲自设计过菜单。' in text:
            return {'facts':structured,'model':'synthetic-literal-legacy-fixture','usage':{}}
        quote='亲自接待和洗护' if '亲自接待和洗护' in text else '亲自洗护'
        facts=[] if quote not in text else [
            {'topic':'speaker_practice','value':[quote],'evidence_quote':quote},
            {'topic':'speaker_allowed_topics','value':['本人参与的接待与洗护经验' if '接待' in quote else '本人参与的洗护经验'],'evidence_quote':quote},
            {'topic':'speaker_scope','value':['只讲本人实际参与的服务，不转用公司或他人经历'],'evidence_quote':quote}]
        if not facts: raise RuntimeError('UNSUPPORTED_OFFLINE_FIXTURE: no real AI was invoked')
        return {'facts':facts,'model':'synthetic-offline','usage':{}}
    speaker.analyze_speaker_onboarding(request=request,pipeline_root=root,extractor=personal)
else:
    import customer_onboarding_analysis_v1 as m
    def discover(privacy):
        text=privacy['projection']['materials_safe_semantic']
        if '[人物发现失败]' in text and kind!='discovery_retry':
            raise RuntimeError('synthetic person discovery failure')
        fixed=golden(text,'discovery')
        if fixed is not None: return fixed
        form=structured_form_outputs(text)
        if legacy_literal_fixture(text):
            return {'model':'synthetic-literal-legacy-fixture','speaker_candidates':form['speaker_candidates']}
        quotes=[quote for quote in ['负责人小林亲自洗护并愿意出镜','王琳是店主，亲自接待和洗护并愿意出镜'] if quote in text]
        return {'model':'synthetic-offline','speaker_candidates':[{'name':None if '[身份缺失]' in text else ('小林' if '小林' in quote else '王琳'), 'public_role':'店主','speaker_type_hint':'owner_founder','candidate_status':'explicit_speaker','evidence_quotes':[quote], 'personal_material_quotes':[quote],'explicit_forbidden_claims':[]} for quote in quotes]}
    if kind=='discovery_retry':
        m.retry_speaker_discovery(request_path=request_path,pipeline_root=root,extractor=discover)
    else:
        def extract(privacy):
            text=privacy['projection']['materials_safe_semantic']
            fixed=golden(text,'business')
            if fixed is not None: return fixed
            form=structured_form_outputs(text)
            if legacy_literal_fixture(text):
                return {'model':'synthetic-literal-legacy-fixture','facts':form['facts']}
            options=[('primary_service',['宠物洗护'],'提供宠物洗护'),('core_audience',['附近养宠家庭'],'服务附近养宠家庭'),('service_process',['先检查毛发再洗护'],'先检查毛发再洗护'),('service_process',['先预约，再进行真实皮肤检测'],'先预约，再进行真实皮肤检测'),('industry','本地生活','宠物洗护')]
            facts=[{'topic':t,'value':v,'evidence_quote':q} for t,v,q in options if q in text]
            if not facts:
                raise RuntimeError('UNSUPPORTED_OFFLINE_FIXTURE: no real AI was invoked')
            return {'model':'synthetic-offline','facts':facts}
        m.analyze_customer_onboarding(request=request,pipeline_root=root,extractor=extract,speaker_discovery_extractor=discover)
"""


def driver(settings, stop, delay, root):
    customer_runner, speaker_runner = CustomerTaskRunner(settings), SpeakerTaskRunner(
        settings
    )
    events = root / "task-events.jsonl"

    def record(task, event):
        with events.open("a", encoding="utf-8") as output:
            output.write(
                json.dumps(
                    {
                        "time": time.time(),
                        "task_id": task["task_id"],
                        "subject": task["subject_ref"],
                        "event": event,
                    }
                )
                + "\n"
            )

    try:
        while not stop.wait(0.3):
            for kind, runner in [
                ("customer_analysis", customer_runner),
                ("speaker_analysis", speaker_runner),
            ]:
                recovered = recover_expired_tasks(
                    settings.database_path,
                    task_types=(kind,),
                    reconciler=runner._reconcile_business_state,
                )
                for task_id in recovered:
                    record(get_task(settings.database_path, task_id), "lease_recovered")
            tasks = list(
                iter_queued_tasks(
                    settings.database_path,
                    task_types=("customer_analysis", "speaker_analysis"),
                )
            )
            if not tasks:
                continue
            task = tasks[0]
            if not claim_task(
                settings.database_path,
                task["task_id"],
                worker_id="isolated-synthetic-extraction",
                lease_seconds=10,
                stage="读取已保存资料",
                task_type=task["task_type"],
            ):
                continue
            record(task, "claimed")
            payload = task["payload"]
            source = Path(
                payload.get("discovery_retry_request") or payload["request_path"]
            )
            request = json.loads(
                Path(payload["request_path"]).read_text(encoding="utf-8")
            )
            checkpoint = (
                root
                / "fixture-checkpoints"
                / str(task["subject_ref"])
                / str(payload["intake_id"])
            )
            checkpoint.mkdir(parents=True, exist_ok=True)
            if (
                "SYNTHETIC_FAIL_ONCE" in str(request.get("materials", ""))
                and not (checkpoint / "failed-once").exists()
            ):
                (checkpoint / "failed-once").write_text("synthetic", encoding="utf-8")
                update_task(
                    settings.database_path,
                    task["task_id"],
                    status="failed",
                    stage="分析未完成",
                    error_code="SYNTHETIC_OFFLINE_FAILURE",
                    error_message="隔离验收：合成的可恢复分析失败。",
                )
                record(task, "synthetic_failure")
                continue
            for stage in (
                ["正在整理客户业务信息", "正在查找可能的出镜人"]
                if task["task_type"] == "customer_analysis"
                else ["整理本人经历与职责", "检查第一人称表达范围"]
            ):
                update_task(
                    settings.database_path,
                    task["task_id"],
                    status="running",
                    stage=stage,
                    worker_id="isolated-synthetic-extraction",
                    lease_seconds=10,
                    heartbeat_interval_seconds=1,
                )
                if stop.wait(delay):
                    return
            kind = (
                "discovery_retry"
                if payload.get("discovery_retry_request")
                else task["task_type"]
            )
            result = subprocess.run(
                [
                    settings.pipeline_python_executable,
                    "-X",
                    "utf8",
                    "-c",
                    EXTRACT_CODE,
                    str(settings.pipeline_root),
                    str(settings.repo_root),
                    kind,
                    str(source),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=40,
            )
            (root / "driver-last.log").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
            if result.returncode:
                update_task(
                    settings.database_path,
                    task["task_id"],
                    status="failed",
                    stage="分析未完成",
                    error_code="SYNTHETIC_DRIVER_ERROR",
                    error_message=("隔离模拟暂不支持这类资料，尚未运行真实 AI 分析。"
                        if "UNSUPPORTED_OFFLINE_FIXTURE" in result.stderr
                        else "隔离验收分析未完成，请检查夹具日志。"),
                )
                record(task, "driver_failed")
                continue
            if "SYNTHETIC_INTERRUPT_AFTER_ARTIFACTS" in str(
                request.get("materials", "")
            ):
                (checkpoint / "artifacts-persisted-before-interrupt").write_text(
                    task["task_id"], encoding="utf-8"
                )
                record(task, "artifacts_persisted_before_interrupt")
                while not stop.wait(0.3):
                    pass
                return
            update_task(
                settings.database_path,
                task["task_id"],
                status="completed" if kind == "discovery_retry" else "awaiting_review",
                progress=100,
                stage="人物发现完成" if kind == "discovery_retry" else "等待人工确认",
            )
            record(
                task, "completed" if kind == "discovery_retry" else "awaiting_review"
            )
    finally:
        customer_runner.close()
        speaker_runner.close()


def main():
    for key in list(os.environ):
        if key.startswith(("AIVO_", "QYAPI_", "DEEPSEEK_", "OPENAI_")):
            os.environ.pop(key)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18010)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--navigation-fixture", action="store_true", help="Stage fictional pre-existing creation references, only in a new root")
    parser.add_argument("--stage-delay", type=float, default=3)
    args = parser.parse_args()
    root = args.workdir.resolve()
    repo = Path(__file__).resolve().parents[2]
    project = repo.parent.parent if repo.parent.name == ".worktrees" else repo
    if not any(root.is_relative_to(project / folder) for folder in (".local", ".verify")) or args.port == 8000:
        parser.error("Use isolated project-local .local/.verify root and a non-production port.")
    manifest = root / "browser_manifest.json"
    if args.resume:
        if args.navigation_fixture:
            parser.error("Navigation reference fixtures may only initialize a new isolated root")
        if (
            not manifest.is_file()
            or not json.loads(manifest.read_text())["fixture_only"]
        ):
            parser.error("Not an isolated fixture root")
        settings = Settings(
            repo_root=repo,
            console_root=repo / "internal-console",
            pipeline_root=root / "ops-pipeline",
            database_path=root / "console.sqlite3",
            python_executable=sys.executable,
            case_analysis_worker_enabled=False,
            customer_analysis_worker_enabled=False,
            speaker_analysis_worker_enabled=False,
            background_worker_enabled=False,
        )
    else:
        if root.exists():
            parser.error("Use new root or --resume")
        root.mkdir(parents=True)
        settings = fixture_settings.__wrapped__(root)
        shutil.copy2(
            repo / "ops-pipeline/speaker_prompt.md",
            settings.pipeline_root / "speaker_prompt.md",
        )
        if args.navigation_fixture:
            shutil.copytree(repo / "internal-console/tests/fixtures/customer_navigation_v1/data", settings.pipeline_root / "data", dirs_exist_ok=True)
    settings = replace(
        settings,
        pipeline_python_executable=str(repo / "ops-pipeline/.venv/Scripts/python.exe"),
        session_cookie_name=f"aivo_cs_intake_fixture_{args.port}",
        default_business_id=None,
        background_worker_enabled=False,
    )
    if not args.resume:
        with TestClient(build_app(settings)) as client:
            for phone in PHONES:
                provision_user(settings.database_path, phone)
                login = client.post(
                    "/api/auth/login", json={"phone": phone, "password": "123456"}
                ).json()
                changed = client.post(
                    "/api/auth/change-password",
                    headers={"X-CSRF-Token": login["csrf_token"]},
                    json={
                        "current_password": "123456",
                        "new_password": PASSWORD,
                        "confirm_password": PASSWORD,
                    },
                )
                assert changed.status_code == 200
        manifest.write_text(
            json.dumps(
                {
                    "fixture_only": True,
                    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                    "current_worktree": str(repo),
                    "url": f"http://127.0.0.1:{args.port}",
                    "accounts": PHONES,
                    "database": str(settings.database_path),
                    "model_boundary": "synthetic outputs only; no external calls",
                    "navigation_reference_fixture": args.navigation_fixture,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    application = build_app(settings)
    inject_review_interruption(settings, root)
    add_fixture_notice(application)
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host="127.0.0.1",
            port=args.port,
            workers=1,
            access_log=False,
            log_level="warning",
        )
    )
    stop = threading.Event()

    def run_driver():
        while not server.started and not stop.wait(0.1):
            pass
        if not stop.is_set():
            driver(settings, stop, args.stage_delay, root)

    thread = threading.Thread(target=run_driver, daemon=True)
    thread.start()
    print(
        json.dumps(
            {
                "fixture_only": True,
                "url": f"http://127.0.0.1:{args.port}",
                "root": str(root),
            }
        ),
        flush=True,
    )
    try:
        server.run()
    finally:
        stop.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
