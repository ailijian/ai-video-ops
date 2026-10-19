import test from 'node:test';
import assert from 'node:assert/strict';
import {preparedPeopleHTML,collectPersonDecisions,jointFinalPreview} from '../../static/assets/customer-speaker-confirmation.mjs';

const people=[{candidate_id:'person',name:'<人物>',public_role:'<身份>',facts:[
  {candidate_id:'name',field:'public_display_name',value:'<人物>',source_excerpt:'原始姓名',editable:false},
  {candidate_id:'role',field:'speaker_role_facts',value:['本人职责'],source_excerpt:'<本人原文>',editable:true}]}];

test('all person facts and original quotes are visible without approval checkboxes or unescaped markup',()=>{
  const html=preparedPeopleHTML(people);
  assert.match(html,/&lt;人物&gt;/);assert.match(html,/&lt;本人原文&gt;/);
  assert.match(html,/本人职责与经历/);assert.match(html,/企业或他人的经历不会自动归到/);
  assert.equal((html.match(/data-joint-fact=/g)||[]).length,2);
  assert.equal((html.match(/data-person-decision/g)||[]).length,1);
  assert.doesNotMatch(html,/<input|checkbox|human_gate/);
});

test('only displayed exact person rows produce proposed decisions; edits keep the original value type',()=>{
  globalThis.CSS={escape:v=>v};
  const host={querySelector(selector){return selector.includes('"name"')?{querySelector:()=>null}:{querySelector:s=>s==='[data-person-decision]'?{value:'edit'}:{value:'本人修改后的职责\n本人补充职责'}};}};
  const result=collectPersonDecisions(host,people);
  assert.equal(result[0].candidate_id,'person');assert.equal(result[0].decisions[0].decision,'approve');
  assert.deepEqual(result[0].decisions[1].edited_value,['本人修改后的职责','本人补充职责']);
  assert.throws(()=>collectPersonDecisions({querySelector:()=>null},people),/尚未完整显示/);
});

test('final joint scope names each person and preserves independent receipts and media rights',()=>{
  const value={mode:'approve_customer_and_speakers',people:[{name:'<人物>',projection:{facts:{speaker_role_facts:['本人职责']}}}]};
  const html=jointFinalPreview(value,()=>'<p>客户摘要</p>');
  assert.match(html,/客户摘要/);assert.match(html,/&lt;人物&gt;/);assert.match(html,/所选出镜人 · 1 位/);
  assert.doesNotMatch(html,/本人职责<|profile-rows/);assert.match(html,/data-review-section-target="customer-review-person-review"/);
  assert.match(html,/分别保存审核记录和审批收据/);assert.match(html,/不授予原始素材使用权/);
});
