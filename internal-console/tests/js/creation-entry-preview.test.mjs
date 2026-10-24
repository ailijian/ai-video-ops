import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {createPreparationOperation} from '../../static/assets/creation-entry-flow.js';
const source=await readFile(new URL('../../static/assets/content-views.js',import.meta.url),'utf8');
const check=source.slice(source.indexOf('checkCurrentEntry = async (version) => {'),source.indexOf('    entryForm.addEventListener("submit"'));
function fixture(quantity='1') {
  const button={},errorBox={classList:{remove(){},add(){}}},host={innerHTML:'',querySelector(){return null;}},entryForm={classList:{contains(){return false;},toggle(){}}};
  const fields={'#content-entry-form':entryForm,'#create-quantity':{value:quantity},'#check-content-capacity':button,'#content-entry-error':errorBox};
  const pending=[],renders=[];
  const context=vm.createContext({
    previewVersion:1,window:{location:{href:'current-route'}},route:'current-route',entryForm,host,
    business:{value:'approved_business'},speaker:{value:'approved_speaker'},confirmationKey:null,
    selectedProfileValue:()=> 'mix',selectedNewsModeValue:()=> 'cross_profile_repurpose',
    document:{querySelector:s=>fields[s]},renderResult:p=>renders.push(p),CreationState:s=>s.title,
    safeCreationMessage:(message)=>message,api:(path,options)=>new Promise((resolve,reject)=>pending.push({path,options,resolve,reject})),
  });
  vm.runInContext(check,context);
  return {context,pending,renders,fields,host,errorBox};
}
test('older quantity response cannot replace latest preview',async()=>{
  const f=fixture();const a=f.context.checkCurrentEntry(1);
  f.context.previewVersion=2;f.fields['#create-quantity'].value='2';const b=f.context.checkCurrentEntry(2);
  f.pending[1].resolve({preview:{quantity:2}});await b;
  f.pending[0].resolve({preview:{quantity:1}});await a;
  assert.deepEqual(f.renders,[{quantity:2}]);
  assert.ok(f.pending.every(p=>p.path==='/api/create/capacity-preview'));
});
test('invalid quantity never calls preview or creates a Request',async()=>{
  const f=fixture('0');await f.context.checkCurrentEntry(1);
  assert.equal(f.pending.length,0);assert.match(f.errorBox.textContent,/1–20/);
  assert.equal(f.host.innerHTML,'创作条件暂未确认');
});
test('navigation during preview cannot render stale success or error',async()=>{
  for (const failed of [false,true]) {
    const f=fixture();const work=f.context.checkCurrentEntry(1);
    f.context.window.location.href='customer-list';
    if(failed)f.pending[0].reject(Error('old error'));else f.pending[0].resolve({preview:{quantity:1}});
    await work;assert.equal(f.renders.length,0);assert.equal(f.errorBox.textContent,undefined);
  }
});
test('debounce immediately invalidates old confirmation and only checks latest input',()=>{
  const schedule=source.slice(source.indexOf('  function schedulePreview('),source.indexOf('  const deliveryViews'));
  const timers=new Map(),checks=[];let count=0;
  const form={classList:{contains(){return false;}}},host={innerHTML:'old-confirmation'};
  const context=vm.createContext({preparing:false,previewTimer:null,previewVersion:0,confirmationKey:'old',
    document:{querySelector:s=>s==='#content-entry-form'?form:host},CreationState:s=>s.title,
    setTimeout:fn=>{timers.set(++count,fn);return count;},clearTimeout:id=>timers.delete(id),checkCurrentEntry:v=>checks.push(v)});
  vm.runInContext(schedule,context);context.schedulePreview();context.schedulePreview();
  assert.equal(timers.size,1);assert.equal(context.confirmationKey,null);
  assert.equal(host.innerHTML,'正在检查创作条件');assert.equal(checks.length,0);
  [...timers.values()][0]();assert.deepEqual(checks,[2]);
});
test('a completed stale preparation cannot unlock a newer page operation',async()=>{
  const code=source.slice(source.indexOf('  function preparationOperation('),source.indexOf('  function renderRequestEstablished('));
  const form={dataset:{}},host={innerHTML:''};let release;
  const response=new Promise(resolve=>release=resolve);
  const context=vm.createContext({entryVersion:1,preparing:false,window:{location:{href:'same-route'}},
    document:{querySelector:s=>s==='#content-entry-form'?form:host},createPreparationOperation,
    api:()=>response,CreationState:s=>s.title,lockEntryForm(){}});
  vm.runInContext(code,context);
  const resume=context.preparationOperation({requested_quantity:1,confirmed_quantity:1,idempotency_key:'original_once'});
  const work=resume();assert.equal(context.preparing,true);
  context.entryVersion=2;context.preparing=true;release({result:{request_id:'old_request'}});
  await work;assert.equal(context.preparing,true);
});
