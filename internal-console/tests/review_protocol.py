"""HTTP workflow tests use the same read-before-submit protocol as the browser.

Tests for absent/forged/stale context use client.request directly or provide an
explicit context. This helper never grants a role or modifies an assertion.
"""
def post_review(client, url, **kwargs):
    payload = dict(kwargs.get("json") or {})
    if "review_context" not in payload:
        detail_url = str(url).rsplit("/", 2)[0] if str(url).endswith(("/persona/approve", "/facts/review")) else str(url).rsplit("/", 1)[0]
        response = client.get(detail_url)
        key = "review_context" if str(url).endswith("/facts/review") and "/speakers/" not in str(url) else "approval_context"
        context = response.json().get(key) if response.status_code == 200 else None
        if context:
            payload["review_context"] = context["token"]
    # This helper models the final human confirmation. Negative API tests call
    # client.post directly so absent/AI/default quality decisions remain absent.
    if payload.get("decision") == "approve" and "quality_decision" not in payload:
        current = client.get(str(url).rsplit("/", 1)[0])
        context = current.json().get("quality_context") if current.status_code == 200 else None
        if context:
            payload["quality_decision"] = {**context, "decision": "suitable", "origin": "human_final_confirmation"}
    return client.post(url, **{**kwargs, "json": payload})


def historical_case_context(client, detail):
    """Explicit frozen v1.0 fixture, not an HTTP fallback when v1.1 fails.

    Legacy evidence fixtures intentionally lack the new source graph. Encode an
    actual old-version context using its original snapshot/signature contract;
    all real authorization, freshness, Approval and recovery Gates still run.
    Production has no endpoint that issues this historical context.
    """
    import base64
    import hmac
    import json
    from app import review_commands
    context = json.loads(base64.urlsafe_b64decode(detail['approval_context']['token'].split('.')[0]))
    context['version'] = review_commands.VERSION
    context['snapshot'] = review_commands.snapshot(client.app.state.settings, 'case', detail['case_id'], version=review_commands.VERSION)
    body = base64.urlsafe_b64encode(json.dumps(context, sort_keys=True).encode()).decode()
    return body + '.' + hmac.new(review_commands._KEY, body.encode(), 'sha256').hexdigest()


def frozen_v11_context(token):
    """Explicit pre-share compatibility fixture; no production issuer does this.

    Preserve the original UX1 Coverage/recovery tests without reinterpreting their
    frozen approvals as new display decisions. Source graph and scope are exact.
    """
    import base64, hmac, json
    from app import review_commands
    value=json.loads(base64.urlsafe_b64decode(token.split('.')[0]))
    value['version']=review_commands.CASE_VERSION
    value.pop('sharing',None)
    for key in ('sharing_mode','share_preview_sha256','share_blocker_sha256','reviewer_grant_ref'):
        value['snapshot'].pop(key,None)
    body=base64.urlsafe_b64encode(json.dumps(value,sort_keys=True).encode()).decode()
    return body+'.'+hmac.new(review_commands._KEY,body.encode(),'sha256').hexdigest()


def post_historical_case_review(client, url, **kwargs):
    """Only callers with explicitly frozen legacy fixtures opt into this path."""
    payload = dict(kwargs.get('json') or {})
    if 'review_context' not in payload:
        response = client.get(str(url).rsplit('/', 1)[0])
        if response.status_code == 200 and response.json().get('approval_context'):
            payload['review_context'] = historical_case_context(client, response.json())
    return post_review(client, url, **{**kwargs, 'json': payload})


def case_command_fixture(settings, case_id, *, task=None):
    """Bound candidate for unit tests that explicitly stub the Approval owner."""
    import json
    from app.task_service import create_case_task, update_task
    from app import review_commands
    existing = task is not None
    task = task or create_case_task(settings.database_path, source_url=f"https://www.douyin.com/video/{case_id}",
        case_id=case_id, operator_profile_hint="mix", created_by_user_id=1)
    if not existing:
        update_task(settings.database_path,task["task_id"],status="awaiting_review",progress=99,stage="Synthetic candidate awaiting review")
    directory = settings.pipeline_root / "data/case_analysis_attempts" / case_id / task["task_id"]
    path = directory / "candidate_cases" / case_id / "case_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"case_id":case_id,"lifecycle":{"status":"review_required","approved":False},
        "identity":{"platform":"douyin","source_url":f"https://www.douyin.com/video/{case_id}","industry":"待分类"},
        "analysis_lineage":{"attempt_id":task["task_id"]}}),encoding="utf-8")
    (directory/"case_analysis_attempt_v1.json").write_text(json.dumps({"case_id":case_id,"attempt_id":task["task_id"],
        "status":"awaiting_review","artifacts":{"case_candidate_v1":str(path)}}),encoding="utf-8")
    return review_commands.issue(settings,"case",case_id,1)["token"]
