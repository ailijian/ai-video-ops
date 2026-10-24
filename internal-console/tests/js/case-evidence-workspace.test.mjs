import test from "node:test";
import assert from "node:assert/strict";
import { evidenceWorkspace, evidenceEdits } from "../../static/assets/case-evidence-workspace.mjs";
import { caseReviewContent } from "../../static/assets/case-components.js";
import { reviewWorkspace, bindEvidenceWorkspace } from "../../static/assets/case-evidence-workspace.mjs";
const escape=s=>String(s??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll('"',"&quot;");
const space={state:"original",can_save:true,can_approve:true,narration:[{segment_id:"A1",start:0,end:2,
  original_text:"原词",effective_text:"原词"}],boundaries:[{frame_id:"F0",start:0,end:3,locked:true},
  {frame_id:"F3",start:3,end:6,locked:false}],frames:[{frame_id:"F0",seconds:0},{frame_id:"F1",seconds:1},{frame_id:"F3",seconds:3}],
  scope:{scope_sha256:"a".repeat(64),summary:{ordinary:3,explicit:0,blocked:0,keep_original:3,corrected_narration:0,adjusted_boundaries:0},items:[]}};
test("ordinary items have no mechanical keep checkboxes or default Human decision",()=>{
  const html=evidenceWorkspace(space,escape);
  assert.doesNotMatch(html,/checkbox|checked|data-evidence-kind/);
  assert.match(html,/最终确认范围：保留原识别 3 项/);
  assert.match(html,/data-save-evidence disabled/);
});
test("only explicit risks have a deliberate keep action; unknown risks remain blocked",()=>{
  const html=evidenceWorkspace({...space,scope:{...space.scope,items:[{kind:"narration",item_id:"narration:A1",mode:"explicit",start:0},
    {kind:"shot",item_id:"shot:F3",mode:"blocked",start:3}]}},escape);
  assert.equal((html.match(/type="checkbox"/g)||[]).length,1);
  assert.doesNotMatch(html,/checked/);
  assert.match(html,/不能统一批准/);
});
test("saved or failed edits show recovery and disable final approval",()=>{
  const pending={...space,state:"failed",can_save:false,can_approve:false,scope:null,message:"重新校验失败",build_task_id:"real-task"};
  const html=caseReviewContent({case_id:"7999999999999999901",title:"虚构",status:"awaiting_review",
    permissions:{can_review:true},review:{can_review:true},evidence_workspace:pending},()=>"");
  assert.match(html,/data-review-action="approve" disabled/);
  assert.match(html,/查看校验任务与恢复/);
  assert.doesNotMatch(html,/data-narration-edit/);
});
test("text corrections are escaped and exact unchanged values do not become edits",()=>{
  assert.match(evidenceWorkspace({...space,narration:[{...space.narration[0],effective_text:"<script>"}]},escape),/&lt;script>/);
  const input={value:"原词",dataset:{narrationEdit:"A1"}};
  const root={querySelectorAll:selector=>selector.includes("narration")?[input]:[]};
  assert.deepEqual(evidenceEdits(space,root),{narration_edits:[],boundary_edits:[]});
  input.value="原声修正";
  assert.deepEqual(evidenceEdits(space,root).narration_edits,[{segment_id:"A1",corrected_text:"原声修正",basis:"source_audio_listening",evidence_frame_refs:["F1"]}]);
});

test("unavailable v1.1 scope never renders legacy keep or an executable approval",()=>{
  for(const evidence_workspace of [undefined,{state:"unavailable",can_save:false,can_approve:false,scope:null}]){
    const detail={case_id:"7999999999999999901",permissions:{can_review:true},review:{can_review:true},
      approval_context:{version:"human-review-command-v1.1"},evidence_workspace,
      evidence_review:{required:true,available:true,narration_items:[{item_id:"A1",source_text:"原词"}],shot_items:[]}};
    const html=caseReviewContent(detail,()=>"");
    assert.match(html,/审核范围暂不可用/);
    assert.match(html,/已有分析（审核范围尚未恢复）/);
    assert.match(html,/恢复完整来源与依赖证据/);
    assert.match(html,/data-review-action="approve" disabled/);
    assert.doesNotMatch(html,/data-evidence-kind|type="checkbox"/);
    assert.equal(reviewWorkspace(detail).can_approve,false);
  }
});

test("unavailable scope refresh is actionable; frozen v1.0 page stays distinct",()=>{
  let clicked;
  bindEvidenceWorkspace({querySelector:()=>({addEventListener:(name,handler)=>{clicked=handler;}})},
    {evidence_workspace:{state:"unavailable"}}, {reload:()=>"refreshed"});
  assert.equal(clicked(),"refreshed");
  assert.equal(reviewWorkspace({approval_context:{version:"human-review-command-v1.0"}}),null);
  assert.equal(reviewWorkspace({review:{approval_recovery_required:true},approval_context:{version:"human-review-command-v1.1"}}),null);
});
