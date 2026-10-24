import test from 'node:test';
import assert from 'node:assert/strict';
import { createExcelImportSession, projectImportRecord, validatePrivateResult, importResultPath } from '../../static/assets/case-excel-import-session.mjs';
import { matchWorkflowRoute, safeExcelReturn, excelLoginPath } from '../../static/assets/routes.js';

const batchId='import_'+'1'.repeat(32),intentSha='b'.repeat(64);
const file={name:'fictional.xlsx',size:4,arrayBuffer:async()=>new Uint8Array([1,2,3,4]).buffer};
const preview=()=>({schema_version:'case-excel-preview-v0.3',file_sha256:'a'.repeat(64),registry_sha256:'c'.repeat(64),issues:[],excluded_sheets:[],
 authority:{can_persist:false,can_dispatch:false,can_approve:false,can_share:false},rows:[5,6].map(n=>({row:n,status:'unverified_preview',issues:[],external_case_key:'key-'+n,
 canonical_source_key:'douyin:799999999999999970'+n,raw:{source_title:'虚构'+n,source_url:'https://www.douyin.com/video/799999999999999970'+n,video_content_type_hint:'故事型'}}))});
const rowRef=n=>({row_id:'row_'+n,row_sha256:String(n).repeat(64)});
function context(input,p=preview()){
 const refs=[5,6].map(n=>({...rowRef(n),source_row:n}));
 return {batch:{batch_id:batchId,file_sha256:p.file_sha256,row_refs:refs},preview:p,batch_sha256:'d'.repeat(64),intent_sha256:intentSha,
  intent:{operation_id:input.operation_id,batch_id:batchId,action:'save_unverified_candidates',dispatch_model:false,expected_head_sha256:null,selected_rows:refs.filter(r=>input.selected_rows.includes(r.source_row)).map(({row_id,row_sha256})=>({row_id,row_sha256}))}};
}
const result=(op='import_one',rows=[5,6])=>({schema_version:'case-excel-import-result-v0.2-proposal',operation_id:op,intent_sha256:intentSha,state:'saved',model_dispatched:false,case_approved:false,shared_published:false,
 row_results:rows.map(n=>({row_id:'row_'+n,state:'pending_source',candidate_ref_sha256:'e'.repeat(64)}))});
function harness({prepare=p=>context(p),save=p=>({batch_id:batchId,result:result(p.operation_id,p.selected_rows)}),previewRead=()=>preview(),upload}={}){
 const calls=[],prepared=[],saved=[];
 const session=createExcelImportSession({api:async(path,options)=>{const input=path.endsWith('/preview')?null:JSON.parse(options.body);calls.push({path,input});
  if(path.endsWith('/preview'))return {preview:await previewRead()};
  if(path.endsWith('/prepare'))return prepare(input);
  if(path.endsWith('/save'))return save(input);
  throw Error('Unexpected API');},onPrepared:id=>prepared.push(id),onSaved:id=>saved.push(id),upload});
 return {session,calls,prepared,saved};
}

test('selecting a file auto-checks only; one explicit save pins the exact selected rows and uses native prepare/save once',async()=>{
 const h=harness();await h.session.choose(file);
 assert.equal(h.session.snapshot().phase,'review');assert.deepEqual(h.session.snapshot().selected,[5,6]);assert.equal(h.calls.length,1);
 h.session.select(6,false);assert.deepEqual(h.session.snapshot().selected,[5]);assert.equal(h.calls.length,1,'selection is not persistence');
 await Promise.all([h.session.save(),h.session.save()]);
 assert.deepEqual(h.calls.map(c=>c.path),['/api/case-excel/preview','/api/case-excel/imports/prepare','/api/case-excel/imports/save']);
 assert.deepEqual(h.calls[1].input.selected_rows,[5]);assert.deepEqual(h.calls[2].input.selected_rows,[5]);
 assert.equal(h.calls[1].input.operation_id,h.calls[2].input.operation_id);assert.equal(h.calls[2].input.intent_sha256,intentSha);
 assert.deepEqual(h.prepared,h.saved);assert.equal(h.session.snapshot().phase,'saved');
 await h.session.save();assert.equal(h.calls.length,3,'completed state has no replay/save action');
});

test('zero selection and invalid rows cannot start persistence',async()=>{
 const p=preview();p.rows[1].status='invalid';const h=harness({previewRead:()=>p});await h.session.choose(file);
 h.session.select(6,true);assert.deepEqual(h.session.snapshot().selected,[5]);h.session.select(5,false);
 await h.session.save();assert.equal(h.calls.length,1);
});

test('video upload and source consent remain explicit, before any upload or prepare',async()=>{
 let uploads=0;const h=harness({upload:async()=>{uploads++;return {upload_id:'f'.repeat(32)};}});await h.session.choose(file);
 await h.session.save([{sourceRow:5,file:{name:'fake.mp4',size:100,type:'video/mp4'},rightsConfirmed:false}]);
 assert.equal(uploads,0);assert.equal(h.calls.length,1);assert.equal(h.session.snapshot().phase,'review');assert.match(h.session.snapshot().message,/上传权限/);
});

test('changed preview requires a new visible decision and does not silently save a reduced selection',async()=>{
 const changed=preview();changed.rows[1].status='invalid';const h=harness({prepare:p=>context(p,changed)});await h.session.choose(file);await h.session.save();
 assert.equal(h.session.snapshot().phase,'review');assert.deepEqual(h.session.snapshot().selected,[5]);assert.match(h.session.snapshot().message,/核对结果已变化/);
 assert.equal(h.calls.filter(c=>c.path.endsWith('/save')).length,0);assert.equal(h.prepared.length,0);
});

test('changed native row identity, file identity or dispatch permission blocks the save',async()=>{
 for(const mutate of [c=>c.intent.selected_rows.reverse(),c=>c.batch.file_sha256='f'.repeat(64),c=>c.intent.dispatch_model=true]){
  const h=harness({prepare:p=>{const c=context(p);mutate(c);return c;}});await h.session.choose(file);await h.session.save();
  assert.equal(h.session.snapshot().phase,'review');assert.equal(h.prepared.length,0);assert.equal(h.calls.filter(c=>c.path.endsWith('/save')).length,0);
 }
});

test('unknown response preserves the original identity and never automatically resubmits or replaces the file',async()=>{
 const h=harness({save:()=>{throw Error('connection lost');}});await h.session.choose(file);await h.session.save();
 assert.equal(h.session.snapshot().phase,'uncertain');const identity=h.session.snapshot().identity;assert.deepEqual(identity,h.prepared[0]);
 await h.session.save();await h.session.choose({...file,name:'another.xlsx'});
 assert.equal(h.calls.length,3);assert.deepEqual(h.session.snapshot().identity,identity);assert.equal(h.session.snapshot().file.name,'fictional.xlsx');
});

test('a foreign result or an approval claim cannot become a successful result page',async()=>{
 for(const mutate of [r=>r.batch_id='import_'+'2'.repeat(32),r=>r.result.case_approved=true,r=>r.result.operation_id='import_foreign']){
  const h=harness({save:p=>{const r={batch_id:batchId,result:result(p.operation_id)};mutate(r);return r;}});await h.session.choose(file);await h.session.save();
  assert.equal(h.session.snapshot().phase,'uncertain');assert.equal(h.saved.length,0);
 }
});

test('late preview and prepare responses cannot replace a newer file or navigate after leaving',async()=>{
 let release;const pending=new Promise(resolve=>{release=resolve;});let count=0;
 const second={...preview(),file_sha256:'f'.repeat(64)};
 const h=harness({previewRead:()=>++count===1?pending:second});const first=h.session.choose(file);await h.session.choose({...file,name:'new.xlsx'});release(preview());await first;
 assert.equal(h.session.snapshot().file.name,'new.xlsx');assert.equal(h.session.snapshot().preview.file_sha256,second.file_sha256);
 let finish,entered;const started=new Promise(resolve=>{entered=resolve;});const paused=new Promise(resolve=>{finish=resolve;});
 const next=harness({prepare:async input=>{entered();await paused;return context(input);}});await next.session.choose(file);const saving=next.session.save();await started;next.session.dispose();finish();await saving;
 assert.equal(next.prepared.length,0);assert.equal(next.calls.filter(c=>c.path.endsWith('/save')).length,0);
});

function record(){
 const r=result();const refs=[5,6].map(n=>({...rowRef(n),source_row:n}));
 return {batch:{batch_id:batchId,row_refs:refs},head_sha256:intentSha,can_dispatch:false,can_approve:false,can_share:false,
 rows:[5,6].map(n=>({row_id:'row_'+n,raw_case:{source_title:'case '+n},approval_granted:false,evidence_promoted:false,formal_video_type:null})),
 operations:[{intent:{operation_id:'import_one',dispatch_model:false,selected_rows:refs.map(({row_id,row_sha256})=>({row_id,row_sha256}))},intent_sha256:intentSha,result:r,current_bindings:[]}]};
}
test('refresh projection binds the exact operation; persisted row files alone do not prove completion',()=>{
 const current=record();assert.equal(projectImportRecord(current,'import_one').saved,2);assert.equal(projectImportRecord(current,'import_missing').status,'unknown');
 current.operations[0].result=null;const pending=projectImportRecord(current,'import_one');assert.equal(pending.status,'incomplete');assert.equal(pending.saved,null);
});
test('partial, linked and cancelled results keep their actual quantities and private authority boundaries',()=>{
 const current=record();current.operations[0].result.state='partially_saved';current.operations[0].result.row_results[0].state='already_recorded_private';current.operations[0].result.row_results[1]={row_id:'row_6',state:'invalid',candidate_ref_sha256:null};
 const p=projectImportRecord(current);assert.equal(p.saved,1);assert.equal(p.linked,1);assert.equal(p.total,2);assert.equal(p.status,'partially_saved');
 current.rows[0].approval_granted=true;assert.throws(()=>projectImportRecord(current));
 for(const key of ['model_dispatched','case_approved','shared_published'])assert.throws(()=>validatePrivateResult({...result(),[key]:true}));
 assert.throws(()=>validatePrivateResult({...result(),schema_version:'unknown'}));
});
test('independent result routes and login return preserve only validated local Excel destinations',()=>{
 const path=importResultPath(batchId,'import_one',true);assert.equal(matchWorkflowRoute(path.split('?')[0]).name,'excel-import-result');assert.equal(safeExcelReturn(path),path);
 assert.equal(decodeURIComponent(excelLoginPath(path).split('return_to=')[1]),path);
 for(const value of ['//evil.test','https://evil.test','/\\evil.test','/cases/1234567890','/cases/excel-imports/not-a-batch','/cases/excel-preview/../../workbench'])assert.equal(safeExcelReturn(value),null);
 assert.equal(safeExcelReturn('/cases/excel-imports?page=2&next=https://evil.test'),'/cases/excel-imports?page=2');
 assert.equal(excelLoginPath('/workbench'),'/login');
});
