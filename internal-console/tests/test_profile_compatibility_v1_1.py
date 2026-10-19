"""Native Compatibility component/HTTP checks, not the end-to-end Golden."""
import copy
import json
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

import pytest

from conftest import login_and_change_password
from app.case_library_access import principal
from app.profile_compatibility_gateway import manage_reviewer
from approve_pattern_v1 import APPROVABLE_PATTERN_ID, approve_pattern
from production_profile_v1 import bootstrap_mix_profile_v1_1
from profile_compatibility_contract_v1_1 import CompatibilityError
from profile_compatibility_decisions_v1_1 import (
    DOMAIN, decide, decision_graph, file_sha, prepare_target, preview, read, ref,
    target_id, write_once,
)


def inputs(root):
    """Minimal isolated source fixtures; native Pattern/Compatibility writers."""
    case_ids = ['7999999999999999811', '7999999999999999812', '7999999999999999813']
    hashes, fp_hashes = {}, {}
    for case_id in case_ids:
        directory = root / 'data/cases' / case_id
        storyboard = directory / 'storyboard_v1.json'
        storyboard_sha = write_once(storyboard, {'case_id': case_id})
        case = {'case_id': case_id, 'lifecycle': {'status': 'approved', 'approved': True},
                'validation': {'passed': True}, 'storyboard': {'artifact': {'path': str(storyboard), 'sha256': storyboard_sha}}}
        hashes[case_id] = write_once(directory / 'case_v1.json', case)
        write_once(directory / 'approval_receipt.json', {'case_id': case_id, 'human_gate': True,
            'decision': 'approved', 'case_sha256_after_approval': hashes[case_id],
            'frozen_artifacts': {'reverse_storyboard_v1': {'path': str(storyboard), 'sha256': storyboard_sha}}})
        fp = {'case_id': case_id, 'source_case': {'sha256': hashes[case_id], 'status': 'approved', 'approved': True},
              'narration_features': {'speech_to_video_ratio': .8},
              'visual_shot_features': {'shot_count': 6},
              'audio_visual_features': {'narration_and_shots_are_separate_tracks': True,
                                       'shot_to_narration_cardinality': 'many_to_many'},
              'provenance': {'storyboard_sha256': storyboard_sha},
              'pattern_mining_contract': {'this_artifact_is_not_a_pattern': True}}
        fp_hashes[case_id] = write_once(root / 'data/fingerprints' / case_id / 'case_fingerprint_v1.json', fp)
    research = {'validation': {'passed': True}, 'authority': {'remote_model_used': False},
                'case_ids': case_ids, 'pattern_candidate_ids': [APPROVABLE_PATTERN_ID],
                'case_sources': [{'case_id': c, 'fingerprint_sha': fp_hashes[c]} for c in case_ids]}
    candidate = {'pattern_id': APPROVABLE_PATTERN_ID, 'status': 'candidate',
                 'authority': {'candidate_only': True, 'human_review_required': True},
                 'effectiveness': {'status': 'unvalidated', 'performance_data_used': False},
                 'scope': {'supported_case_ids': case_ids, 'supported_case_count': 3},
                 'lineage': {'fingerprint_sha256': fp_hashes, 'approved_case_sha256': hashes},
                 'evidence': [{'case_id': c} for c in case_ids]}
    cp, rp = root / 'data/research/candidate.json', root / 'data/research/research.json'
    write_once(cp, candidate)
    write_once(rp, research)
    approve_pattern(cp, rp, root / 'data/patterns/approved', 'isolated-pattern-reviewer')
    template = root / 'mix-template.xlsx'
    with zipfile.ZipFile(template, 'w') as archive:
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="4"><c r="A4" t="inlineStr"><is><t>视频制作标题</t></is></c><c r="B4" t="inlineStr"><is><t>视频制作口播内容</t></is></c></row></sheetData></worksheet>')
    definitions = bootstrap_mix_profile_v1_1(root, template)
    return [prepare_target(root, case_id=c, pattern_id=APPROVABLE_PATTERN_ID, **definitions) for c in case_ids]


def request(target, graph=None, action='approve'):
    identity = target_id(target)
    current = (graph or {}).get('heads', {}).get(identity, {})
    return {'target_id': identity, 'target': target, 'action': action,
            'parent': current.get('head'), 'withdraws': current.get('effective') if action == 'withdraw' else None,
            'reason': 'Explicit isolated component Human decision'}


@pytest.fixture
def compat(client, settings):
    csrf = login_and_change_password(client)
    targets = inputs(settings.pipeline_root)
    actor = principal(settings, 1)
    return client, settings, {'X-CSRF-Token': csrf}, actor, targets


def grant(settings):
    return manage_reviewer(settings, 1, action='grant', operator='isolated-maintainer', reason='Explicit independent review capability')


def execute(settings, actor, decisions, operation_id=None):
    operation = operation_id or uuid.uuid4().hex
    value = preview(settings.pipeline_root, settings.database_path, actor, operation, decisions)
    return decide(settings.pipeline_root, settings.database_path, actor, operation, value['preview_ref']['sha256'])


def test_independent_capability_http_auth_csrf_and_native_receipt(compat):
    client, settings, headers, actor, targets = compat
    body = {'operation_id': uuid.uuid4().hex, 'decisions': [request(t) for t in targets]}
    assert client.post('/api/profile-compatibility/preview', json=body).status_code == 403
    # The existing fixture has case_library_reviewer; it does not imply this grant.
    assert client.post('/api/profile-compatibility/preview', headers=headers, json=body).status_code == 409
    grant(settings)
    value = client.post('/api/profile-compatibility/preview', headers=headers, json=body)
    assert value.status_code == 200, value.text
    submitted = {'operation_id': body['operation_id'], 'preview_sha256': value.json()['preview_ref']['sha256']}
    result = client.post('/api/profile-compatibility/confirm', headers=headers, json=submitted)
    assert result.status_code == 200, result.text
    assert result.json()['receipt']['human_gate'] is True
    assert result.json()['receipt']['authorization']['capability'] == 'profile_compatibility_reviewer'
    replay = client.post('/api/profile-compatibility/confirm', headers=headers, json=submitted)
    assert replay.status_code == 200 and replay.json()['receipt_ref'] == result.json()['receipt_ref']
    assert len(list((settings.pipeline_root / DOMAIN / 'decisions').glob('*.json'))) == 1
    client.cookies.clear()
    assert client.post('/api/profile-compatibility/confirm', headers=headers, json=submitted).status_code == 401


def test_batch_omission_reject_and_withdraw_preserve_other_targets(compat):
    _, settings, _, actor, targets = compat
    grant(settings)
    first = execute(settings, actor, [request(t) for t in targets[:2]])
    original = Path(settings.pipeline_root / first['receipt_ref']['path']).read_bytes()
    graph = decision_graph(settings.pipeline_root)
    execute(settings, actor, [request(targets[2])])
    assert len([v for v in decision_graph(settings.pipeline_root)['heads'].values() if v['effective']]) == 3
    execute(settings, actor, [request(targets[0], graph, 'reject')])
    graph = decision_graph(settings.pipeline_root)
    assert graph['heads'][target_id(targets[0])]['effective'] == first['receipt_ref']
    execute(settings, actor, [request(targets[0], graph, 'withdraw')])
    graph = decision_graph(settings.pipeline_root)
    assert graph['heads'][target_id(targets[0])]['effective'] is None
    assert graph['heads'][target_id(targets[1])]['effective'] == first['receipt_ref']
    assert (settings.pipeline_root / first['receipt_ref']['path']).read_bytes() == original
    with pytest.raises(CompatibilityError, match='Old operation'):
        decide(settings.pipeline_root, settings.database_path, actor, first['receipt']['operation_id'], first['receipt']['preview_ref']['sha256'])


@pytest.mark.parametrize('change', ['source', 'case_approval', 'fingerprint', 'storyboard', 'pattern', 'pattern_approval', 'profile', 'rules', 'audit', 'revoke', 'regrant'])
def test_stale_source_or_revoked_regranted_intent_rejected(compat, change):
    _, settings, _, actor, targets = compat
    grant(settings)
    operation = uuid.uuid4().hex
    value = preview(settings.pipeline_root, settings.database_path, actor, operation, [request(targets[0])])
    if change in {'revoke', 'regrant'}:
        manage_reviewer(settings, 1, action='revoke', operator='fixture', reason='Withdraw review permission')
        if change == 'regrant':
            grant(settings)
    else:
        key = ('case' if change == 'source' else change) + '_ref'
        path = settings.pipeline_root / targets[0][key]['path']
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(CompatibilityError):
        decide(settings.pipeline_root, settings.database_path, actor, operation, value['preview_ref']['sha256'])
    assert not list((settings.pipeline_root / DOMAIN / 'decisions').glob('*.json'))


def test_cli_cannot_use_case_grant_or_reviewer_name(compat):
    _, settings, _, actor, targets = compat
    data = settings.pipeline_root / 'decisions.json'
    data.write_text(json.dumps([request(targets[0])]), encoding='utf-8')
    command = [sys.executable, str(settings.repo_root / 'ops-pipeline/scripts/approve_production_profile_compatibility_v1.py'),
               'v1.1', 'preview', '--root', str(settings.pipeline_root), '--database', str(settings.database_path),
               '--namespace', actor['namespace'], '--user-id', '1', '--operation-id', uuid.uuid4().hex, '--decisions-json', str(data)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert not list((settings.pipeline_root / DOMAIN / 'decisions').glob('*.json'))


def test_disabled_or_borrowed_principal_and_conflicting_operation_cannot_decide(compat):
    from app.database import transaction
    client, settings, headers, actor, targets = compat
    grant(settings)
    operation = uuid.uuid4().hex
    first = preview(settings.pipeline_root, settings.database_path, actor, operation, [request(targets[0])])
    with pytest.raises(CompatibilityError, match='conflicts'):
        preview(settings.pipeline_root, settings.database_path, actor, operation, [request(targets[1])])
    borrowed = {**actor, 'namespace': 'f' * 32}
    with pytest.raises(CompatibilityError):
        decide(settings.pipeline_root, settings.database_path, borrowed, operation, first['preview_ref']['sha256'])
    spoof = client.post('/api/profile-compatibility/confirm', headers=headers, json={
        'operation_id': operation, 'preview_sha256': first['preview_ref']['sha256'], 'actor': borrowed})
    assert spoof.status_code == 422
    with transaction(settings.database_path) as db:
        db.execute("UPDATE users SET status='disabled' WHERE id=1")
    with pytest.raises(CompatibilityError, match='not active'):
        decide(settings.pipeline_root, settings.database_path, actor, operation, first['preview_ref']['sha256'])
    assert not list((settings.pipeline_root / DOMAIN / 'decisions').glob('*.json'))


@pytest.mark.parametrize('change', ['outside_scope', 'candidate', 'news'])
def test_original_pattern_scope_and_explicit_mix_target_are_required(compat, change):
    _, settings, _, actor, targets = compat
    grant(settings)
    changed = copy.deepcopy(targets[0])
    if change == 'news':
        changed['target_profile'] = 'news'
    else:
        path = settings.pipeline_root / changed['pattern_ref']['path']
        pattern = read(path)
        if change == 'candidate':
            pattern['status'] = 'candidate'
        else:
            pattern['scope']['supported_case_ids'] = [targets[1]['case_id'], targets[2]['case_id']]
        path.write_text(json.dumps(pattern), encoding='utf-8')
        changed['pattern_ref'] = ref(settings.pipeline_root, path)
        receipt_path = settings.pipeline_root / changed['pattern_approval_ref']['path']
        receipt = read(receipt_path)
        receipt['approved_pattern']['sha256'] = changed['pattern_ref']['sha256']
        receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
        changed['pattern_approval_ref'] = ref(settings.pipeline_root, receipt_path)
    with pytest.raises(CompatibilityError):
        execute(settings, actor, [request(changed)])


def test_pattern_scope_wrong_sha_and_unknown_schema_never_authorize(compat):
    _, settings, _, actor, targets = compat
    grant(settings)
    changed = copy.deepcopy(targets[0])
    changed['pattern_id'] = 'outside_scope'
    with pytest.raises(CompatibilityError, match='Pattern'):
        execute(settings, actor, [request(changed)])
    approved = execute(settings, actor, [request(targets[0])])
    path = settings.pipeline_root / approved['receipt_ref']['path']
    data = read(path)
    data['schema_version'] = 'production-profile-compatibility-approval-v9'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(CompatibilityError, match='Unknown'):
        decision_graph(settings.pipeline_root)


def test_archived_case_cannot_bypass_changed_canonical_source(compat):
    _, settings, _, actor, targets = compat
    grant(settings)
    changed = copy.deepcopy(targets[0])
    original = settings.pipeline_root / changed['case_ref']['path']
    archive = settings.pipeline_root / 'data/archive/old_case.json'
    archive.parent.mkdir(parents=True)
    archive.write_bytes(original.read_bytes())
    changed['case_ref'] = ref(settings.pipeline_root, archive)
    original.write_bytes(original.read_bytes() + b' ')
    with pytest.raises(CompatibilityError, match='canonical Case'):
        execute(settings, actor, [request(changed)])


def test_two_previews_cannot_fork_parent_and_old_intent_cannot_revive_withdrawal(compat):
    _, settings, _, actor, targets = compat
    grant(settings)
    root = settings.pipeline_root
    a, b = uuid.uuid4().hex, uuid.uuid4().hex
    first = preview(root, settings.database_path, actor, a, [request(targets[0])])
    second = preview(root, settings.database_path, actor, b, [request(targets[0])])
    decide(root, settings.database_path, actor, a, first['preview_ref']['sha256'])
    with pytest.raises(CompatibilityError, match='head advanced'):
        decide(root, settings.database_path, actor, b, second['preview_ref']['sha256'])
    execute(settings, actor, [request(targets[0], decision_graph(root), 'withdraw')])
    with pytest.raises(CompatibilityError):
        decide(root, settings.database_path, actor, a, first['preview_ref']['sha256'])
    renewed = execute(settings, actor, [request(targets[0], decision_graph(root))])
    assert decision_graph(root)['heads'][target_id(targets[0])]['effective'] == renewed['receipt_ref']
    assert len(list((root / DOMAIN / 'decisions').glob('*.json'))) == 3


def test_decision_publication_failure_recovers_one_exact_native_receipt(compat, monkeypatch):
    _, settings, _, actor, targets = compat
    grant(settings)
    operation = uuid.uuid4().hex
    root = settings.pipeline_root
    value = preview(root, settings.database_path, actor, operation, [request(targets[0])])
    import profile_compatibility_decisions_v1_1 as owner
    original = owner.write_once
    def interrupted(path, data):
        if path.parent.name == 'decisions':
            raise OSError('Synthetic failure after immutable Human decision intent')
        return original(path, data)
    with monkeypatch.context() as fault:
        fault.setattr(owner, 'write_once', interrupted)
        with pytest.raises(OSError):
            decide(root, settings.database_path, actor, operation, value['preview_ref']['sha256'])
    intent = root / DOMAIN / 'operations' / operation / 'decision_intent.json'
    saved = intent.read_bytes()
    receipt = decide(root, settings.database_path, actor, operation, value['preview_ref']['sha256'])
    assert intent.read_bytes() == saved
    assert receipt['receipt']['decided_at'] == read(intent)['decided_at']
    assert len(list((root / DOMAIN / 'decisions').glob('*.json'))) == 1


def test_missing_parent_and_forked_decision_files_fail_closed(compat):
    _, settings, _, actor, targets = compat
    grant(settings)
    root = settings.pipeline_root
    first = execute(settings, actor, [request(targets[0])])
    second = execute(settings, actor, [request(targets[0], decision_graph(root), 'reject')])
    path = root / first['receipt_ref']['path']
    bytes_before = path.read_bytes()
    path.unlink()  # Isolated corruption probe only, never a revocation mechanism.
    with pytest.raises(CompatibilityError, match='parent missing'):
        decision_graph(root)
    path.write_bytes(bytes_before)
    assert decision_graph(root)['heads'][target_id(targets[0])]['head'] == second['receipt_ref']
