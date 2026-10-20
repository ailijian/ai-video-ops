"""Disposable unit fixtures, not v1.2 qualification or Human Authority evidence."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3


def context(root: Path, user_id=1):
    from generation_recovery_v1 import authorization
    path = root / 'unit-session.sqlite3'
    token_hash = str(user_id) * 64
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS console_principal_namespace(singleton INTEGER, namespace TEXT);
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,status TEXT,must_change_password INTEGER,updated_at TEXT);
            CREATE TABLE IF NOT EXISTS sessions(user_id INTEGER,token_hash TEXT,expires_at TEXT);
        ''')
        if not db.execute('SELECT * FROM console_principal_namespace').fetchone():
            db.execute('INSERT INTO console_principal_namespace VALUES(1,?)', ('a'*32,))
        if not db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone():
            db.execute('INSERT INTO users VALUES(?,?,?,?)', (user_id,'active',0,'2026-10-20T00:00:00+00:00'))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (user_id,token_hash,
                (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
    actor = {'namespace': 'a'*32, 'user_id': user_id}
    return {'actor': actor, 'authorization': authorization(path, actor, hashlib.sha256(token_hash.encode()).hexdigest())}


def generate(*, pipeline_root, request_id, **kwargs):
    """Unit fixture still passes real local principal/session admission."""
    import novel_news_v1 as novel
    auth = context(pipeline_root)
    attempt = novel.prepare_novel_news_generation(pipeline_root=pipeline_root, request_id=request_id,
        authorization_context=auth)
    return novel.generate_novel_news_plan(pipeline_root=pipeline_root, request_id=request_id,
        authorization_context=auth, operation_id=attempt['operation_id'], intent_sha256=attempt['sha256'], **kwargs)


def prepare(tmp_path, kind):
    import test_novel_news_v1 as novel_fixture
    import test_news_delivery_v1 as repurpose_fixture
    import novel_news_v1 as novel
    import news_delivery_v1 as repurpose
    if kind == 'novel':
        root, rid, beats = novel_fixture.fixture(tmp_path)
        generate(pipeline_root=root, request_id=rid,
            transport=lambda prompt: {'payload': {'beats': beats}, 'response_sha256': 'synthetic-offline'})
        novel.review_novel_news_plan(pipeline_root=root, request_id=rid, reviewer='unit human decision',
            decisions=[{'beat_id':f'B{i:03d}', 'decision':'approved'} for i in range(1,5)])
        paths = novel._paths(root, rid)
        directory = paths['approved'].parent
        receipt, closure = paths['receipt'], paths['closure']
        def export(auth): return novel.export_novel_news(pipeline_root=root, request_id=rid, export_context=auth)
        def status(): return novel.novel_news_status(pipeline_root=root, request_id=rid)
        owner = novel
    else:
        f = repurpose_fixture.build_fixture(tmp_path)
        root = f['pipeline']
        request, _ = repurpose.create_news_delivery_request(pipeline_root=root, business_id=f['business_id'],
            speaker_id=f['speaker_id'], source_content_id=f['source_content_id'], idempotency_key='nr-test')
        rid = request['request_id']
        plan,_ = repurpose.resolve_news_delivery_plan(pipeline_root=root, request_id=rid)
        repurpose.approve_news_delivery(pipeline_root=root, request_id=rid,
            review_path=repurpose_fixture.build_review(tmp_path,plan))
        directory = repurpose._request_root(root,rid)
        receipt = directory / 'news_dynamic_excel_export_receipt_v1.json'
        closure = directory / 'news_delivery_export_closure_v1.json'
        def export(auth): return repurpose.export_news_delivery(pipeline_root=root, request_id=rid, export_context=auth)
        def status(): return repurpose.status_news_delivery(pipeline_root=root, request_id=rid)
        owner = repurpose
    return {'root':root,'rid':rid,'directory':directory,'receipt':receipt,'closure':closure,
        'export':export,'status':status,'owner':owner,'context':context(root), 'kind':kind}
