import test from 'node:test';
import assert from 'node:assert/strict';
import { createExcelPreviewViews } from '../../static/assets/case-excel-preview-view.mjs';

function fixture({confirmed=false,loseResponse=false}={}){
  const batch='import_'+'a'.repeat(32), head='b'.repeat(64), operation='import_original';
  const nodes=new Map();
  const previous={document:globalThis.document,window:globalThis.window,location:globalThis.location};
  const location=new URL(`http://fixture.invalid/cases/excel-imports/${batch}?operation=${operation}`);
  globalThis.window={location};globalThis.location=location;
  globalThis.document={getElementById:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);}};
  const record={batch:{batch_id:batch,row_refs:[]},rows:[],head_sha256:head,
    can_dispatch:false,can_approve:false,can_share:false,
    operations:[{intent_sha256:head,intent:{operation_id:operation,dispatch_model:false,action:'save_unverified_candidates',selected_rows:[]},result:null}]};
  const calls=[],dialogs=[],navigations=[];
  const views=createExcelPreviewViews({app:{innerHTML:''},shell:(_title,body)=>body,bindCommonActions:()=>{},
    navigate:(...args)=>navigations.push(args),openModal:async options=>{dialogs.push(options);return {confirmed};},
    api:async(path,options={})=>{
      calls.push({path,options});if(!options.method)return record;
      if(loseResponse)throw Error('response unknown');
      const body=JSON.parse(options.body);
      return {result:{schema_version:'case-excel-import-result-v0.2-proposal',state:'cancelled_remaining',row_results:[],
        operation_id:body.operation_id,model_dispatched:false,case_approved:false,shared_published:false}};
    }});
  return {batch,head,operation,calls,dialogs,navigations,nodes,views,
    cleanup:()=>{views.dispose();Object.assign(globalThis,previous);}};
}

test('ending remaining rows needs the existing page confirmation and binds the exact Native head',async()=>{
  for(const confirmed of [false,true]){
    const f=fixture({confirmed});try{
      await f.views.renderImportResult(f.batch);
      assert.equal(f.nodes.get('excel-flow-back').textContent,'结束未保存部分');
      await f.nodes.get('excel-flow-back').onclick();
      assert.equal(f.dialogs.length,1);
      assert.match(f.dialogs[0].description,/已经保存的投稿与历史记录会保留/);
      const writes=f.calls.filter(c=>c.options.method==='POST');
      assert.equal(writes.length,confirmed?1:0);
      if(confirmed){
        assert.equal(writes[0].path,`/api/case-excel/imports/${f.batch}/cancel`);
        assert.equal(JSON.parse(writes[0].options.body).expected_head_sha256,f.head);
        assert.match(f.navigations[0][0],/operation=import_/);
      }
    }finally{f.cleanup();}
  }
});

test('unknown recovery response switches to GET-only reread without generating a new save intent',async()=>{
  const f=fixture({loseResponse:true});try{
    await f.views.renderImportResult(f.batch);
    await f.nodes.get('excel-flow-primary').onclick();
    const write=f.calls.find(c=>c.options.method==='POST');
    assert.equal(write.path,`/api/case-excel/imports/${f.batch}/recover`);
    assert.deepEqual(JSON.parse(write.options.body),{operation_id:f.operation,intent_sha256:f.head});
    assert.equal(f.nodes.get('excel-flow-primary').textContent,'重新读取保存状态');
    assert.equal(f.navigations.length,0);
    await f.nodes.get('excel-flow-primary').onclick();
    assert.equal(f.calls.filter(c=>c.options.method==='POST').length,1);
    assert.equal(f.calls.at(-1).options.method,undefined);
    assert.equal(f.dialogs.length,0);
  }finally{f.cleanup();}
});
