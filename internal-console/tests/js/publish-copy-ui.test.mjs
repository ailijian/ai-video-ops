import assert from 'node:assert/strict';
import test from 'node:test';
import { mountPublishCopy } from '../../static/assets/publish-copy-views.js';
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const state = () => ({ request_id:'gen_original', mode:'novel_content', state:'draft_ready', tasks:[],
  source_sha256:'a'.repeat(64), attempt_ref:{path:'attempt',sha256:'b'.repeat(64)},
  production:[{target_id:'gen_original-N001',units:[{unit_id:'B1',text:'套餐29元，仅限自取'},{unit_id:'B2',text:'不含配送'}]}],
  draft:{ref:{path:'draft',sha256:'c'.repeat(64)},payload:{items:[{target_id:'gen_original-N001',source_version_sha256:'a'.repeat(64),
    publish_title:'套餐29元',publish_body:'仅限自取，不含配送',topics:['套餐'],production_headlines:[
      {order:1,text:'套餐29元，仅限自取，不含配送',source_unit_ids:['B1','B2'],mapping_kind:'merge'}]}]}},confirmed:true });
function el(extra={}) { return Object.defineProperties({dataset:{},disabled:false,isConnected:true,
  addEventListener(n,f){this[n]=f;}},Object.getOwnPropertyDescriptors(extra)); }
async function fixture(value=state(),behavior=async()=>null) {
  const calls=[],toasts=[];let panel;
  const host={isConnected:true,append:p=>panel=p};
  const nodes={};let row;
  globalThis.window={addEventListener(){},removeEventListener(){}};
  globalThis.document={visibilityState:'hidden',addEventListener(){},removeEventListener(){},createElement:()=>el({set innerHTML(html){this.html=html;
    for(const key of ['refresh','retry-consent','retry','generate','remaining','edit','cancel','save','confirm','export','download','status','progress']) {
      const tag=html.match(new RegExp(`<[^>]+data-pc-${key}(?=[\\s>])[^>]*>`))?.[0];
      if(tag)nodes[key]=el({checked:false,hidden:/\shidden(?=[\s>])/.test(tag),disabled:/\sdisabled(?=[\s>])/.test(tag),
        className:/class="([^"]*)"/.exec(tag)?.[1]||'',href:/href="([^"]*)"/.exec(tag)?.[1]});else delete nodes[key];
    }
    nodes.message=el();
    const item=value.draft?.payload?.items[0];
    row=item?{dataset:{pcItem:'0'},title:el({value:item.publish_title}),body:el({value:item.publish_body}),
      topics:el({value:item.topics.join(' ')}),
      querySelector(s){return {'[data-pc-title]':this.title,'[data-pc-body]':this.body,'[data-pc-topics]':this.topics}[s];},
      querySelectorAll(){return item.production_headlines.map(h=>({querySelector:s=>s==='[data-pc-headline-text]'?{value:h.text}:null,
        querySelectorAll:()=>h.source_unit_ids.map(id=>({dataset:{pcUnit:id}}))}));}}:null;
  },querySelector(s){return s==='[role="status"]'?nodes.message:nodes[/^\[data-pc-(.+)\]$/.exec(s)?.[1]]||null;},
  querySelectorAll(s){if(s==='[data-pc-item]')return row?[row]:[];if(s.startsWith('textarea,input'))return row?[row.title,row.body,row.topics]:[];return [];}})};
  await mountPublishCopy(host,'gen_original',{escapeHtml:esc,showToast:m=>toasts.push(m),api:async(path,options)=>{
    const call={path,method:options?.method,body:options?.body?JSON.parse(options.body):null};calls.push(call);
    const overridden=await behavior(call);if(overridden)return overridden;
    if(path.endsWith('/capability'))return {enabled:true};
    if(path.endsWith('/edit'))return {result:value.draft.ref};
    return {state:structuredClone(value)};
  }});
  return {host,get panel(){return panel;},nodes,calls,toasts,get row(){return row;}};
}
test('unknown outcome never auto-dispatches and requires explicit retry consent',async()=>{
  const value=state();value.state='dispatched_outcome_unknown';value.draft=null;value.confirmed=false;
  const f=await fixture(value);assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
  assert.equal(f.nodes.generate,undefined);assert.match(f.panel.html,/不会自动重复生成/);
  assert.match(f.panel.html,/data-pc-retry disabled/);
  f.nodes['retry-consent'].checked=true;f.nodes['retry-consent'].change({target:f.nodes['retry-consent']});
  await f.nodes.retry.click({currentTarget:f.nodes.retry});
  const submit=f.calls.find(c=>c.method==='POST');assert.ok(submit.path.endsWith('/publish-copy/generate'));
  assert.deepEqual(submit.body,{expected_parent:value.attempt_ref,retry_confirmation:'explicit_retry_possible_additional_cost'});
});
test('combined confirmation saves actual News headlines and all publishing fields on original Request',async()=>{
  const value=state();value.confirmed=false;
  const f=await fixture(value);assert.match(f.panel.html,/实际交付的制作短标题/);
  assert.equal(f.nodes.confirm.hidden,false);
  await f.nodes.confirm.click({currentTarget:f.nodes.confirm});
  const posts=f.calls.filter(c=>c.method==='POST');assert.equal(posts.length,2);
  assert.ok(posts[0].path.endsWith('/edit'));assert.equal(posts[0].body.payload.items[0].production_headlines[0].mapping_kind,'merge');
  assert.ok(posts[1].path.endsWith('/confirm'));assert.deepEqual(posts[1].body,{draft_ref:state().draft.ref});
  assert.ok(posts.every(p=>p.path.startsWith('/api/create/gen_original/publish-copy/')));
});
test('unsaved changes disable formal export and a failed save retains editor values',async()=>{
  const f=await fixture(state(),async call=>{if(call.path.endsWith('/edit'))throw Error('Source changed');});
  await f.nodes.edit.click({currentTarget:f.nodes.edit});
  f.row.title.value='尚未保存的表达';f.row.title.input();assert.equal(f.nodes.export.disabled,true);
  assert.equal(f.nodes.export.hidden,true);assert.equal(f.nodes.confirm.hidden,false);
  const before=f.calls.length;await f.nodes.save.click({currentTarget:f.nodes.save});
  assert.equal(f.row.title.value,'尚未保存的表达');assert.equal(f.panel.dataset.dirty,'true');
  assert.equal(f.calls.slice(before).filter(c=>!c.method).length,0);assert.ok(f.toasts.length);
});
test('existing confirmed download is labelled as a version while a stale draft cannot be exported',async()=>{
  const value=state();value.state='stale';value.confirmed=false;value.delivery={delivery_id:'d'.repeat(32)};
  const f=await fixture(value);assert.equal(f.nodes.export,undefined);assert.equal(f.nodes.confirm,undefined);
  assert.match(f.panel.html,/下载上次已确认版本/);assert.match(f.panel.html,/原发布稿不能用于新的正式交付/);
});
test('model text and source are escaped in editable controls',async()=>{
  const value=state();value.draft.payload.items[0].publish_title='<img src=x onerror=bad()>';
  const f=await fixture(value);assert.doesNotMatch(f.panel.html,/<img src=/);assert.match(f.panel.html,/&lt;img/);
});
test('partial export gives a continue action while a lost response with verified completion does not',async()=>{
  const value=state();value.tasks=[{status:'failed',payload:{operation:'publish_copy_export',publish_copy:{expected_draft_ref:value.draft.ref}}}];
  const pending=await fixture(value);assert.match(pending.panel.html,/导出尚未完成，可继续原操作/);
  assert.match(pending.panel.html,/继续完成原导出/);
  value.delivery={delivery_id:'d'.repeat(32),draft_ref:value.draft.ref};
  const completed=await fixture(value);assert.doesNotMatch(completed.panel.html,/导出尚未完成/);
  assert.match(completed.panel.html,/下载已确认版本/);
});
test('a terminal Task paired with a pre-completion snapshot triggers only a fresh read',async()=>{
  const value=state();let reads=0;
  const f=await fixture(value,async call=>{
    if(call.path==='/api/create/gen_original/publish-copy'&&!call.method) {
      reads++;const snapshot=structuredClone(value);
      snapshot.tasks=[{task_id:'finished-original',status:'completed'}];
      if(reads===1){snapshot.state='not_dispatched';snapshot.draft=null;snapshot.confirmed=false;}
      return {state:snapshot};
    }
  });
  assert.equal(reads,2);assert.match(f.panel.html,/实际交付的制作短标题/);
  assert.equal(f.calls.filter(call=>call.method==='POST').length,0);
});

const mainActions = f => Object.entries(f.nodes).filter(([,node]) => !node.hidden && (node.className||'').split(' ').includes('btn-primary')).map(([name])=>name);
test('each stage highlights only its next action and viewing stages never writes business data',async()=>{
  const initial=state();initial.state='not_started';initial.draft=null;initial.confirmed=false;
  const pending=state();pending.confirmed=false;
  const complete=state();complete.delivery={delivery_id:'d'.repeat(32),draft_ref:complete.draft.ref};
  for(const [value,action] of [[initial,'generate'],[pending,'confirm'],[state(),'export'],[complete,'download']]){
    const f=await fixture(value);assert.deepEqual(mainActions(f),[action]);
    assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
  }
});
test('editing a delivered version exposes confirmation while retaining the original download',async()=>{
  const value=state();value.delivery={delivery_id:'d'.repeat(32),draft_ref:value.draft.ref};
  const f=await fixture(value);const download=f.nodes.download.href;
  assert.equal(f.nodes.confirm.hidden,true);assert.equal(f.nodes.save.hidden,true);
  assert.equal(f.row.body.readOnly,true);
  await f.nodes.edit.click({currentTarget:f.nodes.edit});assert.equal(f.row.body.readOnly,false);
  f.row.body.value='只改变表达';f.row.body.input();
  assert.deepEqual(mainActions(f),['confirm']);assert.equal(f.nodes.save.hidden,false);
  assert.equal(f.nodes.download.href,download);assert.equal(f.nodes.download.textContent,'下载上次已确认版本');
  assert.equal(f.nodes.status.textContent,'修改待确认');assert.match(f.nodes.progress.innerHTML,/核对并确认/);
  assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
});
test('a partial batch asks to complete missing items before offering batch confirmation',async()=>{
  const value=state();value.confirmed=false;value.production.push({target_id:'second',units:[]});
  const f=await fixture(value);assert.deepEqual(mainActions(f),['remaining']);assert.equal(f.nodes.confirm.hidden,true);
  f.row.title.input();assert.equal(f.nodes.confirm.hidden,true);
});
test('unknown outcomes with prior items keep the explicit recovery action and cannot look confirmed after editing',async()=>{
  const value=state();value.state='dispatched_outcome_unknown';value.confirmed=false;
  value.production.push({target_id:'second',units:[]});
  const f=await fixture(value);assert.deepEqual(mainActions(f),['retry']);
  assert.equal(f.nodes.remaining,undefined);assert.equal(f.nodes.confirm.hidden,true);
  f.row.title.input();assert.equal(f.nodes.confirm.hidden,true);assert.equal(f.nodes.status.textContent,'需要处理');
  assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
});
test('a running operation keeps editor and business actions disabled',async()=>{
  const value=state();value.confirmed=false;value.tasks=[{task_id:'current',status:'running'}];
  const f=await fixture(value);assert.equal(f.nodes.confirm.disabled,true);assert.equal(f.nodes.save.disabled,true);
  assert.ok([f.row.title,f.row.body,f.row.topics].every(input=>input.disabled));
  assert.match(f.panel.html,/正在后台处理/);assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
});
test('Mix uses the shared publishing editor without News headline controls',async()=>{
  const value=state();value.mode='mix';value.production=[{target_id:'gen_original-N001',title:'制作标题',narration:'已审核口播'}];
  const f=await fixture(value);assert.doesNotMatch(f.panel.html,/data-pc-headline-text/);
  assert.match(f.panel.html,/制作标题\n已审核口播/);assert.ok(f.panel.className.includes('creation-section'));
  assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
});
test('confirmed information is read-only before and after export, and cancel restores it without writes',async()=>{
  for(const completed of [false,true]){
    const value=state();if(completed)value.delivery={delivery_id:'d'.repeat(32),draft_ref:value.draft.ref};
    const f=await fixture(value);
    assert.ok([f.row.title,f.row.body,f.row.topics].every(input=>input.readOnly));
    await f.nodes.edit.click({currentTarget:f.nodes.edit});
    assert.ok([f.row.title,f.row.body,f.row.topics].every(input=>!input.readOnly));
    assert.ok(!f.nodes.export || f.nodes.export.hidden);
    f.row.title.value='尚未保存的修改';f.row.title.input();
    await f.nodes.cancel.click({currentTarget:f.nodes.cancel});
    assert.equal(f.row.title.value,value.draft.payload.items[0].publish_title);
    assert.equal(f.row.title.readOnly,true);assert.equal(f.calls.filter(c=>c.method==='POST').length,0);
  }
});
test('ordered server snapshots do not need a duplicate full Native read',async()=>{
  const value=state();value.task_snapshot_before_native=true;
  value.tasks=[{task_id:'already-finished',status:'completed'}];
  const f=await fixture(value);
  assert.equal(f.calls.filter(c=>c.path==='/api/create/gen_original/publish-copy'&&!c.method).length,1);
});
test('confirmation validates the saved ref without an intermediate page refresh',async()=>{
  const value=state();value.confirmed=false;const f=await fixture(value);
  const start=f.calls.length;await f.nodes.confirm.click({currentTarget:f.nodes.confirm});
  assert.deepEqual(f.calls.slice(start).map(c=>[c.path.split('/').at(-1),c.method||'GET']),
    [['edit','POST'],['confirm','POST'],['publish-copy','GET']]);
});
test('an accepted Task is polled without immediately repeating full source validation',async()=>{
  const value=state();value.state='not_started';value.draft=null;value.confirmed=false;
  const f=await fixture(value,async call=>call.path.endsWith('/generate')?{accepted:true,task:{task_id:'original-task',status:'queued'}}:null);
  const start=f.calls.length;await f.nodes.generate.click({currentTarget:f.nodes.generate});
  assert.equal(f.calls.slice(start).filter(c=>c.path==='/api/create/gen_original/publish-copy').length,0);
  assert.match(f.panel.html,/正在后台处理/);assert.equal(f.nodes.generate.disabled,true);
});
test('slow admission immediately shows busy state and blocks a repeated click',async()=>{
  const value=state();value.state='not_started';value.draft=null;value.confirmed=false;
  let accept;const submitted=new Promise(resolve=>accept=resolve);
  const f=await fixture(value,async call=>call.path.endsWith('/generate')?submitted:null);
  const button=f.nodes.generate;const pending=button.click({currentTarget:button});
  assert.equal(button.disabled,true);assert.equal(button.textContent,'正在处理…');
  assert.match(f.nodes.message.textContent,/正在核对并提交/);
  accept({accepted:true,task:{task_id:'same-original',status:'queued'}});await pending;
  assert.equal(f.calls.filter(c=>c.method==='POST').length,1);
});
test('a confirmation failure retains the Native saved ref for an explicit retry',async()=>{
  const value=state();value.confirmed=false;const saved={path:'new-draft',sha256:'d'.repeat(64)};
  let confirmations=0;
  const f=await fixture(value,async call=>{
    if(call.path.endsWith('/edit'))return {result:saved};
    if(call.path.endsWith('/confirm') && ++confirmations===1)throw Error('response lost');
    return null;
  });
  const button=f.nodes.confirm;await button.click({currentTarget:button});
  assert.equal(f.calls.filter(c=>c.method==='POST').length,2);
  await button.click({currentTarget:button});
  const posts=f.calls.filter(c=>c.method==='POST');
  assert.deepEqual(posts[1].body.draft_ref,saved);assert.deepEqual(posts[2].body.draft_ref,saved);
  assert.deepEqual(posts[3].body.draft_ref,saved);
});
