"""Derived journal compatibility only; no Native approval/qualification claim."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from creation_batch_review_v1 import write_or_reuse_mix_review_input
from creation_batch_contract_v1 import BatchError
from human_review_operations_v1 import write_once,io_path


def test_saved_pre_normalization_input_is_reused_without_rewriting_immutable_bytes(tmp_path):
    expected={'schema_version':'generation-batch-review-input-v2.0','reviewer':'fictional-reviewer',
        'note':'Explicit batch content review unit', 'items':[
            {'content_id':'unit-first','decision':'approved','note':''},
            {'content_id':'unit-second','decision':'rejected','note':''}]}
    old=copy.deepcopy(expected);old['items'].reverse()
    path=tmp_path/'legacy.native-input.json';write_once(path,old);before=io_path(path).read_bytes()
    write_or_reuse_mix_review_input(path,expected)
    assert io_path(path).read_bytes()==before
    for wrong in [{**expected,'reviewer':'someone-else'}, {**expected,'items':expected['items'][:1]},
                  {**expected,'items':[{**expected['items'][0],'decision':'rejected'},expected['items'][1]]}]:
        with pytest.raises(BatchError):write_or_reuse_mix_review_input(path,wrong)
        assert io_path(path).read_bytes()==before
    fresh=tmp_path/'new.native-input.json';write_or_reuse_mix_review_input(fresh,expected)
    assert io_path(fresh).read_bytes()!=before
