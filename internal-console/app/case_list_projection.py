"""Scoped Case card queries. Display states are derived, never lifecycle writes."""
from urllib.parse import quote

from .canonical_gateway import CanonicalOperationError, _read_json, case_cover_path, get_case_detail, list_cases
from .case_classification import classification_summary
from .case_intake_service import get_group
from .case_library_access import can_read_group, can_read_private_case, is_reviewer, owns_task, safe_case_task
from .case_shared_display import shared_cases
from .database import connect
from .task_service import TASK_COLUMNS, _row_to_task


def my_submissions(settings,user_id):
    db=connect(settings.database_path)
    try:
        tasks=[_row_to_task(row) for row in db.execute(
            f"SELECT {TASK_COLUMNS} FROM tasks t LEFT JOIN users u ON u.id=t.created_by_user_id WHERE t.task_type='case_analysis' AND t.created_by_user_id=? ORDER BY t.created_at DESC,t.task_id DESC",(user_id,))]
        group_ids=[r[0] for r in db.execute('SELECT group_id FROM case_intake_groups WHERE created_by_user_id=? ORDER BY created_at DESC,group_id DESC',(user_id,))]
    finally: db.close()
    rows=[]
    own_task_ids={task['task_id'] for task in tasks if owns_task(settings,user_id,task)}
    for task in tasks:
        if not owns_task(settings,user_id,task): continue
        task=safe_case_task(settings,user_id,task)
        case_id=task['subject_ref']
        detail=None
        try:
            if can_read_private_case(settings,user_id,case_id,task['task_id']):
                detail=get_case_detail(settings,case_id,attempt_id=task['task_id'])
        except CanonicalOperationError: pass
        state=task['status']
        classification=None
        if detail:
            try: classification=classification_summary(settings,case_id,attempt_id=task['task_id'])
            except CanonicalOperationError: pass
        receipt=settings.pipeline_root/'data/case_analysis_attempts'/case_id/task['task_id']/'human_review_decision_v1.json'
        decision=_read_json(receipt) if receipt.is_file() else {}
        if decision.get('decision')=='reject': state='rejected'
        elif decision.get('decision')=='reanalyze': state='returned'
        elif detail and detail['review']['approved']: state='approved'
        elif state=='awaiting_review' and detail:
            state='needs_confirmation' if not classification or classification['status']!='confirmed' else 'awaiting_review'
        industry=(classification or {}).get('industry') if (classification or {}).get('status')=='confirmed' else None
        if detail and detail.get('industry_annotation'): industry=detail['industry_annotation']['industry']
        cover=None
        if detail and case_cover_path(settings,case_id,attempt_id=task['task_id']):
            cover=f"/api/cases/{case_id}/cover?attempt_id={quote(task['task_id'])}"
        href=f"/cases/{case_id}?attempt_id={quote(task['task_id'])}" if detail else f"/tasks/{quote(task['task_id'])}"
        if state=='needs_confirmation': href=f'/cases/{case_id}/classification?attempt_id={quote(task["task_id"])}'
        rows.append({'case_id':case_id,'submission_id':task['task_id'],'task_id':task['task_id'],
                     'title':detail['title'] if detail else '未命名的视频投稿',
                     'industry':industry,'video_type':None,'duration_seconds':detail.get('duration_seconds') if detail else None,
                     'cover_url':cover,'status':state,'href':href,'visibility':'mine',
                     'submitted_at':task['created_at'],'updated_at':task['updated_at'],
                     'next_action':'继续解析' if state=='failed' else '核对分类' if state=='needs_confirmation' else '查看投稿',
                     'failure_reason':task.get('error_message') if state=='failed' else None,
                     'review_reason':decision.get('reason') if state=='rejected' else None})
    for group_id in group_ids:
        group=get_group(settings.database_path,group_id)
        if not can_read_group(settings,user_id,group): continue
        for item in group['items']:
            if item['state']=='input_duplicate' or item['task_id'] in own_task_ids: continue
            case_id=item.get('case_id')
            rows.append({'case_id':case_id,'submission_id':f"{group_id}:{item['position']}",
                         'title':'未命名的视频投稿' if case_id else '待处理的视频链接',
                         'industry':None,'video_type':None,'duration_seconds':None,'cover_url':None,
                         'status':'queued' if item['state']=='pending' else 'failed' if item['state']=='error' else 'submitted',
                         'href':f'/case-intake/{group_id}','visibility':'mine','next_action':'查看投稿',
                         'submitted_at':group['created_at'],'updated_at':group['created_at']})
    return sorted(rows,key=lambda row:(row['submitted_at'],row['submission_id']),reverse=True)


def case_cards(settings,user_id,*,view='shared',search='',industry='',video_type='',status='',page=1,page_size=20):
    reviewer=is_reviewer(settings,user_id)
    if view=='review' and not reviewer:
        from .case_library_access import not_visible
        not_visible()
    if view=='shared': rows=shared_cases(settings)
    elif view=='mine': rows=my_submissions(settings,user_id)
    elif view=='review':
        rows=[]
        for row in list_cases(settings, include_terminal=True):
            row['visibility']='review'
            attempt_id=row.get('attempt_id')
            # The card needs only the exact decision companion, not full evidence
            # or media integrity reads for every row in the review list.
            receipt=settings.pipeline_root/'data/case_analysis_attempts'/row['case_id']/str(attempt_id)/'human_review_decision_v1.json'
            decision=_read_json(receipt) if attempt_id and receipt.is_file() else {}
            terminal=decision.get('decision') if (decision.get('case_id'),decision.get('attempt_id'))==(row['case_id'],attempt_id) else None
            if terminal: row['status']='rejected' if terminal=='reject' else 'returned'
            row['href']=f"/cases/{row['case_id']}"+(f'?attempt_id={quote(attempt_id)}' if attempt_id else '')
            row['video_type']=None
            row['cover_url']=None
            row['classification']=classification_summary(settings,row['case_id'],attempt_id=attempt_id)
            row['industry']=row['classification'].get('industry') if row['classification']['status']=='confirmed' else (row.get('industry_annotation') or {}).get('industry')
            if row['status']=='awaiting_review' and row['classification']['status']!='confirmed':
                row['status']='needs_confirmation'
                row['href']=f"/cases/{row['case_id']}/classification"
            rows.append(row)
        rows.sort(key=lambda row:(row['status']=='approved',row['status']!='awaiting_review'))
    else: raise ValueError('Unknown Case view')
    # Query values and counts are derived only after the complete permission scope.
    industries=sorted({row['industry'] for row in rows if row.get('industry')})
    needle=search.strip().casefold()
    rows=[row for row in rows if (not needle or needle in row['title'].casefold())
          and (not industry or industry==row.get('industry')) and (not video_type or video_type==row.get('video_type'))]
    counts={value:sum(row['status']==value for row in rows) for value in sorted({row['status'] for row in rows})}
    if status: rows=[row for row in rows if row['status']==status]
    total=len(rows)
    return {'cases':rows[(page-1)*page_size:page*page_size], 'total':total,
            'page':page,'page_size':page_size,'industries':industries,'video_types':[],
            'status_counts':counts,'capabilities':{'case_library_reviewer':reviewer},'view':view}
