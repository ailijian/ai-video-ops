import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createCaseViews } from '../../static/assets/case-views.js';
import { industryOptions } from '../../static/assets/case-industry.mjs';
import { UNCERTAIN_INDUSTRY, classificationDraft, classificationSubmittable, classificationDiffers,
  batchConfirmableItems, confirmedClassificationLabel, intakeCounts, intakeStage } from '../../static/assets/case-batch-submit.mjs';

const suggestion = { industry:'餐饮', observed_source_profile:'mix', industry_reason:'厨房与菜品线索',
  profile_reason:'连续口播配合多个画面', shot_refs:['S001','S002'] };
const pending = { position:0, state:'linked', case_id:'7999999999999999701',
  case:{title:'待检查的视频',status:'awaiting_review',duration_seconds:20},
  classification:{status:'needs_confirmation',can_confirm:true,suggestion} };
const confirmed = {...pending,classification:{...pending.classification,status:'confirmed',human:{industry:'零售',
  profile:'news',confirmed_by_phone:'19900001101',confirmed_at:'2026-10-09T12:00:00Z'}}};

function renderer(items) {
  const batchButton = {hidden:true,disabled:true,addEventListener(){}};
  const app = {innerHTML:'',querySelectorAll:()=>[],querySelector:()=>batchButton};
  const views = createCaseViews({app,api:async()=>({items}),shell:(_,html)=>html,
    pageHeading:()=>'',skeletonPage(){},bindCommonActions(){},showToast(){},
    renderLoadError:(_,error)=>{throw error;}});
  return {app,views,batchButton};
}

let render = renderer([confirmed]);
await render.views.renderIntakeGroup('group');
assert.doesNotMatch(render.app.innerHTML,/data-classify=|<select|type="checkbox"/,'confirmed result defaults to read-only');
assert.match(render.app.innerHTML,/data-edit-classify/);
assert.match(render.app.innerHTML,/btn btn-primary[^>]*[^]*?继续案例审核/);
assert.equal((render.app.innerHTML.match(/btn btn-primary/g)||[]).length,1,'one primary action on confirmed card');
assert.match(render.app.innerHTML,/<details class="intake-evidence">/,'full reasons/source are disclosed on demand');
assert.equal(render.batchButton.hidden,true);
render.views.dispose();

for (const [industry,profile,label] of [
  ['餐饮','mix','分类已确认'],
  [null,'uncertain','已确认，分类暂未确定'],
  ['餐饮','uncertain','分类已确认，部分信息待确定'],
  [null,'news','分类已确认，部分信息待确定'],
]) {
  const item={...confirmed,classification:{...confirmed.classification,human:{...confirmed.classification.human,industry,profile}}};
  assert.equal(confirmedClassificationLabel(item.classification.human),label);
  assert.equal(intakeStage(item),label);
  assert.equal(intakeCounts([item]).confirmed,1,'uncertainty does not create a new lifecycle status');
  render=renderer([item]);
  await render.views.renderIntakeGroup('group');
  assert.ok(render.app.innerHTML.includes(`<strong>${label}</strong>`));
  assert.match(render.app.innerHTML,/继续案例审核/,'unknown labels never block Human Review');
  assert.doesNotMatch(render.app.innerHTML,/data-classify=|<select|type="checkbox"/);
  assert.equal((render.app.innerHTML.match(/btn btn-primary/g)||[]).length,1);
  render.views.dispose();
}

render = renderer([pending]);
await render.views.renderIntakeGroup('group');
assert.match(render.app.innerHTML,/btn btn-primary[^>]*[^]*?确认分类/);
assert.doesNotMatch(render.app.innerHTML,/我已检查此视频的分类|保留行业未确定状态|type="checkbox"/);
assert.match(render.app.innerHTML,/value="__uncertain__"[^>]*>暂不确定/);
assert.match(render.app.innerHTML,/value="uncertain"[^>]*>暂不确定/);
assert.equal(render.batchButton.hidden,true,'single confirmation has no batch action');
render.views.dispose();

const unknown = classificationDraft({suggestion:{industry:null,observed_source_profile:'uncertain'}});
assert.equal(unknown.industry,'','system uncertainty is not a forged human field choice');
assert.equal(classificationSubmittable(unknown),false);
unknown.industry=UNCERTAIN_INDUSTRY;
assert.equal(classificationSubmittable(unknown),true,'explicit uncertainty is valid for an individual');
assert.equal(classificationSubmittable(unknown,{batch:true}),false);
assert.equal(classificationDiffers(unknown,{industry:null,observed_source_profile:'uncertain'}),false);
assert.equal(classificationDiffers({...unknown,industry:'零售',profile:'news'},suggestion),true);
assert.equal(classificationDiffers(classificationDraft({suggestion}),suggestion),false);
assert.equal(classificationDraft({human:{industry:null,profile:'uncertain'}}).industry,UNCERTAIN_INDUSTRY);
assert.match(industryOptions(UNCERTAIN_INDUSTRY,{uncertainValue:UNCERTAIN_INDUSTRY}),/value="__uncertain__" selected/);
assert.doesNotMatch(industryOptions(UNCERTAIN_INDUSTRY,{uncertainValue:UNCERTAIN_INDUSTRY}),/value="__custom__" selected/);

const drafts = new Map([[0,{industry:'餐饮',profile:'mix',checked:false}]]);
assert.equal(batchConfirmableItems([pending],drafts).length,0,'unreviewed rows cannot enable batch confirmation');
drafts.get(0).checked=true;
assert.equal(batchConfirmableItems([pending],drafts).length,1);
assert.equal(batchConfirmableItems([confirmed],drafts).length,0,'confirmed rows cannot be submitted again in bulk');
drafts.get(0).industry=UNCERTAIN_INDUSTRY;
assert.equal(batchConfirmableItems([pending],drafts).length,0);

render=renderer([{...pending,case:{status:'approved'}},{state:'linked',task:{status:'completed'}}]);
await render.views.renderIntakeGroup('group');
assert.match(render.app.innerHTML,/已入库/);
assert.match(render.app.innerHTML,/任务已结束/);
assert.doesNotMatch(render.app.innerHTML,/>已完成</);
render.views.dispose();

// Exercise real change/submit handlers: one reminder, no explanation/checkbox,
// no premature write, then one audited classification request.
const handlers={},notices=[],requests=[];
const fields={industry:{value:'餐饮'},custom:{value:'',disabled:true,hidden:true},profile:{value:'mix'},button:{disabled:false}};
const form={dataset:{classify:'0'},addEventListener:(event,fn)=>{handlers[event]=fn;},querySelector:selector=>
  ({'[data-industry]':fields.industry,'[data-custom]':fields.custom,'[data-profile]':fields.profile,'button':fields.button}[selector]||null)};
const batchButton={hidden:true,disabled:true,addEventListener(){}};
let active=pending;
const app={innerHTML:'',querySelector:()=>batchButton,querySelectorAll:selector=>
  selector==='[data-classify]'&&app.innerHTML.includes('data-classify=')?[form]:[]};
const views=createCaseViews({app,shell:(_,html)=>html,pageHeading:()=>'',skeletonPage(){},bindCommonActions(){},
  showToast:text=>notices.push(text),renderLoadError:(_,error)=>{throw error;},api:async(url,options)=>{
    if(options?.method==='POST'){
      requests.push({url,payload:JSON.parse(options.body)});
      active={...confirmed};
    }
    return {items:[active]};
  }});
await views.renderIntakeGroup('group');
fields.industry.value='零售';handlers.change();
fields.profile.value='news';handlers.input();handlers.change();
assert.equal(notices.filter(text=>text.includes('系统建议不同')).length,1);
assert.equal(requests.length,0,'editing and a reminder do not save or approve');
await handlers.submit({preventDefault(){}});
assert.equal(requests.length,1);
assert.equal(requests[0].url,`/api/cases/${pending.case_id}/classification`);
assert.equal(requests[0].payload.industry,'零售');
assert.equal(requests[0].payload.profile,'news');
assert.ok(!('reason' in requests[0].payload)&&!('actor_user_id' in requests[0].payload));
assert.doesNotMatch(app.innerHTML,/data-classify=|<select/);
views.dispose();

const css=readFileSync(new URL('../../static/assets/styles.css',import.meta.url),'utf8');
assert.match(css,/\.intake-results-page, \.add-case-page[^}]*padding-bottom:calc\(96px \+ env\(safe-area-inset-bottom\)\)/);
assert.match(css,/\.intake-result-card \.btn[^}]*min-height:44px[^}]*scroll-margin-block/);
console.log('CASE_SMART_INTAKE_POLISH_V11_PASS');
