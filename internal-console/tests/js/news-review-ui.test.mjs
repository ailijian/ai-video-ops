import assert from 'node:assert/strict';
import test from 'node:test';
import {createNovelNewsViews} from '../../static/assets/novel-news-views.js';
import {bindContentReviewControls,ContentReviewItem} from '../../static/assets/creation-components.js';

const texts=['午餐套餐29元，仅限到店自取，不含配送','下单时单独核对忌口','套餐含一份主食与两份蔬菜','门店提供密封餐盒'];
const original={stage:'review',beats:texts.map((text,i)=>({beat_id:`B00${i+1}`,order:i+1,text,
  semantic_role:i===0?'price_offer_first_semantic_anchor':'grounded_information',source_fact_refs:[`fact_${i}`]})),
  source_facts:Object.fromEntries(texts.map((t,i)=>[`fact_${i}`,t]))};
function element(extra={}) {return {dataset:{},isConnected:true,disabled:false,
  addEventListener(event,fn){this[event]=fn;},...extra};}
function row(beat) {
  const editor={hidden:true},input={value:beat.text},radios=[];
  for(const value of ['approved','revised','rejected']) {
    let checked=value==='approved';
    const radio=element({value,disabled:value==='rejected'&&beat.order===1});
    Object.defineProperty(radio,'checked',{get:()=>checked,set:active=>{
      if(active)for(const other of radios)if(other!==radio)other.checked=false;
      checked=active;
    }});radios.push(radio);
  }
  return {dataset:{itemId:beat.beat_id},editor,input,radios,
    querySelector(selector){
      if(selector==='input[data-content-decision]:checked')return radios.find(r=>r.checked)||null;
      if(selector==='input[data-content-decision][value="approved"]')return radios[0];
      if(selector==='[data-content-revision-editor]')return editor;
      if(selector==='[data-revised-title]')return input;return null;
    },querySelectorAll:()=>radios,
  };
}
async function fixture(behavior=async()=>{}) {
  let state=structuredClone(original),html='',rows=[];
  let submit,progress;
  const calls=[],toasts=[];
  const host={get innerHTML(){return html;},set innerHTML(value){html=value;
    rows=state.stage==='review'?state.beats.map(row):[];
    submit=element({disabled:true});progress={};
  },querySelectorAll(selector){return selector==='[data-content-review-item]'?rows:[];},
  querySelector(selector){
    if(!html.includes('data-submit-novel-review'))return null;
    return ({'[data-submit-novel-review]':submit,'[data-novel-review-progress]':progress})[selector]||null;
  }};
  const view=createNovelNewsViews({escapeHtml:String,showToast:t=>toasts.push(t),api:async(path,options)=>{
    calls.push({path,body:options?.body&&JSON.parse(options.body),method:options?.method});
    if(options?.method==='POST') {
      await behavior(calls.at(-1));state={stage:'export'};return {};
    }return {state};
  }});
  await view.restore('gen_original_A',host);
  return {view,host,calls,toasts,get rows(){return rows;},get html(){return html;},get submit(){return submit;},get progress(){return progress;},
    choose(index,value){const radio=rows[index].radios.find(r=>r.value===value);assert.equal(radio.disabled,false);radio.checked=true;radio.change();}};
}

test('shared review defaults to pass locally and waits for one explicit native submission',async()=>{
  const f=await fixture();assert.equal(f.progress.textContent,'当前选择：通过 4 · 修改 0 · 不采用 0');assert.equal(f.submit.disabled,false);
  for(const text of texts)assert.ok(f.html.includes(text));
  assert.equal((f.html.match(/data-content-review-item/g)||[]).length,4);
  assert.equal((f.html.match(/<h2>审核新闻体<\/h2>/g)||[]).length,1);
  assert.equal((f.html.match(/value="approved" checked/g)||[]).length,4);
  assert.doesNotMatch(f.html,/<fieldset|Beat 1|添加审核备注|全部通过|已处理/);
  assert.match(f.html,/查看来源事实/);assert.match(f.html,/creation-action-bar/);
  assert.ok(f.rows[0].radios.find(r=>r.value==='rejected').disabled);
  assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
  await f.submit.click({currentTarget:f.submit});assert.equal(f.calls.filter(c=>c.method==='POST').length,1);
  assert.ok(f.calls.find(c=>c.method==='POST').body.decisions.every(d=>d.decision==='approved'));
});

test('individual changes are local and selection statistics do not imply completed review',async()=>{
  const f=await fixture();f.choose(1,'revised');assert.equal(f.rows[1].editor.hidden,false);
  assert.equal(f.rows[1].input.value,texts[1]);assert.equal(f.progress.textContent,'当前选择：通过 3 · 修改 1 · 不采用 0');
  f.choose(1,'approved');assert.equal(f.progress.textContent,'当前选择：通过 4 · 修改 0 · 不采用 0');assert.equal(f.submit.disabled,false);
  assert.equal(f.rows[1].editor.hidden,true);assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
  await f.view.restore('gen_original_A',f.host);assert.equal(f.progress.textContent,'当前选择：通过 4 · 修改 0 · 不采用 0');
});

test('submission preserves original beat IDs and legacy raw revised_text identity',async()=>{
  const f=await fixture();f.choose(1,'revised');f.rows[1].input.value=' 下单时核对忌口需求 ';
  await f.submit.click({currentTarget:f.submit});
  const post=f.calls.filter(c=>c.method==='POST');assert.equal(post.length,1);
  assert.equal(post[0].path,'/api/create/novel-news/gen_original_A/review');
  assert.deepEqual(post[0].body,{decisions:original.beats.map((b,i)=>({beat_id:b.beat_id,decision:i===1?'revised':'approved',
    revised_text:i===1?' 下单时核对忌口需求 ':b.text}))});
});

test('four-to-eight retention and empty or oversized edits stay blocked before writing',async()=>{
  for(const invalid of ['reject','empty','long']) {
    const f=await fixture();f.choose(3,invalid==='reject'?'rejected':'revised');
    if(invalid!=='reject')f.rows[3].input.value=invalid==='empty'?'   ':'字'.repeat(201);
    await f.submit.click({currentTarget:f.submit});assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
    assert.ok(f.toasts.length);assert.equal(f.submit.disabled,false);
  }
});

test('an in-flight submission cannot be reopened by changed choices or double-click',async()=>{
  let release;const gate=new Promise(resolve=>release=resolve);
  const f=await fixture(async()=>gate);
  const pending=f.submit.click({currentTarget:f.submit});f.choose(1,'revised');assert.equal(f.submit.disabled,true);
  await f.submit.click({currentTarget:f.submit});assert.equal(f.calls.filter(c=>c.method==='POST').length,1);
  release();await pending;
});

test('native authorization/source refusal preserves unsaved choices for controlled retry',async()=>{
  const f=await fixture(async()=>{throw Error('Native source is no longer valid');});
  await f.submit.click({currentTarget:f.submit});assert.equal(f.submit.disabled,false);
  assert.equal(f.submit.dataset.reviewSubmitting,'false');assert.equal(f.progress.textContent,'当前选择：通过 4 · 修改 0 · 不采用 0');
  assert.equal(f.calls.filter(c=>c.method==='POST').length,1);assert.ok(f.toasts.length);
});

test('Mix and Repurpose selectors use the same decision/progress controller',()=>{
  for(const [progressSelector,submitSelector] of [
    ['[data-review-progress]','[data-submit-review]'],
    ['[data-news-review-progress]','[data-news-submit-review]'],
  ]) {
    const rows=original.beats.map(row),progress={},submit=element();
    const controls={[progressSelector]:progress,[submitSelector]:submit};
    const host={querySelectorAll:()=>rows,querySelector:s=>controls[s]};
    bindContentReviewControls(host,{progressSelector,submitSelector});
    assert.equal(progress.textContent,'当前选择：通过 4 · 修改 0 · 不采用 0');assert.equal(submit.disabled,false);
    rows[2].radios[2].checked=true;rows[2].radios[2].change();
    assert.equal(progress.textContent,'当前选择：通过 3 · 修改 0 · 不采用 1');
  }
});

test('shared cards retain default Mix editors/notes and escape model text and sources',()=>{
  const html=ContentReviewItem({namespace:'mix',itemId:'C1',title:'<img src=x onerror=bad()>',body:'original narration',evidenceRows:[{label:'fact',value:'<script>bad</script>'}]});
  assert.match(html,/data-revised-body/);assert.match(html,/data-content-review-note/);
  assert.doesNotMatch(html,/<img|<script/);assert.match(html,/&lt;img/);
});

test('empty or incomplete review rows cannot use default selection to bypass admission',()=>{
  for(const rows of [[],original.beats.map(row)]) {
    const progress={},submit=element();
    const host={querySelectorAll:()=>rows,querySelector:s=>s==='[progress]'?progress:submit};
    if(rows.length)rows[0].radios[0].checked=false;
    bindContentReviewControls(host,{progressSelector:'[progress]',submitSelector:'[submit]'});
    assert.equal(submit.disabled,true);
  }
});
