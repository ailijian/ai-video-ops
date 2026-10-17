"""SHA-bound, append-only display permission; never Case or production approval."""
from __future__ import annotations

import importlib.util
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from .canonical_gateway import (
    CanonicalOperationError, _read_json, _sha256, case_cover_path,
)
from .case_classification import classification_summary
from .case_library_access import reviewer_authorization, reviewer_lock, _owner

VERSION = 'case-shared-display-v1.0'
FIELDS = ('title','industry','video_type','duration_seconds','structure_summary')
KEYS = {'schema_version','case_id','audience','sequence','parent_sha256','action','at','actor',
        'case_sha256','approval_receipt_sha256','allowed_fields','display','sources','cover_clearance'}


def _blocked(message='共享展示记录无法核对。'):
    return CanonicalOperationError('CASE_DISPLAY_CONFLICT',message,'请刷新案例并重新核对。')


def _root(settings,case_id):
    if not re.fullmatch(r'\d{10,24}',str(case_id)):
        raise _blocked()
    return settings.pipeline_root/'data/case_governance/cases'/case_id/'shared_display'


def _base(settings,case_id):
    _root(settings,case_id)  # Reject identifiers before touching filesystem paths.
    path = settings.pipeline_root/'data/cases'/case_id/'case_v1.json'
    receipt_path = path.parent/'approval_receipt.json'
    case, receipt = _read_json(path), _read_json(receipt_path)
    case_sha, receipt_sha = _sha256(path), _sha256(receipt_path)
    lifecycle = case.get('lifecycle') or {}
    if (case.get('case_id') != case_id or lifecycle.get('status') != 'approved' or lifecycle.get('approved') is not True
            or receipt.get('case_id') != case_id or receipt.get('human_gate') is not True
            or receipt.get('decision') != 'approved' or receipt.get('case_sha256_after_approval') != case_sha):
        raise _blocked('案例批准与收据尚未完整核对。')
    # Preserve the existing full approved-artifact validator and partial recovery boundary.
    from .canonical_gateway import _validate_approved_case_artifacts, _partial_approval_state
    _validate_approved_case_artifacts(path,expected_case_id=case_id,
        expected_attempt_id=str((case.get('analysis_lineage') or {}).get('attempt_id') or ''),
        expected_reviewer=str(receipt.get('reviewer') or ''))
    if _partial_approval_state(settings,case_id,case) is not None:
        raise _blocked('案例需要先恢复正式批准。')
    return case, case_sha, receipt_sha


def _history(settings,case_id):
    previous = None
    records = []
    for sequence,path in enumerate(sorted(_root(settings,case_id).glob('receipt_*.json')),1):
        value = _read_json(path)
        if (path.name != f'receipt_{sequence:06}.json' or set(value) != KEYS
                or value['schema_version'] != VERSION or value['case_id'] != case_id
                or value['audience'] != 'eligible_platform_users'
                or value['sequence'] != sequence or value['parent_sha256'] != previous
                or value['action'] not in {'publish','withdraw'}
                or not re.fullmatch(r'[a-f0-9]{64}',str(value['case_sha256']))
                or not re.fullmatch(r'[a-f0-9]{64}',str(value['approval_receipt_sha256']))
                or set(value['actor']) != {'namespace','user_id','capability','event_id','event_sha256'}
                or value['actor']['capability'] != 'case_library_reviewer'):
            raise _blocked()
        if not _owner(str(settings.pipeline_root)).validate_authorization_evidence(settings.database_path,value['actor']):
            raise _blocked()
        if value['action'] == 'publish':
            if (value['allowed_fields'] != list(FIELDS) or set(value['display']) != set(FIELDS)
                    or set(value['sources']) != set(FIELDS)):
                raise _blocked()
            _validate_display(value['display'])
        elif value['allowed_fields'] or value['display'] or value['sources'] or value['cover_clearance']:
            raise _blocked()
        previous = _sha256(path)
        records.append((value,previous))
    return records


def _validate_display(display):
    if not isinstance(display['title'],str) or not display['title'].strip() or len(display['title']) > 120:
        raise _blocked('请提供已人工核对的展示标题。')
    if display['industry'] is not None and (not isinstance(display['industry'],str) or len(display['industry']) > 30):
        raise _blocked()
    if display['video_type'] is not None:  # No formal type taxonomy exists in the current contract.
        raise _blocked('当前尚无正式视频类型合同。')
    duration=display['duration_seconds']
    if duration is not None and (isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration <= 0):
        raise _blocked()
    if not isinstance(display['structure_summary'],str) or len(display['structure_summary']) > 1000:
        raise _blocked()
    text=display['title']+' '+display['structure_summary']
    if re.search(r'(?<!\d)1[3-9]\d{9}(?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text):
        raise _blocked('共享展示中不能包含个人联系方式。')


def _confirmed_industry(settings,case_id,case_sha):
    annotation_path=settings.pipeline_root/'data/case_governance/cases'/case_id/'case_industry_annotation_v1.json'
    if annotation_path.is_file():
        from .canonical_gateway import get_case_detail
        detail=get_case_detail(settings,case_id)
        annotation=detail.get('industry_annotation')
        if annotation:
            return annotation['industry'],{'kind':'industry_annotation','sha256':_sha256(annotation_path)}
    summary=classification_summary(settings,case_id)
    if summary['status']=='confirmed' and summary.get('industry'):
        case_path=settings.pipeline_root/'data/cases'/case_id/'case_v1.json'
        attempt_id=(_read_json(case_path).get('analysis_lineage') or {}).get('attempt_id')
        path=settings.pipeline_root/'data/case_analysis_attempts'/case_id/str(attempt_id)/'case_classification_review_v1.json'
        record=_read_json(path)
        receipt=_read_json(case_path.parent/'approval_receipt.json')
        if record.get('confirmed_case_sha256')!=receipt.get('case_sha256_before_approval'):
            raise _blocked('分类确认与原批准候选无法绑定。')
        return summary['industry'],{'kind':'classification_confirmation','sha256':_sha256(path)}
    return None,{'kind':'not_confirmed','case_sha256':case_sha}


def publication_context(settings,case_id):
    try:
        _,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        return {'available':True,'approved_case_sha256':case_sha,'approval_receipt_sha256':receipt_sha,
                'cover_available':case_cover_path(settings,case_id) is not None,
                'display_receipt_sha256':history[-1][1] if history else None,
                'published':bool(history and history[-1][0]['action']=='publish' and shared_projection(settings,case_id))}
    except (CanonicalOperationError,OSError,ValueError,TypeError,KeyError) as exc:
        return {'available':False,'published':False,'blocker':{
            'code':getattr(exc,'code','CASE_DISPLAY_EVIDENCE_UNAVAILABLE'),
            'message':'案例的来源、隐私或批准收据证据尚未完整通过共享校验。',
            'next_action':'请由指定审核或运维人员核对原来源与批准证据。保留历史审核；补证完成前不能共享。'}}


def change_publication(settings,case_id,*,actor,action,title='',structure_summary='',cover_evidence=None,
                       approved_case_sha256,approval_receipt_sha256,expected_display_receipt_sha256=None):
    if action not in {'publish','withdraw'}: raise _blocked()
    with reviewer_lock(settings,actor):
        authorization=reviewer_authorization(settings,actor)
        case,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        parent=history[-1][1] if history else None
        if case_sha!=approved_case_sha256 or receipt_sha!=approval_receipt_sha256 or parent!=expected_display_receipt_sha256:
            raise _blocked('案例或共享决定已经变化。')
        display,sources,clearance={},{},None
        if action=='publish':
            industry,industry_source=_confirmed_industry(settings,case_id,case_sha)
            duration=(case.get('identity') or {}).get('duration_seconds')
            if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
                duration=None
            display={'title':title.strip(),'industry':industry,'video_type':None,
                     'duration_seconds':duration,'structure_summary':structure_summary.strip()}
            _validate_display(display)
            spec=importlib.util.spec_from_file_location('case_display_privacy',settings.pipeline_root/'scripts/privacy_projection_v1.py')
            privacy=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(privacy)
            if privacy.scan_sensitive_values(display):
                raise _blocked('展示内容需要先处理隐私信息。')
            sources={'title':{'kind':'human_confirmed_display_title','case_sha256':case_sha},
                     'industry':industry_source,'video_type':{'kind':'no_formal_taxonomy'},
                     'duration_seconds':{'kind':'approved_case_identity','case_sha256':case_sha},
                     'structure_summary':{'kind':'human_reviewed_structural_reference','case_sha256':case_sha}}
            if cover_evidence is not None:
                path=case_cover_path(settings,case_id)
                provenance=case.get('source_provenance') or {}
                source_sha=provenance.get('recorded_source_media_sha256') or ((case.get('source_evidence') or {}).get('video') or {}).get('sha256')
                if (path is None or not re.fullmatch(r'[a-f0-9]{64}',str(source_sha))
                        or set(cover_evidence)!= {'reference','statement','display_rights_confirmed'}
                        or cover_evidence['display_rights_confirmed'] is not True
                        or not str(cover_evidence['reference']).strip() or not str(cover_evidence['statement']).strip()):
                    raise _blocked('封面需要独立、明确的展示权利证据。')
                clearance={'case_id':case_id,'case_sha256':case_sha,'source_media_sha256':source_sha,
                           'cover_sha256':_sha256(path),'scope':'eligible_platform_users_display_only',
                           'evidence':cover_evidence,'production_media_rights_granted':False}
        record={'schema_version':VERSION,'case_id':case_id,'audience':'eligible_platform_users','sequence':len(history)+1,
                'parent_sha256':parent,'action':action,'at':datetime.now(timezone.utc).isoformat(),
                'actor':authorization,'case_sha256':case_sha,'approval_receipt_sha256':receipt_sha,
                'allowed_fields':list(FIELDS) if action=='publish' else [],'display':display,'sources':sources,
                'cover_clearance':clearance}
        root=_root(settings,case_id)
        root.mkdir(parents=True,exist_ok=True)
        target=root/f"receipt_{record['sequence']:06}.json"
        from .canonical_gateway import _write_atomic
        # The caller holds the existing Case authority lock; no old receipt is replaced.
        if target.exists(): raise _blocked()
        _write_atomic(target,record)
        return publication_context(settings,case_id)


def shared_projection(settings,case_id):
    try:
        _,case_sha,receipt_sha=_base(settings,case_id)
        history=_history(settings,case_id)
        if not history: return None
        record,record_sha=history[-1]
        if record['action']!='publish' or record['case_sha256']!=case_sha or record['approval_receipt_sha256']!=receipt_sha:
            return None
        industry,source=_confirmed_industry(settings,case_id,case_sha)
        if record['display']['industry']!=industry or record['sources']['industry']!=source:
            return None
        return {'case_id':case_id,**record['display'],'status':'approved','visibility':'shared',
                'published_at':record['at'],'display_revision':record_sha,
                'cover_url':f'/api/case-library/{case_id}/cover' if shared_cover_path(settings,case_id,record) else None,
                'media_rights':{'production_authorized':False},'review':{'can_review':False,'approved':True}}
    except (CanonicalOperationError,OSError,ValueError,TypeError,KeyError):
        return None


def shared_cover_path(settings,case_id,record=None):
    try:
        case,case_sha,receipt_sha=_base(settings,case_id)
        if record is None:
            history=_history(settings,case_id)
            if not history: return None
            record=history[-1][0]
        clearance=record.get('cover_clearance')
        if (record['action']!='publish' or record['case_sha256']!=case_sha
                or record['approval_receipt_sha256']!=receipt_sha or not clearance
                or clearance.get('case_id')!=case_id or clearance.get('case_sha256')!=case_sha
                or clearance.get('source_media_sha256')!=((case.get('source_provenance') or {}).get('recorded_source_media_sha256')
                    or ((case.get('source_evidence') or {}).get('video') or {}).get('sha256'))
                or clearance.get('scope')!='eligible_platform_users_display_only'
                or clearance.get('production_media_rights_granted') is not False
                or clearance.get('evidence',{}).get('display_rights_confirmed') is not True):
            return None
        path=case_cover_path(settings,case_id)
        return path if path and _sha256(path)==clearance['cover_sha256'] else None
    except (CanonicalOperationError,OSError,ValueError,TypeError,KeyError):
        return None


def shared_cases(settings):
    rows=[]
    for root in (settings.pipeline_root/'data/case_governance/cases').glob('*/shared_display'):
        row=shared_projection(settings,root.parent.name)
        if row: rows.append(row)
    return sorted(rows,key=lambda row:(row['published_at'],row['case_id']),reverse=True)
