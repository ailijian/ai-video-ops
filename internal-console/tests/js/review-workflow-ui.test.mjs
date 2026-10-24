import assert from 'node:assert/strict';
import test from 'node:test';
import {amendmentPanel,bindingReviewPanel} from '../../static/assets/review-workflow-ui.mjs';
import {intakeItemState,intakeStage} from '../../static/assets/case-batch-submit.mjs';

test('correction displays only server-authorized fields and requires a bound command',()=>{
  const detail={business_id:'fictional',approval_context:{token:'opaque'},amendable_fields:['public_display_name'],
    business_persona:{facts:[{field:'public_display_name',value:'<unsafe title>'},{field:'forbidden_claims',value:['不可发布']}]}};
  const html=amendmentPanel(detail,'business',x=>x);
  assert.match(html,/data-amendment-form/);assert.doesNotMatch(html,/option value="forbidden_claims"/);
  assert.doesNotMatch(html,/<unsafe title>/);
  assert.equal(amendmentPanel({...detail,approval_context:null},'business',x=>x),'');
});
test('pending first Speaker has a separate explicit rebase action',()=>{
  const html=bindingReviewPanel({business_id:'fake-business'});
  assert.match(html,/type="checkbox" required/);assert.match(html,/仍需完成事实核对与档案批准/);
});
test('customer and speaker corrections have accessible labels, explicit disclosure state and the same evidence requirement',()=>{
  for(const kind of ['business','speaker']) {
    const detail={approval_context:{token:'must-not-render'},amendable_fields:['public_display_name'],
      [kind==='business'?'business_persona':'speaker_persona']:{facts:[{field:'public_display_name',value:'旧名称'}]}};
    const html=amendmentPanel(detail,kind,()=>'<姓名>');
    const id=kind==='business'?'customer-correction':'speaker-correction';
    for(const field of ['field','value','evidence']) {
      assert.ok(html.includes(`for="${id}-${field}"`));assert.ok(html.includes(`id="${id}-${field}"`));
    }
    assert.match(html,/correction-closed">展开/);assert.match(html,/correction-open">收起/);
    assert.match(html,/data-disclosure-affordance/);assert.match(html,/data-amend-evidence rows="3" required maxlength="2000"/);
    assert.match(html,/不会直接改写已批准档案/);assert.match(html,/&lt;姓名&gt;/);
    assert.doesNotMatch(html,/must-not-render|\bactor\b|<input|<姓名>/);
  }
});
test('a context without any allowed fields cannot expose correction controls',()=>{
  assert.equal(amendmentPanel({approval_context:{token:'signed'},amendable_fields:[],fact_candidates:[{field:'industry',value:'餐饮'}]},'business',v=>v),'');
});
test('neutral duplicate acknowledgement is terminal and never claims a running task',()=>{
  const item={state:'linked',task:null,case:null};
  assert.equal(intakeItemState(item),'submitted');assert.doesNotMatch(intakeStage(item),/等待|解析中/);
});
