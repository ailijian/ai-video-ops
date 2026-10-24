import test from 'node:test';
import assert from 'node:assert/strict';
import {speakerReviewMarkup,collectSpeakerDecisions,bindSpeakerFinalConfirmation} from '../../static/assets/speaker-final-confirmation.mjs';

const turn=()=>new Promise(resolve=>setTimeout(resolve,5));
const fact=(id,risk=false)=>({candidate_id:id,field:risk?'role_scope_constraints':'speaker_role_facts',state:'requires_review',value:['本人实际职责'],source_excerpt:'本人提供的资料',default_review_selection:risk?null:'approve'});
const bundle=(can_submit=true)=>({schema_version:'speaker-final-confirmation-v1.0',mode:'approve_speaker_profile',can_submit,
  preview_sha256:'a'.repeat(64),review_context:{token:'signed-preview'},projection:{facts:{speaker_role_facts:['本人实际职责']}},blockers:can_submit?[]:['仍需重点核对']});
function page(api,options={}) {
  globalThis.CSS={escape:v=>v};globalThis.window={__customerReviewDirty:false};
  const candidates=options.complete?[]:[fact('ordinary'),fact('boundary',true)],rows=new Map(),events={},statusEvents={};
  for(const f of candidates){const select={value:f.default_review_selection || '',disabled:false,events:{},addEventListener(n,fn){this.events[n]=fn;},closest:()=>row};
    if(options.readyRisk)select.value='approve';
    const input={value:'本人实际职责',disabled:false,addEventListener(){}};
    const edit={hidden:true};const row={select,input,querySelector:s=>s==='[data-speaker-decision]'?select:s==='[data-speaker-edit]'?input:edit};rows.set(f.candidate_id,row);}
  const status={addEventListener:(n,fn)=>{statusEvents[n]=fn;}};
  const host={innerHTML:'',querySelector:()=>status,querySelectorAll:()=>[]};
  const button={disabled:false,textContent:'',addEventListener:(n,fn)=>{events[n]=fn;}};
  const root={isConnected:true,querySelector:s=>s==='[data-confirm-speaker]'?button:s==='[data-speaker-final-preview]'?host:rows.get(s.match(/data-speaker-review-row="(.*?)"/)?.[1]),
    querySelectorAll:s=>s==='[data-speaker-decision]'?[...rows.values()].map(v=>v.select):s==='[data-speaker-edit]'?[...rows.values()].map(v=>v.input):s==='input,select,textarea'?[...rows.values()].flatMap(v=>[v.select,v.input]):[]};
  const detail={business_id:'fictional',speaker_id:'person',status:options.complete?'persona_review_required':'fact_review_required',approval_context:{token:'source'},fact_candidates:candidates};
  let reloads=0;const requests=[];
  const changed=bindSpeakerFinalConfirmation({root,detail,delay:0,api:async(url,opts)=>{requests.push({url,body:JSON.parse(opts.body)});return api?api(url,opts):bundle();},reload:async()=>{reloads++;},toast(){}});
  return {root,rows,host,button,changed,requests,detail,click:()=>events.click(),status:()=>statusEvents.click(),get reloads(){return reloads;}};
}

test('concentrated review uses adjustable ordinary choices and explicit risk choices without repeated row confirmation buttons',()=>{
  const html=speakerReviewMarkup({status:'fact_review_required',fact_candidates:[fact('normal'),{...fact('risk',true),value:['<身份>']} ]});
  assert.match(html,/待统一确认/);assert.match(html,/需要重点核对/);assert.match(html,/请选择核对结果/);
  assert.match(html,/data-confirm-speaker/);assert.doesNotMatch(html,/data-review-choice|确认这些信息/);
  assert.match(html,/&lt;身份&gt;/);assert.doesNotMatch(html,/<身份>/);
});

test('collection preserves ordinary preselection, requires a real risk choice and includes exact edited values',()=>{
  const p=page();
  assert.equal(collectSpeakerDecisions(p.root,p.detail).length,1);
  p.rows.get('boundary').select.value='approve';p.rows.get('ordinary').select.value='edit';p.rows.get('ordinary').input.value='真实职责一\n真实职责二';
  const values=collectSpeakerDecisions(p.root,p.detail);
  assert.deepEqual(values[0].edited_value,['真实职责一','真实职责二']);assert.equal(values[1].decision,'approve');
});

test('sourced protective boundaries join the single confirmation; saved limits have no repeated choice',()=>{
  const boundary={...fact('safe'),field:'role_scope_constraints',protective_scope:true,value:['只讲本人实际参与的工作']};
  const retained={candidate_id:'saved',field:'first_person_forbidden_claims',state:'known_candidate',value:['不得声称自己是兽医']};
  const html=speakerReviewMarkup({status:'fact_review_required',fact_candidates:[fact('ordinary'),boundary,retained]});
  assert.match(html,/表达边界/);assert.match(html,/待本次确认/);assert.match(html,/无需逐项选择/);
  assert.match(html,/已确认限制 · 持续保留/);assert.match(html,/不得声称自己是兽医/);
  assert.doesNotMatch(html,/重点核对|请选择核对结果|data-speaker-review-row="saved"/);
  assert.equal((html.match(/data-confirm-speaker/g)||[]).length,1);
});

test('unrecognised or conflicting boundaries still show a visible blank exception choice',()=>{
  const html=speakerReviewMarkup({status:'fact_review_required',fact_candidates:[fact('boundary',true)]});
  assert.match(html,/id="speaker-review-risks"/);assert.match(html,/<option value="" selected>请选择核对结果/);
  assert.doesNotMatch(html,/无需逐项选择/);
});

test('only an explicit final click submits the exact signed approval once and freezes choices',async()=>{
  let finish;const p=page(url=>url.endsWith('/review-preview')?bundle():new Promise(resolve=>{finish=resolve;}),{readyRisk:true});
  await turn();
  assert.equal(p.requests.length,1);assert.equal(p.button.textContent,'确认资料并批准出镜人档案');
  const first=p.click();await p.click();assert.equal(p.rows.get('ordinary').select.disabled,true);
  finish({execution:{completion:'speaker_approved'}});await first;
  assert.equal(p.requests.filter(v=>v.url.endsWith('/confirm')).length,1);
  assert.deepEqual(p.requests[1].body,{review_context:'signed-preview',preview_sha256:'a'.repeat(64),confirmation:'approve_speaker_profile'});
  assert.equal(p.reloads,1);assert.equal(window.__customerReviewDirty,false);
});

test('a blocked or failed preview cannot submit or fall back to old review/approval routes',async()=>{
  for(const response of [()=>bundle(false),()=>{throw Error('<无法读取>');}]){
    const p=page(response);await turn();assert.equal(p.button.disabled,true);await p.click();
    assert.equal(p.requests.length,1);assert.doesNotMatch(p.requests[0].url,/facts\/review|persona\/approve/);
  }
});

test('an unobserved local edit invalidates the old preview before submission',async()=>{
  const p=page();await turn();p.rows.get('ordinary').select.value='reject';await p.click();await turn();
  assert.equal(p.requests.filter(v=>v.url.endsWith('/confirm')).length,0);assert.equal(p.requests.length,2);
});

test('late preview responses cannot replace newer decisions or a departed page',async()=>{
  const resolve=[];const p=page(()=>new Promise(done=>resolve.push(done)));
  p.changed();await turn();resolve[1](bundle(false));await turn();resolve[0](bundle());await turn();
  assert.equal(p.button.disabled,true);assert.equal(p.button.textContent,'请先完成重点核对');
  const q=page(()=>new Promise(done=>resolve.push(done)));q.root.isConnected=false;resolve[2](bundle());await turn();
  assert.equal(q.button.disabled,true);
});

test('interrupted submission offers original recovery without automatic resubmission or another approval',async()=>{
  const p=page(url=>{if(url.endsWith('/confirm'))throw Error('synthetic interruption');return bundle();});
  await turn();window.__customerReviewDirty=true;await p.click();assert.equal(p.button.disabled,true);assert.match(p.host.innerHTML,/查看当前状态与恢复入口/);
  assert.equal(p.requests.filter(v=>v.url.endsWith('/confirm')).length,1);await p.status();assert.equal(p.reloads,1);
  assert.equal(window.__customerReviewDirty,false,'A replaced saved-operation form must not leave a false unsaved-changes warning');
});

test('an already completed fact review is displayed once and submits no replacement fact decisions',async()=>{
  const p=page(undefined,{complete:true});await turn();assert.deepEqual(p.requests[0].body.decisions,[]);
  const html=speakerReviewMarkup({...p.detail,speaker_persona:{facts:[{field:'public_display_name',state:'known',value:'虚构人物'}]}});
  assert.match(html,/虚构人物/);assert.doesNotMatch(html,/data-speaker-decision/);
});
