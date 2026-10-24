"""Read-model ordering only; the Native three-mode tests exercise real gates."""
from contextlib import contextmanager
from types import SimpleNamespace
from app import publish_copy_gateway as gateway

def test_task_snapshot_precedes_native_and_only_one_owner_query(monkeypatch):
    calls=[]
    @contextmanager
    def connect(path):
        class Query:
            def execute(self,*args):return self
            def fetchall(self):return [{'task_id':'original'}]
        yield Query()
    def get_task(path,tid):
        calls.append('task');return {'task_id':tid,'status':'running'}
    def native(settings,rid,command):
        calls.append(command)
        # It may finish after the earlier Task snapshot. Reporting running for
        # one poll is safe; completed Task + older Native truth is avoided.
        return {'state':'draft_ready','confirmed':False,'delivery':None}
    monkeypatch.setattr(gateway,'connect',connect)
    monkeypatch.setattr(gateway,'get_task',get_task)
    monkeypatch.setattr(gateway,'native',native)
    result=gateway.project(SimpleNamespace(database_path='unused'),'original')
    assert calls==['task','project']
    assert result['tasks'][0]['status']=='running'
    assert result['task_snapshot_before_native'] is True
