"""Original Native Human writers retain exact decisions across write windows."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from news_export_support import generate


@pytest.mark.parametrize('kind', ['novel', 'repurpose'])
@pytest.mark.parametrize('window', ['review', 'approved'])
def test_native_human_write_interruption_preserves_decision(tmp_path, kind, window):
    if kind == 'novel':
        import novel_news_v1 as owner
        from test_novel_news_v1 import fixture
        root, rid, beats = fixture(tmp_path)
        generate(pipeline_root=root, request_id=rid, transport=lambda prompt: {'payload': {'beats': beats}})
        paths = owner._paths(root, rid)
        review, approved = paths['review'], paths['approved']
        def submit():
            return owner.review_novel_news_plan(pipeline_root=root, request_id=rid,
                reviewer='unit explicit human', decisions=[{'beat_id':f'B{i:03d}', 'decision':'approved'} for i in range(1,5)])
        writer_name = '_write_new'
    else:
        import news_delivery_v1 as owner
        from test_news_delivery_v1 import build_fixture, build_review
        value = build_fixture(tmp_path)
        root = value['pipeline']
        request, _ = owner.create_news_delivery_request(pipeline_root=root,
            business_id=value['business_id'], speaker_id=value['speaker_id'],
            source_content_id=value['source_content_id'], idempotency_key='human-write-window')
        rid = request['request_id']
        plan, _ = owner.resolve_news_delivery_plan(pipeline_root=root, request_id=rid)
        incoming = build_review(tmp_path, plan)
        directory = owner._request_root(root, rid)
        review, approved = directory/'news_delivery_human_review_v1.json', directory/'approved_news_delivery_v1.json'
        def submit():
            return owner.approve_news_delivery(pipeline_root=root, request_id=rid, review_path=incoming)
        writer_name = 'write_new_json'
    original = getattr(owner, writer_name)
    target = review if window == 'review' else approved
    def interrupted(path, value):
        result = original(path, value)
        if Path(path) == target:
            raise OSError('injected native human write interruption')
        return result
    with patch.object(owner, writer_name, side_effect=interrupted):
        with pytest.raises(OSError, match='injected native human'):
            submit()
    retained = {p:p.read_bytes() for p in (review, approved) if p.exists()}
    if window == 'review':
        assert review.exists() and not approved.exists()
        submit()  # Same explicit decision, original reviewed_at retained.
    elif kind == 'repurpose':
        assert submit()[1] is True
    else:
        # Original completed approval is immutable; status/readers resume it.
        with pytest.raises(owner.NovelNewsError, match='immutable'):
            submit()
        assert owner.novel_news_status(pipeline_root=root, request_id=rid)['stage'] == 'export'
    assert approved.exists()
    assert all(p.read_bytes() == data for p, data in retained.items())
