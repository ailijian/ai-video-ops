import test from 'node:test';
import assert from 'node:assert/strict';
import {capacityMarkup,createCapacityViews} from '../../static/assets/creative-capacity-view.mjs';

function projection() {return {schema_version:'creative-capacity-read-projection-v1.0', business_id:'customer_a',speaker_id:'speaker_a',
  authority:{authorizes_execution:false},new_semantic_inventory:{qualified_count:1},new_expression_inventory:{qualified_source_count:0,sources:[{title:'<script>alert(1)</script>',eligibility:'blocked',blocker_code:'capacity_insufficient',presentation_count:0}]},
  target_gap:{news_novel_target:10,novel_shortfall:9,diagnostic_reasons:[{code:'HISTORICAL_CORE_EXPLICIT',count:2}]},structure_qualification:[{type_id:'news',structure_status:'qualified',structural_case_count:3}]};}
test('separate inventories, deficits and escaped approved-source titles; no execution action',()=>{
  const html=capacityMarkup(projection(),'/create/config');
  assert.match(html,/capacity-novel">1/);assert.match(html,/capacity-repurpose">0/);assert.match(html,/capacity-gap">9/);
  assert.match(html,/不等于可制作视频数量/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|开始创作<\/button/);
  assert.throws(()=>capacityMarkup({...projection(),authority:{authorizes_execution:true}},'/'));
});
test('unknown reader quantity does not render as zero',()=>{
  const data=projection();data.new_semantic_inventory.qualified_count=null;data.target_gap.novel_shortfall=null;
  assert.match(capacityMarkup(data,'/'),/capacity-novel">待核对/);
});
test('changed route discards an old async response; refresh always reads Native again',async()=>{
  const oldWindow=globalThis.window,oldDocument=globalThis.document;
  let resolve,reads=0,writes=0,click;
  globalThis.window={location:{href:'http://fixture/create/capacity?business_id=customer_a&speaker_id=speaker_a',search:'?business_id=customer_a&speaker_id=speaker_a'}};
  globalThis.document={getElementById:()=>({addEventListener:(_,handler)=>{click=handler;}})};
  const app={set innerHTML(value){writes++;}};
  const view=createCapacityViews({app,api:async()=>{reads++;if(reads===1)return await new Promise(done=>{resolve=done;});return {projection:projection()};},shell:(_,html)=>html,bindCommonActions(){},skeletonPage(){},renderLoadError(_,e){throw e;}});
  try {
    const pending=view.renderCapacity();window.location.href='http://fixture/elsewhere';resolve({projection:projection()});await pending;assert.equal(writes,0);
    window.location.href='http://fixture/create/capacity?business_id=customer_a&speaker_id=speaker_a';
    await view.renderCapacity();assert.equal(writes,1);await click();assert.equal(reads,3);
  } finally {globalThis.window=oldWindow;globalThis.document=oldDocument;}
});
