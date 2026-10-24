import test from 'node:test';
import assert from 'node:assert/strict';
import { mountFiniteSelection,mountFiniteResult } from '../../static/assets/case-excel-orchestration.mjs';
import { supplementImportPath } from '../../static/assets/case-excel-import-session.mjs';
import { safeExcelReturn } from '../../static/assets/routes.js';
import { createExcelPreviewViews } from '../../static/assets/case-excel-preview-view.mjs';

const batch='import_'+'a'.repeat(32),ref={row_id:'row_a',row_sha256:'b'.repeat(64)};
test('source supplement return is local, exact and survives login',()=>{
 const path=supplementImportPath(batch);assert.equal(safeExcelReturn(path),path);
 assert.throws(()=>supplementImportPath('../other'));
 assert.equal(safeExcelReturn('/cases/excel-preview?supplement=foreign'),null);
 assert.equal(safeExcelReturn('//evil.test'+path),null);
});

test('all-pending preview offers supplementation and never POSTs finite dispatch',async()=>{
 const prior=globalThis.document;const calls=[],routes=[],frames=[];
 const checked={dataset:{finiteRow:'row_a'}},choices={addEventListener:()=>{},querySelectorAll:s=>s.includes(':checked')?[checked]:[],querySelector:()=>({addEventListener:()=>{}})};
 globalThis.document={createElement:()=>choices};
 const content={replaceChildren:()=>{},querySelector:()=>({focus:()=>{}})};
 try{
  mountFiniteSelection({record:{batch:{batch_id:batch},rows:[{...ref,raw_case:{source_title:'待补证'}}]},rows:[{ref,result:{candidate_ref_sha256:'c'.repeat(64)}}],
   operation:'save_one',content,api:async(path,options)=>{calls.push({path,options});return {new_task_count:0,items:[{row:ref,relation:'pending_source'}]};},
   footer:(label,options)=>frames.push({label,options}),message:()=>{},navigate:p=>routes.push(p),lease:{current:()=>true},signal:new AbortController().signal,bindRoutes:()=>{}});
  await frames.at(-1).options.action();assert.equal(frames.at(-1).label,'补充对应视频');
  frames.at(-1).options.action();assert.equal(routes.at(-1),supplementImportPath(batch));
  assert.equal(calls.length,1);assert.match(calls[0].path,/orchestration-preview$/);
 }finally{globalThis.document=prior;}
});

test('historical all-pending results remain GET-only and no longer show handled success',async()=>{
 const calls=[],frames=[],routes=[],content={querySelectorAll:()=>[]};
 await mountFiniteResult({batch,id:'orch_'+'d'.repeat(32),content,
  api:async(path,options)=>{calls.push({path,options});return {schema_version:'case-excel-orchestration-result-projection-v1.0',
   actual_new_task_count:0,planned_new_task_count:0,submission_complete:true,control_state:'active',rows:[{state:'pending_source',task_id:null}]};},
  footer:(label,options)=>frames.push({label,options}),message:()=>{},navigate:p=>routes.push(p),lease:{current:()=>true},signal:new AbortController().signal,bindRoutes:()=>{},openModal:()=>{}});
 assert.match(content.innerHTML,/未启动解析/);assert.doesNotMatch(content.innerHTML,/本次解析提交已处理/);
 assert.equal(frames.at(-1).label,'补充对应视频');frames.at(-1).options.action();
 assert.equal(routes.at(-1),supplementImportPath(batch));assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
});

test('supplement entry checks original private scope before allowing a file or upload',async()=>{
 const prior={document:globalThis.document,window:globalThis.window,location:globalThis.location};const nodes=new Map(),calls=[];
 const location=new URL('http://fixture.invalid'+supplementImportPath(batch));globalThis.location=location;globalThis.window={location};
 globalThis.document={getElementById:id=>{if(!nodes.has(id))nodes.set(id,{addEventListener:()=>{}});return nodes.get(id);}};
 const routes=[];const views=createExcelPreviewViews({app:{},shell:(_,body)=>body,bindCommonActions:()=>{},navigate:p=>routes.push(p),
  api:async(path,options)=>{calls.push({path,options});throw Error('original private record unavailable');},openModal:()=>{}});
 try{
  await views.renderExcelPreview();assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
  assert.equal(nodes.get('excel-flow-primary').textContent,'返回我的投稿');
  nodes.get('excel-flow-primary').onclick();assert.equal(routes.at(-1),'/cases?view=mine');
 }finally{views.dispose();Object.assign(globalThis,prior);}
});

test('lost-response recovery cannot replay an old all-pending confirmation into a new submit',async()=>{
 const previous=globalThis.sessionStorage,calls=[],frames=[];
 globalThis.sessionStorage={getItem:()=>JSON.stringify({preview:{new_task_count:0,items:[{row:ref,relation:'pending_source'}]}})};
 try{
  await mountFiniteResult({batch,id:'orch_'+'e'.repeat(32),content:{},api:async(path,options)=>{calls.push({path,options});throw Object.assign(Error('not saved'),{status:404});},
   footer:(label,options)=>frames.push({label,options}),message:()=>{},navigate:()=>{},lease:{current:()=>true},signal:new AbortController().signal,bindRoutes:()=>{},openModal:()=>{}});
  assert.equal(frames.at(-1).label,'补充对应视频');assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
 }finally{globalThis.sessionStorage=previous;}
});
