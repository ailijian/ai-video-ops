"""All-fictional native Case -> Pattern -> Compatibility preparation.

Only acquisition/ASR/vision provider transports are synthetic. No approval,
Pattern, Compatibility, release validator, or database result is mocked.
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from app.case_library_access import principal
from app.profile_compatibility_gateway import manage_reviewer
from app.task_service import update_task
from approve_pattern_v1 import APPROVABLE_PATTERN_ID, approve_pattern
from compare_approved_cases_v1 import build_comparison
from mine_pattern_candidates_v1 import build_pattern_research
from production_profile_v1 import bootstrap_mix_profile_v1_1
from profile_compatibility_decisions_v1_1 import prepare_target, write_once, target_id
from test_case_share_joint_v1 import payload
from customer_onboarding_analysis_v1 import analyze_customer_onboarding


def prepare_native_golden(node):
    settings, accounts, storage = node
    project = Path(__file__).resolve().parents[2]
    python = project / 'ops-pipeline/.venv/Scripts/python.exe'
    environment = {k: v for k, v in os.environ.items() if not k.startswith(('DEEPSEEK_', 'QYAPI_', 'AIVO_'))}
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    case_paths, fps, receipts, steps = [], [], [], []
    ids = ['7999999999999999821', '7999999999999999822', '7999999999999999823']
    for index, case_id in enumerate(ids):
        submitter, headers, _ = accounts['A']
        response = submitter.post('/api/case-intake/groups', headers=headers, json={
            'client_request_id': str(uuid.uuid4()), 'text': f'https://www.douyin.com/video/{case_id}'})
        assert response.status_code == 200, response.text
        task = response.json()['items'][0]['task']
        result = subprocess.run([str(python), str(project / 'ops-pipeline/tests/case_review_synthetic.py'),
            'compat-prepare', str(settings.pipeline_root), case_id, task['task_id'],
            'food' if index < 2 else 'plant_service'], capture_output=True, text=True, encoding='utf-8',
            env=environment, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        update_task(settings.database_path, task['task_id'], status='awaiting_review', progress=100)
        url = f'/api/cases/{case_id}'
        context = submitter.get(url + '/classification').json()
        result = submitter.post(url + '/classification', headers=headers, json={
            'industry': '餐饮' if index < 2 else '本地生活', 'profile': 'mix',
            'candidate_sha256': context['candidate_sha256'],
            'expected_confirmation_sha256': context['confirmation_sha256']})
        assert result.status_code == 200, result.text
        reviewer, reviewer_headers, _ = accounts['C']
        detail = reviewer.get(url).json()
        result = reviewer.post(url + '/review', headers=reviewer_headers, json=payload(detail))
        assert result.status_code == 200, result.text
        case_path = settings.pipeline_root / 'data/cases' / case_id / 'case_v1.json'
        receipt = case_path.with_name('approval_receipt.json')
        assert receipt.is_file() and not case_path.with_name('case_profile_compatibility_approval_v1.json').exists()
        result = subprocess.run([str(python), str(settings.pipeline_root / 'scripts/build_case_fingerprint_v1.py'),
            '--case', str(case_path), '--output-root', str(settings.pipeline_root / 'data/fingerprints')],
            capture_output=True, text=True, encoding='utf-8', env=environment, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        fp = settings.pipeline_root / 'data/fingerprints' / case_id / 'case_fingerprint_v1.json'
        assert json.loads(fp.read_text('utf-8'))['narration_features']['speech_to_video_ratio'] >= .5
        case_paths.append(case_path)
        fps.append(fp)
        receipts.append(receipt)
        steps.append({'case_id': case_id, 'task_id': task['task_id'], 'approval': str(receipt)})
    comparison = build_comparison(case_paths[:2], fps[:2])
    comparison_path = settings.pipeline_root / 'data/cross_case_research/compat_golden/comparison.json'
    write_once(comparison_path, comparison)
    research, candidates = build_pattern_research(case_paths, fps, comparison_path)
    research_path = settings.pipeline_root / 'data/pattern_research/compat_golden/research.json'
    write_once(research_path, research)
    selected = next(v for v in candidates if v['pattern_id'] == APPROVABLE_PATTERN_ID)
    candidate_path = settings.pipeline_root / 'data/patterns/candidates' / APPROVABLE_PATTERN_ID / 'pattern_candidate_v1.json'
    write_once(candidate_path, selected)
    pattern_path, pattern_receipt, _, _ = approve_pattern(candidate_path, research_path,
        settings.pipeline_root / 'data/patterns/approved', reviewer='13900000003',
        note='Explicit native review of three all-fictional food/plant process sources only')
    definitions = bootstrap_mix_profile_v1_1(settings.pipeline_root,
        project / 'ops-pipeline/output/素材混剪&数字人口播混剪文案导入模板.xlsx')
    targets = [prepare_target(settings.pipeline_root, case_id=c, pattern_id=APPROVABLE_PATTERN_ID, **definitions) for c in ids]
    reviewer, headers, _ = accounts['C']
    actor = principal(settings, 3)
    operation = uuid.uuid4().hex
    body = {'operation_id': operation, 'decisions': [
        {'target_id': target_id(t), 'target': t, 'action': 'approve', 'parent': None,
         'withdraws': None, 'reason': 'Explicit Mix compatibility review of exact fictional native sources'} for t in targets]}
    assert reviewer.post('/api/profile-compatibility/preview', headers=headers, json=body).status_code == 409
    manage_reviewer(settings, 3, action='grant', operator='isolated-founder-fixture', reason='Independent native Compatibility reviewer for all-fictional validation')
    preview = reviewer.post('/api/profile-compatibility/preview', headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    response = reviewer.post('/api/profile-compatibility/confirm', headers=headers, json={
        'operation_id': operation, 'preview_sha256': preview.json()['preview_ref']['sha256']})
    assert response.status_code == 200, response.text
    return {'case_steps': steps, 'pattern_path': pattern_path, 'pattern_receipt': pattern_receipt,
            'targets': targets, 'compatibility': response.json(), 'actor': actor}


def prepare_native_business(node, *, customer_name='明禾餐食（全虚构 Golden）'):
    """Independent owner-provided facts; no Case fact/claim feeds the Persona."""
    from test_customer_speaker_smart_intake_v1 import review_payload
    from test_customer_speaker_joint_confirmation import preview, submit
    from speaker_review_preparation_v1 import prepare as prepare_people
    from app.task_service import get_task
    from app.persona_authority import resolve_persona_authority
    settings, accounts, _ = node
    client, headers, _ = accounts['A']
    facts = [
        ('primary_service', ['供应按单制作的蔬菜餐食'], '供应按单制作的蔬菜餐食'),
        ('core_audience', ['附近需要午餐的住户'], '服务附近需要午餐的住户'),
        ('customer_use_case', ['工作日午间自取'], '工作日午间自取'),
        ('customer_pain', ['希望提前说明忌口'], '顾客希望提前说明忌口'),
        ('differentiator', ['下单时单独核对忌口'], '下单时单独核对忌口'),
        ('service_process', ['先核对忌口，再按单配菜，制作后标记餐盒'], '先核对忌口，再按单配菜，制作后标记餐盒'),
        ('founder_story', ['负责人小周亲自负责核对订单'], '负责人小周亲自负责核对订单并愿意出镜'),
    ]
    material = '。'.join(quote for _, _, quote in facts) + '。本资料和客户完全虚构，仅用于隔离验收。'
    response = client.post('/api/customers/analyze', headers=headers, json={
        'customer_name': customer_name, 'industry': '餐饮', 'materials': material})
    assert response.status_code == 200, response.text
    body = response.json()
    import shutil
    project = Path(__file__).resolve().parents[2]
    shutil.copyfile(project / 'ops-pipeline/speaker_prompt.md', settings.pipeline_root / 'speaker_prompt.md')
    request_path = Path(body['task']['payload']['request_path'])
    analyze_customer_onboarding(request=json.loads(request_path.read_text('utf-8')), pipeline_root=settings.pipeline_root,
        extractor=lambda _: {'facts': [{'topic': t, 'value': v, 'evidence_quote': q} for t, v, q in facts], 'model': 'synthetic-external-boundary'},
        speaker_discovery_extractor=lambda _: {'model': 'synthetic-external-boundary', 'speaker_candidates': [
            {'name': '小周', 'public_role': '订单核对负责人', 'speaker_type_hint': 'frontline_expert',
             'candidate_status': 'explicit_speaker',
             'evidence_quotes': ['负责人小周亲自负责核对订单并愿意出镜'],
             'personal_material_quotes': ['负责人小周亲自负责核对订单并愿意出镜'], 'explicit_forbidden_claims': []}]})
    update_task(settings.database_path, body['task']['task_id'], status='awaiting_review', progress=99)
    bid = body['business_id']
    detail = client.get(f'/api/customers/{bid}').json()
    decision = review_payload(detail)
    decision['speaker_confirmations'][0].update(speaker_name='小周', public_role='订单核对负责人')
    csrf = headers['X-CSRF-Token']
    decision['joint_speaker_review'] = True
    preparation = client.post(f'/api/customers/{bid}/review-preparation', headers=headers, json=decision)
    assert preparation.status_code == 200, preparation.text
    task = get_task(settings.database_path, preparation.json()['task']['task_id'])
    prepared = Path(task['payload']['speaker_preparation_request'])
    def person_extract(privacy):
        quote = privacy['projection']['materials_safe_semantic']
        return {'facts': [
            {'topic': 'speaker_practice', 'value': ['本人亲自负责核对订单'], 'evidence_quote': quote},
            {'topic': 'speaker_allowed_topics', 'value': ['本人核对订单的职责'], 'evidence_quote': quote}]}
    prepare_people(pipeline_root=settings.pipeline_root, request_path=prepared, extractor=person_extract)
    checked = client.post(f'/api/customers/{bid}/review-preparation', headers=headers, json=decision)
    assert checked.status_code == 200, checked.text
    status = checked.json()
    decision['speaker_fact_decisions'] = [{'candidate_id': p['candidate_id'], 'decisions': [
        {'candidate_id': f['candidate_id'], 'decision': 'approve'} for f in p['facts']]} for p in status['people']]
    bundle = preview(client, bid, csrf, decision)
    result = submit(client, bid, csrf, bundle)
    assert result.status_code == 200, result.text
    sid = status['people'][0]['speaker_id']
    assert resolve_persona_authority(settings, bid, 'business').current
    assert resolve_persona_authority(settings, sid, 'speaker').current
    return {'business_id': bid, 'speaker_id': sid, 'client': client, 'headers': headers}
