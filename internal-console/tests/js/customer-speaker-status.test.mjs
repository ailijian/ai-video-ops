import test from 'node:test';
import assert from 'node:assert/strict';
import {watchCustomerSpeakerTasks} from '../../static/assets/customer-speaker-status.mjs';

const flush=()=>new Promise(setImmediate);
const speaker=id=>({speaker_id:id,status:'analyzing',task:{task_id:'task-'+id,task_type:'speaker_analysis',subject_ref:id,status:'running',payload:{business_id:'business'}}});
const customer=(speakers=[speaker('person')])=>({business_id:'business',status:'approved',speakers});
async function environment(run) {
  const old={window:globalThis.window,document:globalThis.document};
  const doc=Object.assign(new EventTarget(),{visibilityState:'visible'}),win=new EventTarget(),timers=new Map();let serial=0;
  win.setTimeout=fn=>{timers.set(++serial,fn);return serial;};win.clearTimeout=id=>timers.delete(id);
  globalThis.document=doc;globalThis.window=win;
  const disposers=[];const observe=options=>{const stop=watchCustomerSpeakerTasks(options);disposers.push(stop);return stop;};
  const tick=async()=>{assert.ok(timers.size);[...timers.values()][0]();await flush();};
  try {await run({observe,timers,tick,doc,win});}
  finally {disposers.forEach(stop=>stop());Object.assign(globalThis,old);}
}

test('all terminal executions re-read canonical status and never infer Human approval from completion',async()=>{
  for(const status of ['awaiting_review','completed','failed']) await environment(async({observe,tick,timers})=>{
    let terminal=false;const reads=[],updates=[],detail=customer();
    const latest=customer([{...speaker('person'),status:status==='failed'?'failed':'fact_review_required',task:{...speaker('person').task,status}}]);
    observe({detail,isCurrent:()=>true,onDetail:v=>updates.push(v),onError:assert.fail,api:async(path,options)=>{
      assert.equal(options,undefined);reads.push(path);
      return path.startsWith('/api/tasks/')?{task:{...speaker('person').task,status:terminal?status:'running'}}:latest;
    }});
    await flush();assert.equal(updates.length,0);terminal=true;await tick();
    assert.deepEqual(reads,['/api/tasks/task-person','/api/tasks/task-person','/api/customers/business']);
    assert.equal(updates.length,1);assert.equal(updates[0],latest);assert.notEqual(updates[0].speakers[0].status,'approved');assert.equal(timers.size,0);
  });
});

test('a failed projection read retries read-only without finishing the observer prematurely',async()=>{
  await environment(async({observe,tick,timers})=>{
    const updates=[],errors=[];let reads=0;
    observe({detail:customer(),isCurrent:()=>true,onDetail:v=>updates.push(v),onError:e=>errors.push(e),api:async path=>{
      if(path.startsWith('/api/tasks/')) return {task:{...speaker('person').task,status:'awaiting_review'}};
      if(++reads===1) throw Error('temporary read failure');return customer([]);
    }});
    await flush();assert.equal(updates.length,0);assert.equal(errors.length,1);assert.equal(timers.size,1);
    await tick();assert.equal(reads,2);assert.equal(updates.length,1);assert.equal(timers.size,0);
  });
});

test('leaving a page cancels an in-flight task and suppresses its later customer read',async()=>{
  await environment(async({observe,timers})=>{
    let resolve;const pending=new Promise(r=>{resolve=r;}),reads=[],updates=[];
    const stop=observe({detail:customer(),isCurrent:()=>true,onDetail:v=>updates.push(v),onError:assert.fail,api:path=>{reads.push(path);return pending;}});
    stop();resolve({task:{...speaker('person').task,status:'completed'}});await flush();
    assert.deepEqual(reads,['/api/tasks/task-person']);assert.deepEqual(updates,[]);assert.equal(timers.size,0);
  });
});

test('a late canonical response cannot update another route or a replacement page',async()=>{
  await environment(async({observe,timers})=>{
    let current=true,resolve;const pending=new Promise(r=>{resolve=r;}),updates=[];
    observe({detail:customer(),isCurrent:()=>current,onDetail:v=>updates.push(v),onError:assert.fail,api:async path=>path.startsWith('/api/tasks/')?{task:{...speaker('person').task,status:'completed'}}:pending});
    await flush();current=false;resolve(customer([]));await flush();
    assert.deepEqual(updates,[]);assert.equal(timers.size,0);
  });
});

test('multiple speakers settle once using the freshest read and discard older responses',async()=>{
  await environment(async({observe,timers})=>{
    const waiting=[],updates=[];let terminal=false;
    observe({detail:customer([speaker('a'),speaker('b')]),isCurrent:()=>true,onDetail:v=>updates.push(v),onError:assert.fail,api:async path=>{
      if(path.startsWith('/api/tasks/')) return {task:{status:terminal?'completed':'running'}};
      return new Promise(resolve=>waiting.push(resolve));
    }});
    await flush();assert.equal(timers.size,2);terminal=true;
    for(const fn of [...timers.values()]) fn();await flush();assert.equal(waiting.length,2);
    waiting[1](customer([]));await flush();waiting[0](customer([speaker('a')]));await flush();
    assert.equal(updates.length,1);assert.deepEqual(updates[0].speakers,[]);assert.equal(timers.size,0);
  });
});

test('permission failures stop reads and never publish a successful projection',async()=>{
  for(const status of [401,403]) await environment(async({observe,timers})=>{
    const errors=[],updates=[];
    observe({detail:customer(),isCurrent:()=>true,onDetail:v=>updates.push(v),onError:e=>errors.push(e),api:async()=>{throw Object.assign(Error('denied'),{status});}});
    await flush();assert.equal(errors.length,1);assert.deepEqual(updates,[]);assert.equal(timers.size,0);
  });
});

test('hidden pages pause execution reads and resume through the existing visibility mechanism',async()=>{
  await environment(async({observe,doc,timers})=>{
    let reads=0;
    observe({detail:customer(),isCurrent:()=>true,onDetail:assert.fail,onError:assert.fail,api:async()=>{reads++;return {task:{status:'running'}};}});
    await flush();doc.visibilityState='hidden';doc.dispatchEvent(new Event('visibilitychange'));assert.equal(timers.size,0);
    doc.visibilityState='visible';doc.dispatchEvent(new Event('visibilitychange'));await flush();assert.equal(reads,2);assert.equal(timers.size,1);
  });
});

test('unrelated task identities and customers without active speaker work never start polling',async()=>{
  await environment(async({observe,timers})=>{
    const foreign=speaker('foreign');foreign.task.payload.business_id='another';
    observe({detail:customer([foreign,{...speaker('person'),status:'fact_review_required'}]),isCurrent:()=>true,onDetail:assert.fail,onError:assert.fail,api:async()=>assert.fail('unrelated read')});
    await flush();assert.equal(timers.size,0);
  });
});

test('a changed customer lifecycle blocks the refresh without converting it to an approved view',async()=>{
  await environment(async({observe,timers})=>{
    const updates=[],errors=[];
    observe({detail:customer(),isCurrent:()=>true,onDetail:v=>updates.push(v),onError:e=>errors.push(e),api:async path=>path.startsWith('/api/tasks/')?{task:{status:'completed'}}:{...customer([]),status:'fact_review_required'}});
    await flush();assert.equal(updates.length,0);assert.match(errors[0].message,/客户资料状态已变化/);assert.equal(timers.size,0);
  });
});
