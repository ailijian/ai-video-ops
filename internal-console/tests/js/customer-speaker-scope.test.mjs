import test from 'node:test';
import assert from 'node:assert/strict';
import {updatePersonConfirmationScope,jointFinalPreview,bindCustomerSpeakerConfirmation} from '../../static/assets/customer-speaker-confirmation.mjs';

function scopeFixture() {
  const elements=Object.fromEntries(['title','note','toggle'].map(n=>[n,{textContent:'',hidden:false,disabled:false}]));
  const status={textContent:''},input={value:'保留已修改的本人职责',disabled:false};
  const section={querySelector:s=>s==='[data-business-only]'?elements.toggle:s==='[data-person-scope-title]'?elements.title:elements.note};
  const host={querySelectorAll:s=>s==='[data-person-scope-status]'?[status]:[input]};
  return {elements,status,input,section,host};
}

test('scope and person badges agree in both directions without discarding edited values',()=>{
  const f=scopeFixture();
  updatePersonConfirmationScope(f.section,f.host,{businessOnly:false});
  assert.match(f.elements.title.textContent,/一起确认/);assert.equal(f.elements.toggle.textContent,'出镜人稍后确认');
  assert.equal(f.status.textContent,'本次一起确认');
  updatePersonConfirmationScope(f.section,f.host,{businessOnly:true});
  assert.equal(f.elements.title.textContent,'本次仅确认客户');assert.equal(f.elements.toggle.textContent,'改为一起确认');
  assert.match(f.status.textContent,/稍后确认.*尚未批准/);assert.equal(f.input.disabled,true);
  updatePersonConfirmationScope(f.section,f.host,{businessOnly:false});
  assert.equal(f.input.disabled,false);assert.equal(f.input.value,'保留已修改的本人职责');
});

test('an empty selection does not advertise a joint approval or require a scope switch',()=>{
  const f=scopeFixture();updatePersonConfirmationScope(f.section,f.host,{businessOnly:false,empty:true});
  assert.equal(f.elements.title.textContent,'本次未选择出镜人');assert.equal(f.elements.toggle.hidden,true);
});

test('business-only summary identifies deferred people without implying a person receipt or repeating their facts',()=>{
  const people=[{name:'<本人>',facts:[{value:'不能重复显示的人物经历'}]}];
  const before=JSON.stringify(people);
  const html=jointFinalPreview({mode:'approve_business_profile'},()=>'<p>客户范围</p>',{businessOnly:true,deferredPeople:people});
  assert.match(html,/稍后确认的出镜人 · 1 位/);assert.match(html,/本次不批准/);assert.match(html,/&lt;本人&gt;/);
  assert.match(html,/出镜人资料保留/);assert.doesNotMatch(html,/本次一起确认|分别保存审核记录和审批收据|不能重复显示的人物经历/);
  assert.equal(JSON.stringify(people),before);
});

const turn=()=>new Promise(resolve=>setTimeout(resolve,220));
function element() { return {textContent:'',innerHTML:'',disabled:false,hidden:false,events:{},addEventListener(n,fn){this.events[n]=fn;}}; }

test('actual binding switches proposal and final button together, preserves edits, and never submits on a scope switch',async()=>{
  const originalDocument=globalThis.document,originalWindow=globalThis.window,originalCSS=globalThis.CSS;
  const title=element(),note=element(),toggle=element(),badge=element(),choice=element(),edit=element();
  choice.value='edit';edit.value='本人修订后的职责';
  const row={querySelector:s=>s==='[data-person-decision]'?choice:edit};
  const host={...element(),querySelector:()=>row,querySelectorAll(s){
    return s==='[data-person-scope-status]'?[badge]:s==='[data-person-decision]'?[choice]:s==='[data-person-edit]'?[edit]:s==='[data-person-decision], [data-person-edit]'?[choice,edit]:[];
  }};
  const section={...element(),isConnected:true,querySelector:s=>({'[data-person-scope-title]':title,'[data-person-scope-note]':note,'[data-business-only]':toggle,'[data-prepared-people]':host}[s]),querySelectorAll:()=>[]};
  const finalHost={...element(),querySelector:()=>element(),querySelectorAll:()=>[]},button=element(),consequence=element();
  const summary={before(){}},root={querySelector:s=>({'#customer-review-summary':summary,'#submit-fact-review':button,'[data-customer-final-preview]':finalHost,'[data-review-consequence]':consequence}[s]),querySelectorAll:()=>[]};
  const people=[{candidate_id:'p',name:'虚构出镜人',facts:[{candidate_id:'f',field:'speaker_role_facts',value:['原职责'],editable:true}]}];
  const requests=[];
  try {
    globalThis.document={createElement:()=>section};globalThis.window={};globalThis.CSS={escape:v=>v};
    bindCustomerSpeakerConfirmation({root,detail:{business_id:'fictional'},collect:()=>({speaker_confirmations:[{candidate_id:'p',selected:true}]}),render:()=>'<p>客户摘要</p>',reload(){},toast(){},
      api:async(url,options)=>{
        const body=JSON.parse(options.body);requests.push({url,body});
        if(url.endsWith('/review-preparation'))return {state:'prepared',people};
        return {mode:body.business_only?'approve_business_profile':'approve_customer_and_speakers',can_submit:true,
          preview_sha256:'a'.repeat(64),review_context:{token:'signed'},projection:{facts:{}},people:body.business_only?[]:people};
      }});
    await turn();
    assert.doesNotMatch(section.innerHTML,/本次暂不确认出镜人|customer-joint-options/);
    assert.equal(button.textContent,'确认客户与所选出镜人档案');
    toggle.events.click({currentTarget:toggle});assert.equal(button.disabled,true);await turn();
    assert.equal(title.textContent,'本次仅确认客户');assert.equal(button.textContent,'仅确认客户档案');
    assert.match(badge.textContent,/尚未批准/);assert.match(finalHost.innerHTML,/稍后确认的出镜人/);
    assert.deepEqual(requests.at(-1).body.speaker_fact_decisions,[]);
    toggle.events.click({currentTarget:toggle});await turn();
    assert.equal(button.textContent,'确认客户与所选出镜人档案');assert.equal(badge.textContent,'本次一起确认');
    assert.equal(edit.value,'本人修订后的职责');assert.equal(edit.disabled,false);
    assert.deepEqual(requests.at(-1).body.speaker_fact_decisions[0].decisions[0].edited_value,['本人修订后的职责']);
    assert.equal(requests.filter(r=>r.url.endsWith('/review-preparation')).length,1);
    assert.equal(requests.filter(r=>r.url.endsWith('/confirm')).length,0);
  } finally {globalThis.document=originalDocument;globalThis.window=originalWindow;globalThis.CSS=originalCSS;}
});
