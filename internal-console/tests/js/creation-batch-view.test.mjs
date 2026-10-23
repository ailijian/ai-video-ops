import test from 'node:test';
import assert from 'node:assert/strict';
import { batchProgressSummary, batchWorkflow, batchDetailMarkup, nativeCreationUrl, createBatchControls, humanReviewMarkup, humanCommand, batchHistoryMarkup,continueHumanCommand,deliveryReadySlots,availableBatchPhases,batchWorkspaceMarkup,batchIdentity } from '../../static/assets/creation-batch-view.mjs';
import { batchDeliveryScope } from '../../static/assets/creation-batch-draft.mjs';

const projection = () => ({ batch_id: 'batch_fictional', business_id: 'fictional', control: 'resume',
  completion_proven: false, status: 'awaiting_review', counts: { target: 2, generated: 2, approved: 0,
    delivered: 0, unknown: 0, failed: 0, missing_generation: 0 }, groups: [] });

test('bounded Human continuation reuses the exact confirmed command and stops on no progress or navigation',async()=>{
  const body={operation_id:'original',items:[{slot_id:'one',decision:'approve'}]},calls=[];
  const responses=[2,1,0].map(n=>({result:{all_native_completed:n===0,continuation_needed:n>0,
    results:Array.from({length:n},()=>({deferred:true}))}}));
  const result=await continueHumanCommand(async(suffix,payload)=>{calls.push([suffix,payload]);return responses.shift();},body,()=>true);
  assert.equal(result.result.all_native_completed,true);assert.equal(calls.length,3);
  assert.ok(calls.every(([suffix,payload])=>suffix==='human-command' && payload===body));
  let count=0;
  await continueHumanCommand(async()=>{count+=1;return {result:{continuation_needed:true,results:[{deferred:true}]}};},body,()=>true);
  assert.equal(count,2);
  let current=true;count=0;
  await continueHumanCommand(async()=>{count+=1;current=false;return {result:{continuation_needed:true,results:[{deferred:true}]}};},body,()=>current);
  assert.equal(count,1);
});

test('generated count never implies approval or complete delivery', () => {
  const value = projection();
  assert.equal(batchProgressSummary(value).full, false);
  assert.match(batchDetailMarkup(value), /等待人工审核/);
  value.control = 'end';
  assert.equal(batchProgressSummary(value).full, false);
  assert.match(batchDetailMarkup(value), /本批结束不等于整批完成/);
  assert.doesNotMatch(batchDetailMarkup(value), /id="batch-resume"/);
  value.completion_proven = true; value.counts.approved = value.counts.delivered = 2;
  assert.equal(batchProgressSummary(value).full, false);
  value.control = 'resume';
  assert.equal(batchProgressSummary(value).full, true);
  value.counts.unknown = 1;
  assert.equal(batchProgressSummary(value).full, false);
});

test('Native routes preserve source kind and escape rendered content', () => {
  const value = projection();
  value.groups = [{ request_id: 'native&fictional', profile: 'news', native: { mode: 'novel_content' }, target: 1, generated: 1, approved: 0 }];
  const url = new URL(nativeCreationUrl(value.groups[0], value.business_id), 'https://fixture.invalid');
  assert.equal(url.searchParams.get('request_id'), 'native&fictional');
  assert.equal(url.searchParams.get('news_mode'), 'novel_content');
  assert.match(batchDetailMarkup(value), /新闻体 · 新创作/);
  value.groups[0].native.mode = 'cross_profile_repurpose';
  assert.match(batchDetailMarkup(value), /新闻体 · 改编已有内容/);
  value.groups[0].native.mode = null;
  assert.match(batchDetailMarkup(value), /来源待核对/);
  value.groups[0].style_id = '<script>bad</script>';
  assert.doesNotMatch(batchDetailMarkup(value), /<script>/);
});

test('double click is inert and response-loss retry keeps control identity', async () => {
  let calls = [], release;
  const controls = createBatchControls(async (path, options) => {
    calls.push({ path, body: JSON.parse(options.body) });
    if (calls.length === 1) return new Promise((_resolve, reject) => { release = () => reject(Error('response lost')); });
    return { result: { control: { action: 'resume' } } };
  }, () => 'fixed_fictional_operation');
  const first = controls('resume');
  assert.equal(await controls('resume'), null);
  release(); await assert.rejects(first, /response lost/);
  await controls('resume');
  assert.equal(calls.length, 2); assert.deepEqual(calls[0], calls[1]);
  assert.equal(calls[0].body.action, 'resume');
  assert.doesNotMatch(calls[0].path, /generate|review|export/);
});

test('concentrated decisions have no default approval and bind the complete Native group', () => {
  const source = { path: 'fictional-source', sha256: 'a'.repeat(64) };
  const preview = { scope: 'native_content_review', source_sha256: 'b'.repeat(64), items: ['s1', 's2'].map(slot_id => ({
    slot_id, native_kind: 'mix', native_source_ref: source, expected_head_ref: source,
    display: { title: '<img src=x onerror=bad()>', narration: '须逐条阅读的完整正文', style_id: 'story' },
  })) };
  const value = projection(); value.groups = [{ slots: [{ slot_id: 's1' }, { slot_id: 's2' }] }];
  const markup = humanReviewMarkup(preview);
  assert.doesNotMatch(markup, /aria-pressed="true"|<img/); assert.match(markup, /尚未选择/);
  assert.throws(() => humanCommand(preview, ['', ''], value, 'op'), /至少/);
  assert.throws(() => humanCommand(preview, ['approve', ''], value, 'op'), /每条/);
  const command = humanCommand(preview, ['reject', 'approve'], value, 'op');
  assert.deepEqual(command.items.map(v => v.decision), ['reject', 'approve']);
  assert.equal(command.items[0].native_source_ref, source); assert.ok(!('display' in command.items[0]));
  assert.equal(command.source_sha256, preview.source_sha256);
});

test('publish confirmation displays exact title, body, topics and production headlines', () => {
  const value = { scope: 'publish_copy_confirmation', items: [{ slot_id: 's1', native_kind: 'novel_content', display: {
    publish_title: '准确发布标题', publish_body: '含主体、数字及适用条件的正文。', topics: ['来源话题'],
    production_headlines: [{ order: 1, text: '准确制作短标题' }],
  } }] };
  const markup = humanReviewMarkup(value);
  for (const text of ['准确发布标题', '含主体、数字及适用条件的正文。', '来源话题', '准确制作短标题']) assert.ok(markup.includes(text));
  assert.doesNotMatch(markup, /checked/);
});

test('Publish review preserves the exact batch Slot Style without adding it to the Native payload', () => {
  const preview={scope:'publish_copy_confirmation',items:[{slot_id:'story-slot',native_kind:'mix',
    display:{publish_title:'有来源的标题',publish_body:'已核对的正文',topics:['正文']}}]};
  const state={groups:[{style_id:'story',slots:[{slot_id:'story-slot'}]},{style_id:'persona',slots:[{slot_id:'other'}]}]};
  const before=JSON.stringify(preview);
  assert.match(humanReviewMarkup(preview,state),/第 1 条 · 故事型/);
  assert.match(humanReviewMarkup(preview,state),/发布正文/);
  assert.equal(JSON.stringify(preview),before);
});

test('batch history is an intent list and never guesses completed content from configuration', () => {
  const markup = batchHistoryMarkup({ batches: [{ batch_id: 'b&1', actual_target: 40, mode: 'stage', operating_stage: 'trust', control: 'resume' }], blocked: [] });
  assert.match(markup, /目标 40/); assert.match(markup, /batch_id=b%261/);
  assert.doesNotMatch(markup, /全部完成|已生成40|已批准40/);
  assert.match(batchHistoryMarkup(null), /无法可靠读取/);
  const p=projection(); p.verification_deferred=true;p.generation_quiescent=false;
  assert.equal(availableBatchPhases(p)[1],false);
  assert.doesNotMatch(batchDetailMarkup(p), /data-review-choice/);
  assert.match(batchDetailMarkup(p), /核对中/);
});

test('partial delivery includes only current confirmed Native parents',()=>{
  const ref={path:'exact',sha256:'a'.repeat(64)};
  const group=(id,publish)=>({publish,slots:[{slot_id:id,approved:true,native_exported:true}]});
  const value={...projection(),publish_copy_enabled:true,groups:[
    group('fresh',{confirmed:true,draft:{ref},delivery:{draft_ref:{...ref}}}),
    group('unconfirmed',{confirmed:false,draft:{ref},delivery:{draft_ref:ref}}),
    group('old-parent',{confirmed:true,draft:{ref},delivery:{draft_ref:{...ref,sha256:'b'.repeat(64)}}})]};
  assert.deepEqual(deliveryReadySlots(value).map(s=>s.slot_id),['fresh']);
  assert.deepEqual(batchDeliveryScope(value,deliveryReadySlots(value)),{scope:'explicit_legal_subset',slot_ids:['fresh']});
  const markup=batchWorkspaceMarkup(value,{phase:3,deliveryPreview:{delivered:1,shortfall:1,files:[{profile:'mix',rows:1}]}});
  assert.match(markup,/本次交付 1 条/);assert.match(markup,/差额 1 条/);assert.match(markup,/生成分类 Excel/);
});

test('ended partial batches allow review of retained results while active work remains fenced',()=>{
  const value={...projection(),control:'end',generation_quiescent:false,publish_copy_enabled:true};
  assert.equal(availableBatchPhases(value)[1],true);
  assert.equal(availableBatchPhases(value)[2],false); // No publish draft or prior approval.
  value.verification_deferred=true;
  assert.equal(availableBatchPhases(value)[1],false);
  assert.equal(availableBatchPhases(value)[2],false);
});

test('video deliveries and Native semantic/presentation results remain separate dimensions',()=>{
  const value=projection();value.counts={...value.counts,delivered:2,new_semantic_count:1,repurpose_presentation_count:1};
  const markup=batchDetailMarkup(value);
  assert.match(markup,/<dt>已交付<\/dt><dd>2/);
  assert.match(markup,/<dt>已登记新增内容<\/dt><dd>1/);
  assert.match(markup,/<dt>已登记重新表达<\/dt><dd>1/);
});

test('four-step journey highlights only the next explicit Human or delivery operation',()=>{
  const value={...projection(),publish_copy_enabled:true,generation_quiescent:false,status:'generating'};
  assert.equal(batchWorkflow(value).current,0);
  assert.equal(batchWorkflow(value).action,null);
  value.status='awaiting_review';value.generation_quiescent=true;value.counts.review_pending=2;
  assert.equal(batchWorkflow(value).current,1);
  assert.equal(batchWorkflow(value).action,'batch-review-content');
  const markup=batchDetailMarkup(value);
  for(const text of ['生成','内容审核','发布确认','Excel下载']) assert.ok(markup.includes(text));
  assert.doesNotMatch(markup,/开始内容审核|核对生成内容/);
  assert.match(markup,/aria-current="step"/);
  assert.doesNotMatch(markup,/value="approve" selected|type="checkbox"[^>]*checked/);
  value.counts.review_pending=0;value.counts.approved=2;value.status='preparing_publish_copy';
  assert.equal(batchWorkflow(value).current,2);assert.equal(batchWorkflow(value).action,null);
  value.status='awaiting_publish_confirmation';
  assert.equal(batchWorkflow(value).action,'batch-review-publish');
  value.status='preparing_delivery';
  assert.equal(batchWorkflow(value).current,3);assert.equal(batchWorkflow(value).action,null);
  const ref={path:'native-source',sha256:'a'.repeat(64)};
  value.groups=[{publish:{confirmed:true,draft:{ref},delivery:{draft_ref:{...ref}}},
    slots:[{slot_id:'s1',approved:true,native_exported:true}]}];
  value.status='ready_for_delivery';
  assert.equal(batchWorkflow(value).action,'batch-delivery-preview');
  value.counts.delivered=2;
  assert.equal(batchProgressSummary(value).full,false);
  assert.notEqual(batchWorkflow(value).action,'download');
  value.completion_proven=true;
  assert.equal(batchWorkflow(value).action,'download');
  assert.match(batchWorkspaceMarkup(value,{phase:3}),/Excel下载/);
});

test('unknown, stale or partial results retain gaps and do not skip pending Human gates',()=>{
  const value={...projection(),publish_copy_enabled:true,generation_quiescent:true};
  value.counts.review_pending=1;value.counts.missing_generation=1;
  value.status='generation_finished_with_gaps';
  value.deliveries={completed:[{is_current:true,files:[{profile:'news'}],delivered:1,shortfall:1}]};
  assert.equal(batchWorkflow(value).action,'batch-review-content');
  assert.match(batchWorkflow(value).steps[0].status,/差 1 条/);
  value.counts.unknown=1;
  assert.equal(batchWorkflow(value).action,'inspect');
  assert.equal(batchProgressSummary(value).full,false);
  value.counts.unknown=0;value.verification_deferred=true;
  assert.equal(batchWorkflow(value).action,null);
  value.verification_deferred=false;value.counts.review_pending=0;
  value.control='end';value.status='ended_partial';
  assert.equal(batchWorkflow(value).action,'download');
  assert.match(batchWorkflow(value).detail,/部分交付/);
  assert.equal(batchProgressSummary(value).full,false);
  value.deliveries.completed[0].is_current=false;value.counts.generated=0;
  assert.notEqual(batchWorkflow(value).action,'download');
});

test('partial or ended batches advance retained approved work to its independent Publish gate',()=>{
  for(const status of ['generation_finished_with_gaps','ended_partial']){
    const value={...projection(),publish_copy_enabled:true,generation_quiescent:true,status,
      counts:{...projection().counts,target:3,generated:2,approved:2,review_pending:0,missing_generation:1},
      groups:[{approved:2,publish:{confirmed:false,draft:{ref:{path:'exact',sha256:'a'.repeat(64)}}},slots:[{slot_id:'one',approved:true}]}]};
    if(status==='ended_partial')value.control='end';
    assert.equal(batchWorkflow(value).current,2);assert.equal(batchWorkflow(value).action,'batch-review-publish');
    assert.equal(batchProgressSummary(value).full,false);assert.match(batchDetailMarkup(value),/差 1 条/);
  }
});
