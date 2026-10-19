import test from 'node:test';
import assert from 'node:assert/strict';
import {bindFinalCustomerConfirmation} from '../../static/assets/customer-final-confirmation.mjs';
import {customerFinalPreview} from '../../static/assets/customer-views.js';

const turn = () => new Promise(resolve=>setTimeout(resolve,5));
const preview = mode=>({mode,can_submit:true,preview_sha256:'a'.repeat(64),review_context:{token:'signed-test-context'},projection:{facts:{public_display_name:'虚构客户'},constraints:[]}});
function page(api,mode='approve_business_profile', options={}) {
  const events={},statusEvents={};
  const statusButton={addEventListener:(n,fn)=>{statusEvents[n]=fn;}};
  const host={innerHTML:'',querySelector:()=>statusButton,querySelectorAll:()=>[]};
  const button={disabled:false,textContent:'',addEventListener:(n,fn)=>{events[n]=fn;}};
  const consequence={textContent:''};
  let payload={review_context:'source',decisions:[{candidate_id:'one',decision:'approve'}]},reloads=0;
  const root={querySelector:s=>s==='#submit-fact-review'?button:s==='[data-review-consequence]'?consequence:host,querySelectorAll:()=>options.inputs || []};
  const requests=[];
  const changed=bindFinalCustomerConfirmation({root,detail:{business_id:'fictional'},collect:()=>payload,
    api:async(url,opts)=>{requests.push({url,body:JSON.parse(opts.body)});return api?api(url,opts):preview(mode);},
    render:customerFinalPreview,reload:async()=>{reloads++;},toast(){},getBusinessOnly:options.getBusinessOnly,delay:0});
  return {host,button,consequence,changed,requests,click:()=>events.click(),status:()=>statusEvents.click?.(),
    setPayload:v=>{payload=v;},get reloads(){return reloads;}};
}

test('rendering and previews cannot approve; one explicit click submits the signed exact decision',async()=>{
  globalThis.window={__customerReviewDirty:true};
  const p=page(url=>url.endsWith('/review-preview')?preview('approve_business_profile'):{execution:{completion:'business_approved'}});
  await turn();
  assert.equal(p.requests.length,1);assert.match(p.requests[0].url,/review-preview$/);
  assert.equal(p.button.textContent,'确认资料并批准客户档案');assert.equal(p.button.disabled,false);
  await Promise.all([p.click(),p.click()]);
  const submits=p.requests.filter(v=>v.url.endsWith('/confirm'));
  assert.equal(submits.length,1);
  assert.deepEqual(submits[0].body,{review_context:'signed-test-context',preview_sha256:'a'.repeat(64),confirmation:'approve_business_profile'});
  assert.equal(p.reloads,1);assert.equal(window.__customerReviewDirty,false);
});

test('preview failure disables confirmation and never falls back to a legacy approval',async()=>{
  const p=page(()=>{throw new Error('来源 <不完整>');});await turn();
  assert.equal(p.button.disabled,true);assert.match(p.host.innerHTML,/&lt;不完整&gt;/);
  await p.click();assert.equal(p.requests.length,1);
});

test('an unobserved local edit cannot submit an old signed preview',async()=>{
  const p=page();await turn();
  p.setPayload({review_context:'source',decisions:[]});await p.click();
  assert.equal(p.requests.filter(v=>v.url.endsWith('/confirm')).length,0);
  assert.match(p.consequence.textContent,/确认范围已变化/);
  await turn();
});

test('a late response cannot replace the preview for newer input',async()=>{
  const resolve=[];const p=page(()=>new Promise(done=>resolve.push(done)));
  p.changed();await turn();assert.equal(resolve.length,2);
  resolve[1](preview('save_review_progress'));await turn();
  resolve[0](preview('approve_business_profile'));await turn();
  assert.equal(p.button.textContent,'保存核对进度');assert.match(p.consequence.textContent,/不会批准/);
});

test('blocked review explicitly saves progress and never sends an approval decision',async()=>{
  globalThis.window={};
  const p=page(url=>url.endsWith('/review-preview')?preview('save_review_progress'):{execution:{completion:'review_saved'}});
  await turn();await p.click();
  assert.equal(p.requests.find(v=>v.url.endsWith('/confirm')).body.confirmation,'save_review_progress');
});

test('an interrupted submit offers status and recovery without automatically replaying approval',async()=>{
  const p=page(url=>{if(url.endsWith('/confirm'))throw new Error('保存中断');return preview('approve_business_profile');});
  await turn();await p.click();
  assert.equal(p.button.disabled,true);assert.match(p.host.innerHTML,/查看当前状态与恢复入口/);
  assert.equal(p.requests.filter(v=>v.url.endsWith('/confirm')).length,1);
  await p.status();assert.equal(p.reloads,1);
});

test('the compact final scope retains exclusion decisions and links to the original source' ,()=>{
  const v=preview('approve_business_profile');v.projection.constraints=[{constraint_type:'unverified_claim',decision:'exclude',source:{evidence_quote:'<奖项尚未核实>'}}];
  const html=customerFinalPreview(v);
  assert.match(html,/明确排除此项宣传/);assert.doesNotMatch(html,/<奖项尚未核实>|&lt;奖项尚未核实&gt;/);
  assert.match(html,/data-review-section-target="customer-review-constraints"/);
  assert.match(html,/出镜人本人资料仍需独立审核/);
});

test('one joint final action sends the explicit customer and selected people decision',async()=>{
  globalThis.window={__customerReviewDirty:true};
  const value={...preview('approve_customer_and_speakers'),schema_version:'customer-final-confirmation-v1.1',people:[{name:'虚构人物'}]};
  const p=page(url=>url.endsWith('/review-preview')?value:{execution:{completion:'customer_and_speakers_approved'}});
  await turn();
  assert.equal(p.button.textContent,'确认客户与所选出镜人档案');
  assert.match(p.consequence.textContent,/1 位所选出镜人/);
  await Promise.all([p.click(),p.click()]);
  const submits=p.requests.filter(v=>v.url.endsWith('/confirm'));
  assert.equal(submits.length,1);assert.equal(submits[0].body.confirmation,'approve_customer_and_speakers');
  assert.equal(p.reloads,1);
});


test('business-only scope is explicit and switching is frozen during the final request',async()=>{
  globalThis.window={};let finish;
  const scopeButton={disabled:false};
  const p=page(url=>url.endsWith('/review-preview')?preview('approve_business_profile'):new Promise(resolve=>{finish=resolve;}),
    'approve_business_profile',{getBusinessOnly:()=>true,inputs:[scopeButton]});
  await turn();
  assert.equal(p.button.textContent,'仅确认客户档案');assert.match(p.consequence.textContent,/出镜人稍后确认，本次不会批准/);
  const operation=p.click();assert.equal(scopeButton.disabled,true);
  finish({execution:{completion:'business_approved'}});await operation;
  assert.equal(p.requests.filter(v=>v.url.endsWith('/confirm')).length,1);
  assert.equal(p.requests.find(v=>v.url.endsWith('/confirm')).body.confirmation,'approve_business_profile');
});
