import test from 'node:test';
import assert from 'node:assert/strict';
import {createContentOperationsViews} from '../../static/assets/content-operations-views.js';

test('same-URL reopened history cannot display an earlier actor response',async()=>{
  const oldWindow=globalThis.window;
  globalThis.window={location:{href:'http://fixture/customers/customer/content',search:''}};
  let finish;const delayed=new Promise(resolve=>{finish=resolve;});let phase=0;
  const record=actor=>({customer:{display_name:actor},records:[],page_size:20,total:0});
  const history=actor=>({batches:[{batch_id:actor,mode:'free',actual_target:1,control:'resume'}],blocked:[]});
  const api=path=>{
    if(path.includes('content-operations'))return Promise.reject(Error('Overview unavailable'));
    if(phase===0)return delayed.then(()=>path.includes('creation-records') ? record('old_actor') : history('old_actor'));
    return Promise.resolve(path.includes('creation-records') ? record('current_actor') : history('current_actor'));
  };
  const app={innerHTML:''};
  const views=createContentOperationsViews({app,api,shell:(_,markup)=>markup,bindCommonActions(){},pageHeading:(_,title,description)=>title+description,
    skeletonPage(){},renderLoadError(){throw Error('Unexpected page failure');}});
  try {
    const old=views.renderContentOperations('customer');phase=1;
    await views.renderContentOperations('customer');const current=app.innerHTML;
    finish();await old;
    assert.equal(app.innerHTML,current);assert.match(current,/current_actor/);assert.doesNotMatch(current,/old_actor/);
  } finally {globalThis.window=oldWindow;}
});
