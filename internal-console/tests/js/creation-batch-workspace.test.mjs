import test from 'node:test';
import assert from 'node:assert/strict';
import { createBatchReviewDraft } from '../../static/assets/creation-batch-draft.mjs';
import { createCreationBatchViews, batchWorkspaceMarkup, batchIdentity } from '../../static/assets/creation-batch-view.mjs';

const sha='a'.repeat(64),ref={path:'fictional/source.json',sha256:sha};
const storage=()=>{const data=new Map();return {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};};
const state=()=>({batch_id:'b',business_id:'fictional',control:'resume',status:'awaiting_review',generation_quiescent:true,publish_copy_enabled:true,
  counts:{target:2,generated:2,approved:0,delivered:0,review_pending:2,unknown:0,failed:0,missing_generation:0},
  groups:[{profile:'mix',style_id:'story',request_id:'native',native:{business_id:'fictional',business_display_name:'虚构客户'},
    slots:['s1','s2'].map(slot_id=>({slot_id,generated:true}))}]});
const preview=(scope='native_content_review',hash=sha)=>({batch_id:'b',scope,source_sha256:hash,items:['s1','s2'].map(slot_id=>({slot_id,native_kind:'mix',
  native_source_ref:ref,expected_head_ref:ref,display:{title:`标题${slot_id}`,narration:'完整且需要人工核对的正文',publish_title:'发布标题',publish_body:'发布正文',topics:['来源']}}))});
const settle=async()=>{for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));};
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};

function browser(store=storage()) {
  const previous={window:globalThis.window,document:globalThis.document,sessionStorage:globalThis.sessionStorage};
  let elements=new Map(),writes=0;
  function element(id){if(!elements.has(id))elements.set(id,{id,handlers:{},attributes:{},dataset:{},markup:'',
    addEventListener(event,handler){this.handlers[event]=handler;},setAttribute(k,v){this.attributes[k]=v;},focus(){},
    set innerHTML(value){this.markup=value;},get innerHTML(){return this.markup;},querySelector(){return null;},querySelectorAll(){return[];}});return elements.get(id);}
  globalThis.window={location:{href:'http://fixture/create/batch?batch_id=b',search:'?batch_id=b'},scrollY:0,scrollTo(){},confirm:()=>true};
  globalThis.sessionStorage=store;
  globalThis.document={getElementById:element,querySelectorAll:selector=>selector==='[data-batch-phase]'?[0,1,2,3].map(i=>{
    const button=element('batch-phase-'+i);button.dataset.batchPhase=String(i);return button;}):[]};
  const app={set innerHTML(value){this.markup=value;elements=new Map();writes++;}};
  const click=async attrs=>{const target={dataset:attrs,hasAttribute:key=>Object.hasOwn(attrs,key.replace(/^data-/,'').replace(/-([a-z])/g,(_,c)=>c.toUpperCase())),closest(){return this;}};
    element('batch-workspace').handlers.click({target});await settle();};
  return {app,element,store,click,get writes(){return writes;},get markup(){return element('batch-workspace').markup;},
    restore(){Object.assign(globalThis,previous);}};
}
function views(dom,api){return createCreationBatchViews({app:dom.app,api,shell:(_title,html)=>html,bindCommonActions(){},skeletonPage(){},renderLoadError(_title,error){throw error;}});}

test('local choices bind exact source, Slot, Native kind and scope, without becoming approval',()=>{
  const store=storage(),draft=createBatchReviewDraft(store,'b'),p=preview();
  draft.save(p,['approve','reject'],'s2');assert.deepEqual(draft.restore(p).choices,['approve','reject']);
  assert.equal(draft.restore(p).activeSlot,'s2');
  assert.deepEqual(draft.restore({...p,items:[p.items[1],p.items[0]]}).choices,['reject','approve']);
  assert.deepEqual(draft.restore({...p,source_sha256:'b'.repeat(64)}).choices,['','']);
  assert.equal(draft.restore({...p,source_sha256:'b'.repeat(64)}).invalidated,true);
  const news={...p,items:p.items.map(item=>({...item,native_kind:'novel_content'}))};
  assert.deepEqual(draft.restore(news).choices,['approve','']);
  assert.deepEqual(createBatchReviewDraft(store,'different').restore(p).choices,['','']);
  draft.save(preview('publish_copy_confirmation'),['approve',true],'s2');
  assert.deepEqual(draft.restore(preview('publish_copy_confirmation')).choices,['',true]);
  assert.deepEqual(draft.restore(p).choices,['approve','reject']);
  const blocked=createBatchReviewDraft({getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}},'b');
  blocked.save(p,['approve'],'s1');assert.deepEqual(blocked.restore(p).choices,['','']);
});

test('header identity cannot adopt another customer or guess the first Speaker',()=>{
  const p=state();p.groups[0].native={business_id:'other',business_display_name:'private',speaker_display_name:'private'};
  assert.deepEqual(batchIdentity(p,{customer_context:{business_id:'other'},customers:[{business_id:'other',display_name:'private'}]}),{customer:'',speaker:''});
  p.groups[0].native={business_id:'fictional',speaker_id:'exact'};
  assert.deepEqual(batchIdentity(p,{customer_context:{business_id:'fictional'},customers:[{business_id:'fictional',display_name:'合法客户',speakers:[{speaker_id:'other',display_name:'不应猜测'}]}]}),{customer:'合法客户',speaker:''});
});

test('entering review reads actual content, staging and refresh do not issue Human writes',async()=>{
  const dom=browser(),calls=[],p=state();let pv=preview();
  const api=async(path,request)=>{calls.push({path,request});return path.includes('human-options')?{preview:pv}:{state:p};};
  try{
    const view=views(dom,api);await view.renderBatch();
    assert.match(dom.markup,/完整且需要人工核对的正文/);assert.doesNotMatch(dom.markup,/开始审核|核对生成内容/);
    await dom.click({reviewChoice:'approve'});assert.match(dom.markup,/拟通过 · 待提交/);
    assert.match(dom.markup,/data-workspace-submit disabled/); // K=2 requires both explicit decisions.
    await dom.click({reviewSlot:'s2'});await dom.click({reviewChoice:'reject'});
    assert.doesNotMatch(dom.markup,/data-workspace-submit disabled/);
    await view.renderBatch();assert.match(dom.markup,/拟不采用 · 待提交/);assert.match(dom.markup,/第 2 条/);
    assert.equal(p.counts.approved,0);assert.ok(calls.every(c=>!c.request));
    pv=preview('native_content_review','b'.repeat(64));await view.renderBatch();
    assert.doesNotMatch(dom.markup,/拟通过|拟不采用/);assert.match(dom.element('batch-progress-message').textContent,/版本或审核范围已变化/);
    assert.match(dom.markup,/data-workspace-submit disabled/);
  }finally{dom.restore();}
});

test('reader failure and mismatched source cannot expose approval controls',async()=>{
  for(const outcome of ['failure','wrong-batch','duplicate-slot']){
    const dom=browser();
    try{
      await views(dom,async path=>{
        if(!path.includes('human-options'))return{state:state()};
        if(outcome==='failure')throw Error('来源不可读');
        const p=preview();if(outcome==='wrong-batch')p.batch_id='other';else p.items[1].slot_id='s1';return{preview:p};
      }).renderBatch();
      assert.match(dom.markup,/role="alert"/);assert.doesNotMatch(dom.markup,/data-review-choice/);assert.match(dom.markup,/data-workspace-submit disabled/);
    }finally{dom.restore();}
  }
});

test('a stale asynchronous read cannot replace a newer phase or reopened batch view',async()=>{
  const dom=browser(),pending=deferred();let first=true;
  const api=async path=>{if(!path.includes('human-options'))return{state:state()};if(first){first=false;return pending.promise;}return{preview:preview()};};
  try{
    const view=views(dom,api),old=view.renderBatch();await settle();
    await dom.element('batch-phase-0').handlers.click();const markup=dom.markup;
    pending.resolve({preview:preview()});await old;assert.equal(dom.markup,markup);assert.match(dom.markup,/生成进度/);
    const late=deferred();let delay=true;
    const next=views(dom,async path=>path.includes('human-options')?(delay?(delay=false,late.promise):{preview:preview()}):{state:state()});
    createBatchReviewDraft(dom.store,'b').position({phase:1,current:1});const firstRender=next.renderBatch();await settle();
    await next.renderBatch();const writes=dom.writes;late.resolve({preview:preview('native_content_review','b'.repeat(64))});await firstRender;
    assert.equal(dom.writes,writes);assert.doesNotMatch(dom.markup,/role="alert"/);
  }finally{dom.restore();}
});

test('Human response loss reloads and retries the exact submitted command; Publish remains separate',async()=>{
  const dom=browser(),commands=[];let approved=false,fail=true;
  const api=async(path,request)=>{
    if(path.endsWith('/human-command')){
      commands.push(JSON.parse(request.body));if(fail){fail=false;throw Error('response lost');}
      approved=true;return{result:{all_native_completed:true}};
    }
    if(path.includes('human-options'))return{preview:preview(approved?'publish_copy_confirmation':'native_content_review')};
    const p=state();if(approved){p.status='awaiting_publish_confirmation';p.counts.review_pending=0;p.counts.approved=2;p.groups[0].slots.forEach(s=>s.approved=true);}
    return{state:p};
  };
  try{
    const view=views(dom,api);await view.renderBatch();await dom.click({reviewChoice:'approve'});await dom.click({reviewSlot:'s2'});await dom.click({reviewChoice:'reject'});
    await dom.click({workspaceSubmit:''});assert.equal(commands.length,1);assert.match(dom.markup,/继续上次提交/);
    await view.renderBatch();await dom.click({reviewChoice:'approve'}); // Exact pending command is immutable.
    await dom.click({workspaceSubmit:''});assert.deepEqual(commands[1],commands[0]);
    assert.equal(commands.length,2);assert.match(dom.markup,/发布确认/);assert.match(dom.markup,/已选择 0 \/ 2/);
    assert.doesNotMatch(dom.markup,/aria-pressed="true"[^>]*>选择此发布版本/);
    assert.equal(dom.store.getItem('creation-batch-human:b'),null);
  }finally{dom.restore();}
});

test('saved Human result is acknowledged while the next fresh Native state is still loading',async()=>{
  const dom=browser(),next=deferred();let saved=false,reads=0;
  const api=async(path,request)=>{
    if(path.endsWith('/human-command')){saved=true;return{result:{all_native_completed:true}};}
    if(path.includes('human-options'))return{preview:preview()};
    reads++;return saved?next.promise:{state:state()};
  };
  try{
    await views(dom,api).renderBatch();
    await dom.click({reviewChoice:'approve'});await dom.click({reviewSlot:'s2'});await dom.click({reviewChoice:'reject'});
    await dom.click({workspaceSubmit:''});
    assert.equal(reads,2);
    assert.match(dom.element('batch-progress-message').textContent,/本次审核结果已保存/);
    assert.equal(dom.store.getItem('creation-batch-human:b'),null);
    // A saved command does not claim the next Native phase is ready.
    assert.doesNotMatch(dom.markup,/选择此发布版本/);
    next.resolve({state:state()});await settle();
  }finally{next.resolve({state:state()});await settle();dom.restore();}
});

test('active-task polling counts Native read time and never overlaps an unfinished state read',async()=>{
  for(const elapsed of [1000,6000]){
    const dom=browser(),pending=deferred(),timers=[];
    const originalNow=Date.now,originalTimer=globalThis.setTimeout;let now=100,reads=0;
    Date.now=()=>now;globalThis.setTimeout=(callback,delay)=>{timers.push({callback,delay});return 0;};
    try{
      const rendering=views(dom,async()=>{reads++;return pending.promise;}).renderBatch();
      await settle();assert.equal(reads,1);assert.equal(timers.length,0);
      const p=state();p.status='generating';Object.assign(p.counts,{generated:0,approved:0,review_pending:0,missing_generation:2});
      now+=elapsed;pending.resolve({state:p});await rendering;
      assert.equal(timers.length,1);assert.equal(timers[0].delay,elapsed===1000?3000:500);
      assert.equal(reads,1);
    }finally{Date.now=originalNow;globalThis.setTimeout=originalTimer;dom.restore();}
  }
});

test('scheduled polling waits for a newly opened Human reader without issuing another Native state scan',async()=>{
  const dom=browser(),pending=deferred(),timers=[],originalTimer=globalThis.setTimeout;let stateReads=0,contentLoading=false;
  globalThis.setTimeout=(callback,delay)=>{timers.push({callback,delay});return 0;};
  const p=state();p.status='preparing_publish_copy';p.counts.approved=2;p.counts.review_pending=0;
  p.groups[0].publish={draft:{ref},confirmed:false};
  try{
    await views(dom,async path=>{
      if(path.includes('scope=native_content_review')){contentLoading=true;return pending.promise;}
      if(path.includes('human-options'))return{preview:preview('publish_copy_confirmation')};
      stateReads++;return{state:p};
    }).renderBatch();
    assert.equal(timers.length,1);
    await dom.element('batch-phase-1').handlers.click();await settle();assert.equal(contentLoading,true);
    timers[0].callback();await settle();
    assert.equal(stateReads,1);assert.equal(timers.length,2);assert.equal(timers[1].delay,500);
    pending.resolve({preview:preview()});await settle();
    timers[1].callback();await settle();assert.equal(stateReads,2);
  }finally{pending.resolve({preview:preview()});await settle();globalThis.setTimeout=originalTimer;dom.restore();}
});

function deliveryState(){const p=state();p.status='ready_for_delivery';p.counts.approved=2;p.counts.review_pending=0;
  p.groups[0].publish={confirmed:true,draft:{ref},delivery:{draft_ref:{...ref}}};p.groups[0].slots.forEach(s=>{s.approved=true;s.native_exported=true;});return p;}
const deliveryPreview={source_sha256:sha,scope:'complete_target',slot_ids:['s1','s2'],target:2,delivered:2,shortfall:0,files:[{profile:'mix',rows:2}]};

test('delivery reads a legal preview automatically but exports only after explicit confirmation with stable retry',async()=>{
  const dom=browser(),calls=[];let fail=true;
  const api=async(path,request)=>{
    calls.push({path,body:request?JSON.parse(request.body):null});
    if(path.endsWith('delivery-preview'))return{preview:deliveryPreview};
    if(path.endsWith('delivery-export')){if(fail){fail=false;throw Error('response lost');}return{result:{accepted:true}};}
    return{state:deliveryState()};
  };
  try{
    const view=views(dom,api);await view.renderBatch();
    assert.equal(calls.filter(c=>c.path.endsWith('delivery-preview')).length,1);
    assert.equal(calls.filter(c=>c.path.endsWith('delivery-export')).length,0);
    assert.match(dom.markup,/Mix Excel · 2 条/);await dom.click({workspaceSubmit:''});
    const body=calls.find(c=>c.path.endsWith('delivery-export')).body;
    assert.deepEqual(body.slot_ids,['s1','s2']);assert.equal(body.source_sha256,sha);assert.equal(body.scope,'complete_target');
    await view.renderBatch();assert.match(dom.markup,/重试上次汇总/);
    assert.equal(calls.filter(c=>c.path.endsWith('delivery-preview')).length,1);
    await dom.click({workspaceSubmit:''});assert.deepEqual(calls.filter(c=>c.path.endsWith('delivery-export')).map(c=>c.body),[body,body]);
  }finally{dom.restore();}
});

test('stale export preflight rereads sources and requires a new explicit confirmation',async()=>{
  for(const code of ['COMPOSITE_PREFLIGHT_STALE','CREATION_BATCH_DELIVERY_PREFLIGHT_STALE']){
    const dom=browser(),exports=[];let previews=0;
    try{
      await views(dom,async(path,request)=>{
        if(path.endsWith('delivery-preview')){previews++;return{preview:deliveryPreview};}
        if(path.endsWith('delivery-export')){exports.push(JSON.parse(request.body));throw Object.assign(Error('版本已变化'),{detail:{code}});}
        return{state:deliveryState()};
      }).renderBatch();
      await dom.click({workspaceSubmit:''});assert.equal(exports.length,1);assert.equal(previews,2);
      assert.equal(dom.store.getItem('creation-batch-export:b'),null);assert.match(dom.markup,/生成分类 Excel/);
    }finally{dom.restore();}
  }
});

test('a delivery preview for a different Slot set cannot authorize the displayed scope',async()=>{
  const dom=browser();
  try{
    await views(dom,async path=>path.endsWith('delivery-preview')?{preview:{...deliveryPreview,slot_ids:['other','s2']}}:{state:deliveryState()}).renderBatch();
    assert.match(dom.markup,/交付范围版本无法对应/);assert.doesNotMatch(dom.markup,/data-workspace-submit/);
  }finally{dom.restore();}
});

test('completed delivery exposes Native files while historical/partial scopes never imply full completion',()=>{
  const p=deliveryState();p.deliveries={completed:[{delivery_id:'old&1',is_current:false,delivered:1,shortfall:1,scope:'explicit_legal_subset',files:[{profile:'mix'}]},
    {delivery_id:'new',is_current:true,delivered:2,shortfall:0,scope:'complete_target',files:[{profile:'news'},{profile:'mix'}]}]};
  const markup=batchWorkspaceMarkup(p,{phase:3});assert.match(markup,/历史交付 · 1 条/);assert.match(markup,/old%261\/mix/);
  assert.match(markup,/下载新闻 Excel/);assert.match(markup,/下载Mix Excel/);assert.doesNotMatch(markup,/整批交付已完成/);
  p.status='preparing_delivery';assert.match(batchWorkspaceMarkup(p,{phase:3}),/无需重复提交/);
});
