"""Fictional, source-qualified UI fixtures; all approvals use Native owners."""
from test_creation_batch_conversion_v1 import conversion_history
from pathlib import Path
from test_creation_batch_orchestration_v1 import external_boundaries, REAL_RUN

PROJECT=Path(__file__).resolve().parents[2]

PRICES = [
    '午餐套餐29元，仅限工作日到店自取，不含配送',
    '儿童小份餐15元，仅限周末店内点单，不参与工作日午餐套餐',
    '线上预订菌菇午餐35元，周三营业时段可自取，每单仅限一份套餐',
    '午餐双拼套餐39元，周五营业时段可到店自取，不含配送',
    '三人家庭周六分享餐88元，需提前一天预约，到店领取，不含配送',
]

def history_boundary(command,*args,**kwargs):
    name=Path(command[1]).name if len(command)>1 else ''
    if name in {'resolve_generation_content_plan_v1.py','resolve_generation_batch_v1.py'}:
        command=list(command);operation='plan' if name=='resolve_generation_content_plan_v1.py' else 'generate'
        root=command[command.index('--pipeline-root')+1];rid=command[command.index('--request-id')+1]
        extra=[command[command.index('--operation-id')+1],command[command.index('--intent-sha256')+1]] if '--operation-id' in command else []
        return REAL_RUN([command[0],str(PROJECT/'internal-console/tests/news_source_history_synthetic.py'),operation,root,rid,*extra],*args,**kwargs)
    return external_boundaries(command,*args,**kwargs)

def qualified_history(node):
    return conversion_history(node, pricing_facts=PRICES,external_boundary=history_boundary)
