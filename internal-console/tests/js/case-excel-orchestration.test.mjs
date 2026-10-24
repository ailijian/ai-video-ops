import test from 'node:test';
import assert from 'node:assert/strict';
import { orchestrationInput,orchestrationPreviewMarkup,orchestrationResultMarkup,allPendingPreview,allPendingResult } from '../../static/assets/case-excel-orchestration.mjs';
import { safeExcelReturn } from '../../static/assets/routes.js';

test('finite selection preserves ordered exact Row references and rejects stale selections',()=>{
 const rows=[{row_id:'row_b',row_sha256:'b'.repeat(64)},{row_id:'row_a',row_sha256:'a'.repeat(64)}];
 const record={head_sha256:'c'.repeat(64),rows};
 const input=orchestrationInput(record,'save_one',rows,'orch_'+'a'.repeat(32));
 assert.deepEqual(input.selected_rows,rows);assert.equal(input.expected_import_head_sha256,record.head_sha256);
 for(const selected of [[],[rows[0],rows[0]],[{row_id:'row_foreign'}]])assert.throws(()=>orchestrationInput(record,'save_one',selected,'orch_'+'a'.repeat(32)));
 assert.throws(()=>orchestrationInput(record,'save_one',rows,'different'));
});

test('preview counts only new Tasks and clearly separates linked and source-pending Rows',()=>{
 const html=orchestrationPreviewMarkup({new_task_count:1,items:[{row:{row_id:'a'},relation:'new_task'},
  {row:{row_id:'b'},relation:'duplicate'},{row:{row_id:'c'},relation:'pending_source'}]}, {a:'<img src=x>'});
 assert.match(html,/计划新启动 <strong>1/);assert.match(html,/1 条已有来源、1 条待补证/);
 assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);assert.match(html,/不重复新建/);
});

test('admission completion never implies Human approval; unknown cannot offer a fresh model call',()=>{
 const html=orchestrationResultMarkup({schema_version:'case-excel-orchestration-result-projection-v1.0',control_state:'active',
  planned_new_task_count:1,actual_new_task_count:1,submission_complete:true,rows:[{title:'标题',state:'failed',error_code:'CASE_EXTERNAL_RESULT_UNKNOWN'}]});
 assert.match(html,/提交完成不代表审核通过/);assert.match(html,/原结果待核对，不自动重发/);
 assert.doesNotMatch(html,/data-finite-control|重新生成|全部审核通过/);
 assert.throws(()=>orchestrationResultMarkup({schema_version:'unknown'}));
});

test('pause and cancellation controls affect only unadmitted work',()=>{
 const value={schema_version:'case-excel-orchestration-result-projection-v1.0',planned_new_task_count:2,actual_new_task_count:1,
  submission_complete:false,rows:[],control_state:'paused'};
 assert.match(orchestrationResultMarkup(value),/继续未提交部分/);
 assert.doesNotMatch(orchestrationResultMarkup({...value,control_state:'cancelled'}),/data-finite-control/);
});

test('login recovery retains exact finite operation and rejects mixed row or foreign destinations',()=>{
 const base='/cases/excel-imports/import_'+'a'.repeat(32)+'?operation=save_one&view=cases&orchestration=orch_'+'b'.repeat(32);
 assert.equal(safeExcelReturn(base),base);
 assert.equal(safeExcelReturn(base+'&row=row_a'),null);
 assert.equal(safeExcelReturn(base.replace('orch_','invalid_')),null);
 assert.equal(safeExcelReturn('//evil.test'+base),null);
});

test('all source-pending rows are not described as completed analysis or a processed submission',()=>{
 const rows=[{state:'pending_source',task_id:null,title:'待补证'}];
 const result={schema_version:'case-excel-orchestration-result-projection-v1.0',control_state:'active',
  planned_new_task_count:0,actual_new_task_count:0,submission_complete:true,rows};
 assert.equal(allPendingResult(result),true);
 const html=orchestrationResultMarkup(result);
 assert.match(html,/1 条待补证，未启动解析/);assert.doesNotMatch(html,/本次解析提交已处理|data-finite-control/);
 assert.match(html,/未创建分析任务/);
 assert.equal(allPendingResult({...result,rows:[{state:'duplicate',task_id:null}]}),false);
 assert.equal(allPendingResult({...result,rows:[{state:'awaiting_review',task_id:'owned'}]}),false);
 assert.equal(allPendingResult({...result,rows:[]}),false);
 const preview={new_task_count:0,items:[{row:{row_id:'a'},relation:'pending_source'}]};
 assert.equal(allPendingPreview(preview),true);assert.match(orchestrationPreviewMarkup(preview,{}),/没有可提交解析的视频来源/);
 assert.equal(allPendingPreview({items:[{relation:'linked_owned_task'}]}),false);
});

test('withdrawal is distinct from incomplete sharing and offers no re-analysis or automatic re-publication',()=>{
 const base={schema_version:'case-excel-orchestration-result-projection-v1.0',planned_new_task_count:1,actual_new_task_count:1,submission_complete:true,control_state:'active'};
 const row={title:'原案例',state:'approved_pending_share',href:'/tasks/original',sharing_state:'approved_withdrawn'};
 const html=orchestrationResultMarkup({...base,rows:[row]});
 assert.match(html,/已收录 · 共享已撤回/);assert.match(html,/原收录记录保留/);assert.match(html,/无需重新解析/);
 assert.match(html,/指定审核人重新核对并明确确认/);assert.match(html,/查看收录与共享状态/);
 assert.doesNotMatch(html,/已收录待共享|data-finite-control|重新生成|确认共享展示/);
 const incomplete=orchestrationResultMarkup({...base,rows:[{...row,sharing_state:'approved_only',sharing_next_action:'请由指定审核人核对。'}]});
 assert.match(incomplete,/共享尚未完成/);assert.doesNotMatch(incomplete,/共享已撤回/);
 const stale=orchestrationResultMarkup({...base,rows:[{...row,sharing_state:'approved_reconfirm',sharing_next_action:'<script>重新核对</script>'}]});
 assert.match(stale,/展示内容待重新核对/);assert.doesNotMatch(stale,/<script>/);
 const legacy=orchestrationResultMarkup({...base,rows:[{state:'approved_pending_share'}]});
 assert.match(legacy,/共享状态待核对/);assert.doesNotMatch(legacy,/共享已撤回|已收录待共享/);
});
