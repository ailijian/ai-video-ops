import test from 'node:test';
import assert from 'node:assert/strict';
import {customerFinalPreview} from '../../static/assets/customer-views.js';
import {jointFinalPreview} from '../../static/assets/customer-speaker-confirmation.mjs';
import {enhanceReviewDisclosures,bindReviewReturnLinks} from '../../static/assets/customer-review-presentation.mjs';

const sample = () => ({schema_version:'customer-final-confirmation-v1.1',mode:'approve_customer_and_speakers',
  blockers:[],projection:{facts:{public_display_name:'完整客户资料仅在上方',industry:'餐饮'},constraints:[
    {constraint_type:'unverified_claim',decision:'exclude',source:{evidence_quote:'原文完整奖项材料'}},
    {constraint_type:'conditional_fact',decision:'confirm',condition:'以当次确认为准'}]},
  people:[{name:'<所选人物>',projection:{facts:{public_role:'店主',speaker_role_facts:['只在上方显示的本人经历']}}}]});

test('confirmation summarizes the exact server projection without duplicating full customer/person materials',()=>{
  const value=sample(),before=JSON.stringify(value),html=jointFinalPreview(value,customerFinalPreview);
  assert.match(html,/客户信息<\/dt><dd>2 项/);assert.match(html,/保留限制<\/dt><dd>2 项/);
  assert.match(html,/待处理条件<\/dt><dd>0 项/);assert.match(html,/所选出镜人 · 1 位/);
  assert.match(html,/&lt;所选人物&gt;/);assert.match(html,/店主/);
  assert.match(html,/明确排除此项宣传/);assert.match(html,/以当次确认为准/);
  assert.doesNotMatch(html,/完整客户资料仅在上方|原文完整奖项材料|只在上方显示的本人经历|profile-rows|<input/);
  for(const section of ['business','constraints','person-review']) assert.ok(html.includes(`data-review-section-target="customer-review-${section}"`));
  assert.equal(JSON.stringify(value),before);
});

test('blocked and progress-only modes retain explicit blockers and never imply approval',()=>{
  const value=sample();value.mode='save_review_progress';value.blockers=['critical_constraints','人物：<来源不完整>'];
  const html=jointFinalPreview(value,customerFinalPreview);
  assert.match(html,/待处理条件<\/dt><dd>2 项/);assert.match(html,/重要限制仍需处理/);
  assert.match(html,/&lt;来源不完整&gt;/);assert.match(html,/不会批准客户或人物档案/);
  assert.match(html,/尚未批准/);assert.doesNotMatch(html,/本次一起确认/);
});

test('empty business-only summary does not invent facts, restrictions or selected speakers',()=>{
  const html=jointFinalPreview({mode:'save_review_progress',projection:{facts:{},constraints:[]}},customerFinalPreview);
  assert.match(html,/客户信息<\/dt><dd>0 项/);
  assert.doesNotMatch(html,/所选出镜人|返回查看重要限制/);
  assert.match(html,/出镜人本人资料仍需独立审核/);
});

test('disclosure enhancement is idempotent and preserves native state and existing controls',()=>{
  let added=0;const classes=new Set();
  const summary={open:false,querySelector:()=>added?{}:null,ownerDocument:{createElement:()=>({dataset:{}})},
    classList:{add:v=>classes.add(v)},append(hint){added++;assert.match(hint.innerHTML,/展开/);assert.match(hint.innerHTML,/收起/);assert.match(hint.innerHTML,/aria-hidden="true"/);}};
  const root={querySelectorAll:s=>{assert.equal(s,'details > summary');return [summary];}};
  enhanceReviewDisclosures(root);enhanceReviewDisclosures(root);
  assert.equal(added,1);assert.equal(summary.open,false);assert.ok(classes.has('customer-disclosure-summary'));
});

test('return to original customer information opens saved facts without saving, routing or changing a choice',()=>{
  let click;const known={open:false};let focused=false,scrolled=false;
  const button={dataset:{reviewSectionTarget:'customer-review-business'},addEventListener:(event,fn)=>{assert.equal(event,'click');click=fn;}};
  const section={querySelector:()=>known,focus:()=>{focused=true;},scrollIntoView:()=>{scrolled=true;}};
  bindReviewReturnLinks({querySelectorAll:()=>[button]},{querySelector:s=>s==='#customer-review-business'?section:null});
  click();assert.ok(known.open&&focused&&scrolled);
});
