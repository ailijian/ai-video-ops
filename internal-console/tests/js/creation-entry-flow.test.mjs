import assert from 'node:assert/strict';
import test from 'node:test';
import { createPreparationOperation } from '../../static/assets/creation-entry-flow.js';

const confirmation = {business_id:'fictional_A',speaker_id:'fictional_person',profile:'mix',requested_quantity:1,confirmed_quantity:1,idempotency_key:'fixed_explicit_confirmation'};
function fixture(behavior = async () => {}) {
  const calls = [];
  const api = async (path, options) => {
    calls.push({path,body:options?.body && JSON.parse(options.body)});
    await behavior(path, calls.length);
    if (path.endsWith('/confirm')) return {result:{request_id:'original_request'}};
    return {result:{ok:true}};
  };
  return {calls,api};
}
test('one explicit confirmation creates then prepares, never generates or approves', async () => {
  const f=fixture(), stages=[];
  const op=createPreparationOperation({...f,confirmation,onStage:s=>stages.push(s)});
  assert.equal(f.calls.length,0);
  assert.equal(await op.continue(),true);
  assert.deepEqual(f.calls.map(c=>c.path),['/api/create/confirm','/api/create/original_request/resolve-sources']);
  assert.deepEqual(f.calls[0].body,confirmation);
  assert.deepEqual(stages,['正在建立本次创作','正在核对创作依据']);
});
test('double click shares the same in-flight operation', async () => {
  let release; const gate=new Promise(resolve=>release=resolve);
  const f=fixture(async()=>gate),op=createPreparationOperation({...f,confirmation});
  const a=op.continue(),b=op.continue();assert.equal(a,b);release();await Promise.all([a,b]);
  assert.equal(f.calls.length,2);
});
test('unknown confirmation response replays exact intent; no automatic retry', async () => {
  const f=fixture(async(_,n)=>{if(n===1)throw Error('response lost');});
  const op=createPreparationOperation({...f,confirmation});
  await assert.rejects(op.continue(),/response lost/);assert.equal(f.calls.length,1);
  await op.continue();assert.deepEqual(f.calls[0].body,f.calls[1].body);
  assert.equal(op.requestId,'original_request');assert.equal(f.calls.length,3);
});
test('source failure resumes original Request without repeating confirmation', async () => {
  const f=fixture(async(_,n)=>{if(n===2)throw Error('source interruption');});
  const op=createPreparationOperation({...f,confirmation});
  await assert.rejects(op.continue(),/source interruption/);
  await op.continue();assert.equal(f.calls.filter(c=>c.path.endsWith('/confirm')).length,1);
  assert.equal(f.calls[1].path,f.calls[2].path);
});
test('already confirmed A only prepares its exact original Request', async () => {
  const f=fixture(),op=createPreparationOperation({...f,confirmation,active:{request_id:'founder_original_A',handoff_ready:true}});
  await op.continue();assert.deepEqual(f.calls.map(c=>c.path),['/api/create/founder_original_A/resolve-sources']);
});
test('partial handoff cannot switch Request identity', async () => {
  const f=fixture(),op=createPreparationOperation({...f,confirmation,active:{request_id:'different_request',handoff_ready:false}});
  await assert.rejects(op.continue(),/无法准确恢复/);assert.equal(f.calls.length,1);
});
test('withdrawn authority/permission errors stop at native Gate', async () => {
  const f=fixture(async()=>{throw Error('COMPATIBILITY_WITHDRAWN');});
  const op=createPreparationOperation({...f,confirmation,active:{request_id:'original_request',handoff_ready:true}});
  await assert.rejects(op.continue(),/COMPATIBILITY_WITHDRAWN/);assert.equal(f.calls.length,1);
});
test('navigation while confirmation is running cannot start stale preparation', async () => {
  let release,current=true;const gate=new Promise(resolve=>release=resolve);
  const f=fixture(async()=>gate),op=createPreparationOperation({...f,confirmation,isCurrent:()=>current});
  const pending=op.continue();current=false;release();assert.equal(await pending,false);
  assert.equal(f.calls.length,1);
});
