"""UI fallback is a read projection, never a rewrite of a source title."""
from test_case_library_security_v1 import node,analyze,ready,CASE_ID

def test_submission_fallback_retains_exact_identity_and_other_principal_isolation(node):
    a,_,_=node[1]['A'];b,_,_=node[1]['B']
    _,task=analyze(node)
    data=a.get('/api/cases?view=mine').json()
    row=next(r for r in data['cases'] if r['case_id']==CASE_ID)
    assert row['title']=='未命名的视频投稿'
    assert row['submission_id']==task['task_id'] and task['task_id'] in row['href']
    assert b.get('/api/cases?view=mine').json()['total']==0
    ready(node)
    row=next(r for r in a.get('/api/cases?view=mine').json()['cases'] if r['case_id']==CASE_ID)
    assert row['title']=='用于审批测试的公开来源'
