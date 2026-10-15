"""DASH-1: request-local read composition, never a business writer or scheduler."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from urllib.parse import quote

from .canonical_gateway import CanonicalOperationError, list_cases, _find_case_path, _read_json, _case_metadata, _source_caption
from .case_classification import classification_state
from .case_library_access import is_reviewer, owns_task, can_read_private_case
from .customer_gateway import _customer_projection
from .customer_operations_projection import _identity_index, creation_record_index, _timestamp
from .database import connect
from .speaker_gateway import _speaker_projection
from .task_service import TASK_COLUMNS, _row_to_task

BUSINESS_TIMEZONE = timezone(timedelta(hours=8), 'Asia/Shanghai')
EXECUTION_STAGE = {
    'CREATE_CONTENT_PLAN': 'content_plan', 'GENERATE_SCRIPTS': 'script_generation',
    'EXPORT_EXCEL': 'mix_export', 'RESOLVE_NEWS_PLAN': 'news_plan',
    'EXPORT_NEWS_EXCEL': 'news_export', 'generation': 'novel_news_generate',
    'export': 'novel_news_export',
}
SOURCE_LABELS = {'customers': '客户资料', 'requests': '创作记录', 'tasks': '执行任务', 'cases': '案例待办'}
READ_ERRORS = (CanonicalOperationError, OSError, ValueError, RuntimeError, sqlite3.Error)


def business_period(now):
    local = now.astimezone(BUSINESS_TIMEZONE)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year+1, month=1) if start.month == 12 else start.replace(month=start.month+1)
    return {'timezone': 'Asia/Shanghai', 'today': local.date().isoformat(),
            'month_start_inclusive': start.isoformat(), 'month_end_exclusive': end.isoformat()}


def dashboard_tasks(settings, user_id, reviewer):
    """One SQL snapshot, no recent-50 limit. Case scope precedes deserialization."""
    with connect(settings.database_path) as db:
        rows = db.execute(f'''SELECT {TASK_COLUMNS} FROM tasks t
            LEFT JOIN users u ON u.id=t.created_by_user_id
            WHERE t.task_type != 'case_analysis' OR ?=1 OR t.created_by_user_id=?
            ORDER BY t.created_at DESC,t.task_id DESC''', (int(reviewer), user_id)).fetchall()
    tasks = [_row_to_task(row) for row in rows]
    return [t for t in tasks if t['task_type'] != 'case_analysis' or reviewer or owns_task(settings, user_id, t)]


def _item(identity, kind, name, reason, label, url, status, at, priority, **context):
    return {'action_id': identity, 'kind': kind, 'name': name, 'reason': reason,
            'action': {'label': label, 'url': url}, 'status': status,
            'updated_at': _timestamp(at) or None, 'priority': priority,
            'authorized': True, **context}


def _latest(tasks):
    result = {}
    for task in sorted(tasks, key=lambda t: (_timestamp(t['created_at']),t['task_id']), reverse=True):
        # New attempts supersede old failures; retry of one Task retains its ID.
        payload = task.get('payload') or {}
        key = (task['task_type'], task['subject_ref'], task.get('operation_identity') or payload.get('operation') or '')
        result.setdefault(key, task)
    return list(result.values())


def _customer_work(settings):
    ids, speaker_ids = _identity_index(settings)
    customers, speakers, actions, unreadable = {}, {}, [], False
    for business_id in sorted(ids):
        url = '/customers/' + quote(business_id)
        try:
            row = _customer_projection(settings, business_id, approved_speaker_count=0)
            customers[business_id] = row
            status = row['status']
            action = {
                'fact_review_required': ('business_fact_review', '客户事实仍需人工核对。', '核对资料', 30),
                'persona_review_required': ('business_approval', '客户档案等待正式批准。', '审核档案', 40),
                'needs_more_info': ('business_information', '资料缺口或关键限制需要处理。', '查看待处理资料', 35),
                'draft': ('business_draft', '客户资料尚未提交分析。', '继续完善资料', 50),
            }.get(status)
            if action:
                kind, reason, label, priority = action
                persona = row.get('business_persona') or {}
                identity = f"{kind}:{business_id}:{row.get('latest_intake_id') or persona.get('revision') or 'current'}"
                actions.append(_item(identity, kind, row['display_name'], reason, label,
                    url+'/edit' if status == 'draft' else url, status, row.get('submitted_at'), priority,
                    business_id=business_id, timestamp_source='customer_intake.created_at'))
        except READ_ERRORS:
            unreadable = True
            continue
        for speaker_id in sorted(speaker_ids.get(business_id, ())):
            try:
                speaker = _speaker_projection(settings, business_id, speaker_id)
                speakers[speaker_id] = speaker
                action = {
                    'fact_review_required': ('speaker_fact_review', '出镜人事实仍需人工核对。', '核对出镜人', 40),
                    'persona_review_required': ('speaker_approval', '出镜人档案等待正式批准。', '审核出镜人', 40),
                    'revalidation_required': ('speaker_revalidation', '客户档案已更新，需要复核出镜人绑定。', '复核出镜人', 40),
                    'needs_more_info': ('speaker_information', '出镜人资料尚有待处理事项。', '查看出镜人', 45),
                }.get(speaker['status'])
                if action:
                    kind, reason, label, priority = action
                    actions.append(_item(f"{kind}:{business_id}:{speaker_id}:{speaker.get('latest_intake_id') or 'current'}",
                        kind, row['display_name']+' · '+speaker['display_name'], reason, label,
                        url+'/speakers/'+quote(speaker_id), speaker['status'], None, priority,
                        business_id=business_id, speaker_id=speaker_id, timestamp_source=None))
            except READ_ERRORS:
                unreadable = True
    return ids, customers, speakers, actions, unreadable


def _submission_title(settings, user_id, case_id, attempt_id=None):
    """Original source caption only, within the same private Case/Attempt scope."""
    try:
        if can_read_private_case(settings,user_id,case_id,attempt_id):
            path, _ = _find_case_path(settings,case_id,attempt_id=attempt_id)
            title = _source_caption(_case_metadata(_read_json(path)),max_length=110)
            if title: return title
    except READ_ERRORS:
        pass
    return '未命名的视频投稿'


def _work_context(row):
    for key in ('request_id','case_id','speaker_id','business_id','task_id'):
        if row.get(key): return (key,row[key])
    return ('action_id',row['action_id'])


def _case_work(settings, user_id, reviewer, tasks):
    actions = []
    if reviewer:
        rows = [row for row in list_cases(settings) if row['status'] == 'awaiting_review']
    else:
        rows = [{'case_id': t['subject_ref'], 'task': t}
                for t in _latest(tasks) if t['task_type'] == 'case_analysis' and t['status'] == 'awaiting_review'
                and can_read_private_case(settings,user_id,t['subject_ref'])]
    for row in rows:
        case_id = row['case_id']; task = row.get('task')
        # The existing classification writer targets the current Attempt only.
        # Historical readable evidence does not imply an actionable old form.
        classification = classification_state(settings, case_id)
        if task and (classification.get('attempt_id') != task['task_id'] or not classification.get('can_confirm')):
            continue
        needs_confirmation = classification['status'] != 'confirmed'
        # Waiting for platform review is not an action for an ordinary submitter.
        if not needs_confirmation and not reviewer:
            continue
        kind = 'case_classification' if needs_confirmation else 'case_review'
        actions.append(_item(f'{kind}:{case_id}', kind, _submission_title(settings,user_id,case_id,task['task_id'] if task else None),
            'AI 整理的分类需要核对。' if needs_confirmation else '案例等待指定审核人进行人工审核。',
            '核对分类' if needs_confirmation else '审核案例',
            f'/cases/{case_id}/classification' if needs_confirmation else f'/cases/{case_id}',
            'needs_confirmation' if needs_confirmation else 'awaiting_review',
            task['updated_at'] if task else None, 30 if needs_confirmation else 20,
            case_id=case_id, task_id=task['task_id'] if task else None,
            timestamp_source='task.updated_at' if task else None))
    return actions


def dashboard(settings, user_id, *, now=None, section='overview', page=1, page_size=20):
    """All counts and pages share this principal's scope; failures never mean zero."""
    now = now or datetime.now(timezone.utc)
    sources = {key: {'available': True, 'label': label} for key,label in SOURCE_LABELS.items()}
    reviewer = is_reviewer(settings,user_id)
    ids, customers, speakers, actions, records, tasks = None, {}, {}, [], {}, []
    try:
        ids, customers, speakers, actions, unreadable = _customer_work(settings)
        if unreadable: sources['customers']['available'] = False
    except READ_ERRORS:
        sources['customers']['available'] = False
    try:
        records = creation_record_index(settings)
    except READ_ERRORS:
        sources['requests']['available'] = False
    try:
        tasks = dashboard_tasks(settings,user_id,reviewer)
    except READ_ERRORS:
        sources['tasks']['available'] = False
    try:
        # Do not return a misleading empty Case action count when Task scope failed.
        if not sources['tasks']['available']: raise RuntimeError('Task source unavailable')
        actions += _case_work(settings,user_id,reviewer,tasks)
    except READ_ERRORS:
        sources['cases']['available'] = False

    running = [t for t in tasks if t['status'] in {'queued','running'}]
    recent = []
    for business_id,row in customers.items():
        recent.append(_item('customer:'+business_id,'customer',row['display_name'], '客户资料', '查看客户',
            '/customers/'+quote(business_id), row['status'], row.get('submitted_at'), 0,
            business_id=business_id, timestamp_source='customer_intake.created_at', time_label='资料提交'))
    request_map = {}
    tasks_by_subject = {}
    for task in tasks:
        tasks_by_subject.setdefault(task['subject_ref'],[]).append(task)
    active_operations = {(t['subject_ref'],t.get('payload',{}).get('operation')) for t in running}
    for business_id, rows in records.items():
        if ids is None or business_id not in ids: continue
        name = customers.get(business_id,{}).get('display_name',business_id)
        for row in rows:
            request_map[row['request_id']] = row
            active = (row['request_id'],EXECUTION_STAGE.get(row.get('stage'))) in active_operations
            kind = 'content_review' if row.get('stage') in {'HUMAN_REVIEW','human_review','review'} else 'creation_continue'
            item = _item('request:'+row['record_id'], kind, name+' · '+('新闻体创作' if row['profile']=='news' else '视频创作'),
                row['label'], row['label'] if row['label'] != '已导出' else '查看创作记录', row['url'],
                row['status'], row.get('updated_at'), 20 if kind == 'content_review' else 50,
                business_id=business_id, request_id=row['request_id'], timestamp_source='request.created_at', time_label='请求创建')
            matching = tasks_by_subject.get(row['request_id'],[])
            if matching:
                stamp = max((_timestamp(t['updated_at']) for t in matching),default='')
                if stamp and stamp > (item['updated_at'] or ''):
                    item.update(updated_at=stamp,timestamp_source='task.updated_at',time_label='任务更新')
            recent.append(item)
            # A blocked production path is a useful read-only recovery destination;
            # it never grants permission to generate or approve.
            if row.get('action_required') and not active:
                actions.append(item)

    latest = _latest(tasks)
    for task in latest:
        task_id, subject = task['task_id'], task['subject_ref']
        payload = task.get('payload') or {}
        business = customers.get(subject) if task['task_type']=='customer_analysis' else customers.get(payload.get('business_id'))
        speaker = speakers.get(subject) if task['task_type']=='speaker_analysis' else None
        request = request_map.get(subject)
        task_url = '/tasks/'+quote(task_id)
        title = (speaker or {}).get('display_name') or (business or {}).get('display_name') or {
            'content_generation': '视频创作任务', 'excel_export': '内容导出任务',
            'customer_analysis': '客户资料分析', 'speaker_analysis': '出镜人资料分析',
        }.get(task['task_type'],'执行任务')
        context = {'request_id':subject} if request else {'case_id':subject} if task['task_type']=='case_analysis' else (
            {'speaker_id':subject} if speaker else {'business_id':subject} if task['task_type']=='customer_analysis' and business else {})
        if task['task_type']=='case_analysis': title = _submission_title(settings,user_id,subject,task_id)
        if not request:
            existing = next((r for r in recent if _work_context(r)==next(iter(context.items()),None)),None)
            if existing:
                if ((_timestamp(task['updated_at']) or '',task_id) > (existing['updated_at'] or '',existing.get('task_id') or '')):
                    existing.update(updated_at=_timestamp(task['updated_at']),task_id=task_id,timestamp_source='task.updated_at',time_label='任务更新')
                    if task['status'] in {'queued','running','failed'}:
                        existing.update(action={'label':'查看进度' if task['status']!='failed' else '查看任务','url':task_url},status=task['status'])
            else:
                url = ('/customers/'+quote(payload['business_id'])+'/speakers/'+quote(subject)
                       if speaker and payload.get('business_id') else task_url)
                recent.append(_item('task:'+task_id, 'case_submission' if task['task_type']=='case_analysis' else 'task', title,
                    '视频投稿' if task['task_type']=='case_analysis' else '出镜人资料' if speaker else '执行任务',
                    '查看投稿' if task['task_type']=='case_analysis' else '查看出镜人' if speaker else '查看任务',url,
                    task['status'],task['updated_at'],0,task_id=task_id,**context,timestamp_source='task.updated_at',time_label='任务更新'))
        if task['status'] != 'failed': continue
        if task['task_type'] == 'customer_analysis':
            if not business or business['status'] != 'analysis_pending' or payload.get('intake_id') != business.get('latest_intake_id'): continue
            identity = 'customer-recovery:'+subject
        elif task['task_type'] == 'speaker_analysis':
            if not speaker or speaker['status'] != 'analysis_pending' or payload.get('intake_id') != speaker.get('latest_intake_id'): continue
            identity = 'speaker-recovery:'+subject
        elif task['task_type'] in {'content_generation','excel_export'}:
            if not request or not request.get('action_required') or EXECUTION_STAGE.get(request.get('stage')) != payload.get('operation'): continue
            identity = 'request:'+request['record_id']
            actions = [a for a in actions if a['action_id'] != identity]
        elif task['task_type'] == 'case_analysis':
            if len(payload.get('retry_actions',[])) >= 3 or payload.get('duplicate') or task.get('error_code') == 'MEDIA_DUPLICATE_CASE': continue
            # Approved/reviewed candidates and newer attempts block retry at the
            # formal endpoint. Only advertise failures without a current result.
            from .canonical_gateway import resolve_case_source_duplicate
            try:
                duplicate = resolve_case_source_duplicate(settings, str(payload.get('source_url') or ''))
            except READ_ERRORS:
                sources['cases']['available'] = False
                continue
            if duplicate and duplicate.get('state') in {'approved','rejected','awaiting_review','queued','running'}: continue
            if duplicate and duplicate.get('attempt_id') not in {None,task_id}: continue
            identity = 'case-recovery:'+subject
        else: continue
        actions.append(_item(identity,'task_recovery',title,'任务未完成，请从原任务查看原因并恢复。',
            '处理失败任务',task_url,'failed',task['updated_at'],10,task_id=task_id,**context,timestamp_source='task.updated_at'))

    # Stable action identities, not numbers of Tasks/Review files.
    actions = list({row['action_id']:row for row in actions}.values())
    actions.sort(key=lambda r:r['action_id']); actions.sort(key=lambda r:r['updated_at'] or '',reverse=True)
    actions.sort(key=lambda r:r['priority'])
    # One recent business context, not a second list of its execution logs.
    recent_by_context = {}
    for row in recent:
        key = _work_context(row)
        if row['updated_at'] and (key not in recent_by_context or row['updated_at'] > recent_by_context[key]['updated_at']):
            recent_by_context[key] = row
    recent = list(recent_by_context.values())
    recent.sort(key=lambda r:r['action_id']); recent.sort(key=lambda r:r['updated_at'],reverse=True)
    # Only the overview avoids contexts already visible in the five priority
    # actions. The full recent list retains them and their original navigation.
    visible_attention = {_work_context(row) for row in actions[:5]}
    overview_recent = [row for row in recent if _work_context(row) not in visible_attention]
    all_available = all(s['available'] for s in sources.values())
    material_actions = [a for a in actions if a['kind'] in {'business_fact_review','speaker_fact_review','case_classification'}]
    def metric(value, available, label, note, url):
        return {'value':value if available else None,'available':available,'label':label,'note':note,'url':url}
    metrics = {
        'customers':metric(len(ids or ()),ids is not None,'客户总数','当前可访问的独立客户' if ids else '还没有客户，从管理客户开始','/customers'),
        'pending':metric(len(actions),all_available,'待处理事项','按可执行行动去重','/workbench?section=attention'),
        'running':metric(len({t['task_id'] for t in running}),sources['tasks']['available'],'进行中任务','排队与运行中的任务','/workbench?section=running'),
        'materials':metric(len(material_actions),sources['customers']['available'] and sources['cases']['available'],
            '待核对资料','待处理事项中的资料核对','/workbench?section=materials'),
    }
    selected = running if section=='running' else material_actions if section=='materials' else recent if section=='recent' else actions
    if section=='running':
        selected = [_item('task:'+t['task_id'],'task', '执行任务', t['stage'] or '正在处理', '查看进度',
            '/tasks/'+quote(t['task_id']),t['status'],t['updated_at'],0,task_id=t['task_id'],timestamp_source='task.updated_at') for t in running]
        selected.sort(key=lambda r:r['updated_at'] or '',reverse=True)
    section_complete = (sources['tasks']['available'] if section=='running' else metrics['materials']['available'] if section=='materials'
        else all(sources[k]['available'] for k in ('customers','requests','tasks')) if section=='recent' else all_available)
    return {'schema_version':'brand-operations-home-v1.0','projection_only':True,'generated_at':now.isoformat(),
        'period':business_period(now),'scope':'current_authorized_collaboration','recent_scope':'授权范围内最近更新或提交',
        'sources':sources,'partial':not all_available,'metrics':metrics,
        'attention':actions[:5],'recent':overview_recent[:5], 'recent_omitted_attention':len(recent)-len(overview_recent),
        'list':{'section':section,'items':selected[(page-1)*page_size:page*page_size] if section!='overview' else [], 'total':len(selected),
                'complete':section_complete,
                'page':page,'page_size':page_size},
        'completed_works':{'available':False,'value':None,'reason':'没有统一的正式作品完成口径；脚本导出与成片交付不同。'},
        'capabilities':{'case_library_reviewer':reviewer},
        'shortcuts':[{'title':'管理客户','description':'查看客户、添加资料，从客户继续创作。','url':'/customers','icon':'customers'},
                     {'title':'案例库','description':'浏览共享参考，提交视频或查看我的投稿。','url':'/cases','icon':'cases'}]}
