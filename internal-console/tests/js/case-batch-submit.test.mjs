import assert from 'node:assert/strict';
import { intakeItemState, intakeCounts, intakeStage } from '../../static/assets/case-batch-submit.mjs';
const items = [
 {state:'pending'},
 {state:'linked',task:{status:'running',stage:'分析画面'}},
 {state:'linked',task:{status:'failed'}},
 {state:'linked',case:{status:'awaiting_review'},classification:{status:'needs_confirmation'}},
 {state:'linked',case:{status:'awaiting_review'},classification:{status:'confirmed',human:{industry:'餐饮',profile:'mix'}}},
 {state:'linked',case:{status:'approved'},task:{status:'failed'}},
 {state:'input_duplicate'},
];
assert.deepEqual(intakeCounts(items),{total:6,analyzing:2,needs_confirmation:1,confirmed:1,failed:1,completed:0,approved:1,duplicates:1});
assert.equal(intakeCounts([{task:{status:'completed'}}]).approved,0,'execution completion is not admission to the Case library');
assert.equal(intakeItemState(items[5]),'approved','canonical approval wins over historical failed execution');
assert.equal(intakeStage(items[0]),'读取链接 / 等待入队');
assert.equal(intakeStage(items[1]),'分析视频内容');
assert.equal(intakeStage(items[3]),'等待人工确认');
assert.equal(intakeStage(items[4]),'分类已确认');
assert.equal(intakeStage(items[5]),'已加入正式案例库');
assert.equal(intakeStage(items[6]),'本批重复，已合并');
for(const item of items) assert.doesNotMatch(intakeStage(item), /%|剩余.*秒/);
console.log('CASE_INTAKE_BATCH_STATES_PASS');
