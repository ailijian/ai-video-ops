import test from 'node:test';
import assert from 'node:assert/strict';
import {
  constraintReviewImpact, customerReviewConsequence, customerReviewGroups,
  customerConstraintReview, bindCustomerConstraintControls, bindCustomerReviewControls, createCustomerViews,
} from '../../static/assets/customer-views.js';

test('ordinary choices remain pending; risky adoption remains outside collapsed adjustments', () => {
  const items=[{candidate_id:'ordinary',field:'primary_products_or_services',value:['虚构服务'],source_excerpt:'准确原文',default_review_selection:'approve'},
    {candidate_id:'risk',field:'years_in_business',value:'未核实数字',source_excerpt:'未核实数字',review_exception_reason:'需要核实'}];
  const original=JSON.stringify(items),html=customerReviewGroups(items);
  assert.match(html,/data-review-row="ordinary" data-decision="approve"/);
  assert.match(html,/data-review-row="risk" data-decision=""/);
  const risk=html.slice(html.indexOf('data-review-row="risk"'));
  assert.ok(risk.indexOf('data-review-choice="approve"')<risk.indexOf('<details class="customer-fact-options"'));
  assert.doesNotMatch(risk.slice(0,risk.indexOf('<details')),/data-review-choice="approve" hidden/);
  assert.doesNotMatch(html,/<details class="customer-fact-options" open/);
  for(const action of ['edit','reject','']) assert.ok(html.includes(`data-review-choice="${action}"`));
  assert.equal(JSON.stringify(items),original);
});

test('consequences never imply that deferral or exclusion verifies a claim or removes core identity risk', () => {
  assert.match(constraintReviewImpact('unverified_claim','defer'),/暂不能批准/);
  assert.match(constraintReviewImpact('unverified_claim','exclude'),/不表示它已核实/);
  assert.match(constraintReviewImpact('identity_conflict','exclude'),/不会解除/);
  assert.match(constraintReviewImpact('identity_conflict','resolve'),/准确原文.*正式校验/);
  assert.match(constraintReviewImpact('conditional_fact','confirm'),/保留原有适用条件/);
  assert.match(customerReviewConsequence({conflicts:1,deferred:0,pending:0}),/主体冲突/);
  assert.match(customerReviewConsequence({conflicts:0,deferred:1,pending:0}),/暂不能批准/);
  assert.match(customerReviewConsequence({conflicts:0,deferred:0,pending:0}),/仍需分别批准/);
});

test('changing restriction choices updates only the preview and retains evidence input', () => {
  let change;const classes=new Set();
  const elements={
    '[data-constraint-action]':{value:'defer',addEventListener(_,fn){change=fn;}},
    '[data-constraint-status]':{},'[data-constraint-evidence-panel]':{},
    '[data-constraint-impact]':{textContent:'',classList:{toggle(k,on){if(on)classes.add(k);else classes.delete(k);}}},
    '[data-constraint-evidence]':{value:'尚未提交的来源'},
  };
  const row={dataset:{constraintId:'award'},querySelector(s){return elements[s];},classList:{toggle(){}}};
  const detail={constraint_candidates:[{constraint_id:'award',constraint_type:'unverified_claim',source:{evidence_quote:'奖项待核实'}}]};
  const original=JSON.stringify(detail);
  bindCustomerConstraintControls({querySelectorAll:()=>[row],querySelector:()=>null},detail);
  assert.equal(elements['[data-constraint-action]'].value,'defer');
  assert.match(elements['[data-constraint-impact]'].textContent,/暂不能批准/);
  elements['[data-constraint-action]'].value='exclude';change();
  assert.match(elements['[data-constraint-impact]'].textContent,/不表示它已核实/);
  assert.equal(elements['[data-constraint-status]'].textContent,'待统一确认');
  assert.equal(elements['[data-constraint-evidence]'].value,'尚未提交的来源');
  assert.equal(JSON.stringify(detail),original);
});

test('the source and human history are escaped and preserve the selected contract decisions', () => {
  const item={constraint_id:'award',constraint_type:'unverified_claim',source:{evidence_quote:'<script>虚构奖项</script>'}};
  const before=JSON.stringify(item),html=customerConstraintReview({constraint_candidates:[item]});
  assert.match(html,/value="defer" selected/);
  assert.doesNotMatch(html,/value="exclude" selected/);
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  assert.equal(JSON.stringify(item),before);
});

test('reading a review issues GETs only, shows limitations first and has one in-flow save action', async () => {
  let html='';const requests=[];
  const previous=globalThis.document;
  globalThis.document={querySelector:s=>s==='#submit-fact-review'?{addEventListener(){}}:null,querySelectorAll:()=>[]};
  const detail={business_id:'fictional',display_name:'虚构客户',status:'fact_review_required',fact_candidates:[
    {candidate_id:'one',field:'primary_products_or_services',value:['服务'],state:'requires_review',default_review_selection:'approve'}],
    constraint_candidates:[{constraint_id:'award',constraint_type:'unverified_claim',source:{evidence_quote:'奖项待核实'}}],
    speaker_candidates:[{candidate_id:'person-one',name:'AI 提取的称呼',speaker_type_hint:'owner_founder',
      confirmation:{selected:false,speaker_name:'本人核对名',public_role:'本人公开身份',speaker_type:'frontline_expert'},
      evidence_quotes:['<原始来源>']} ]};
  const original=JSON.stringify(detail);
  try {
    const view=createCustomerViews({app:{set innerHTML(v){html=v;}},api:async(url,options)=>{requests.push({url,options});return detail;},
      shell:(_,v)=>v,bindCommonActions(){},pageHeading:(_,v)=>`<h1>${v}</h1>`,skeletonPage(){},renderLoadError(_,e){throw e;}});
    await view.renderCustomerDetail('fictional');
    assert.ok(requests.length>0 && requests.every(x=>x.options===undefined));
    assert.ok(html.indexOf('id="customer-review-constraints"')<html.indexOf('id="customer-review-business"'));
    assert.equal((html.match(/id="submit-fact-review"/g)||[]).length,1);
    assert.doesNotMatch(html,/class="sticky-action review-submit-bar"/);
    assert.match(html,/data-review-consequence/);
    assert.doesNotMatch(html,/重点核对的异常/);
    assert.match(html,/确认出镜人/);
    for(const field of ['name','role','type']){
      assert.ok(html.includes(`for="speaker-person-one-${field}"`));
      assert.ok(html.includes(`id="speaker-person-one-${field}"`));
    }
    assert.doesNotMatch(html,/data-speaker-select checked/);
    assert.match(html,/value="frontline_expert" selected/);
    assert.match(html,/value="本人核对名"/);
    assert.match(html,/&lt;原始来源&gt;/);
    assert.match(html,/<blockquote>奖项待核实<\/blockquote>/);
    assert.doesNotMatch(html,/href="#customer-review-/);
    assert.match(html,/type="button" data-review-section-target="customer-review-business"/);
    assert.equal(JSON.stringify(detail),original);
  } finally {globalThis.document=previous;}
});

test('section navigation preserves unsaved choices without routing or issuing a request', () => {
  let click,focused=false,scrolled=false;
  const detail={fact_candidates:[],constraint_candidates:[],speaker_candidates:[]};
  const original=JSON.stringify(detail);
  const section={tabIndex:0,focus(options){assert.deepEqual(options,{preventScroll:true});focused=true;},
    scrollIntoView(options){assert.deepEqual(options,{block:'start'});scrolled=true;}};
  const root={querySelectorAll(s){return s==='[data-review-section-target]'?
    [{dataset:{reviewSectionTarget:'customer-review-business'},addEventListener(_,fn){click=fn;}}]:[];},
    querySelector:s=>s==='#customer-review-business'?section:null};
  bindCustomerReviewControls(detail,root);
  click();
  assert.ok(focused&&scrolled);
  assert.equal(JSON.stringify(detail),original);
});
