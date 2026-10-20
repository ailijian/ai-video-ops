import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {CreationCapacityState} from '../../static/assets/creation-components.js';
import {createNovelNewsViews} from '../../static/assets/novel-news-views.js';
import {createNewsDeliveryViews} from '../../static/assets/news-delivery-views.js';
import {createPreparationOperation} from '../../static/assets/creation-entry-flow.js';

const escapeHtml = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const opportunity = (id, status='supported') => ({concept_id:id, central_claim:'套餐29元，仅限自取',
  why_publish:'已确认的价格和适用条件',novelty_status:'novel',production_feasibility:{status}});
function hostFixture(kind='novel') {
  let html='', selected='price_one';
  const button={disabled:false,isConnected:true,addEventListener(event,fn){this[event]=fn;}};
  const marker=kind==='novel'?'data-confirm-novel':'data-news-create-request';
  return {button,get html(){return html;},select(value){selected=value;},
    host:{get innerHTML(){return html;},set innerHTML(v){html=v;},querySelector(selector){
      if(selector===`[${marker}]`)return html.includes(marker)?button:null;
      if(selector.includes(':checked'))return {value:selected};return null;
    }},};
}

test('common capacity presentation preserves Mix counts and no-padding/media boundaries',()=>{
  const html=CreationCapacityState({requested:4,available:3,confirmed:3,limited:true});
  assert.match(html,/计划数量[\s\S]*4[\s\S]*内容方向[\s\S]*3[\s\S]*本次确认[\s\S]*3/);
  assert.match(html,/不会为了凑够数量重复/);assert.match(html,/不代表已获得相关素材使用权/);
  assert.match(html,/creation-state-warning/);
});

test('News shows its real one-video limit and restores the previous Mix quantity',async()=>{
  const source=await readFile(new URL('../../static/assets/content-views.js',import.meta.url),'utf8');
  const code=source.slice(source.indexOf('  function syncProfileSpecificUi()'),source.indexOf('  function syncSpeakerOptions('));
  const quantity={value:'4',max:'20',dataset:{}},hint={},field={},submit={closest:()=>null};
  const form={classList:{contains:()=>false}},mode={};
  const nodes={'#create-quantity':quantity,'#create-quantity-field':field,'#create-quantity-hint':hint,
    '#check-content-capacity':submit,'#content-entry-form':form,'#create-news-modes':mode};
  let profile='news';const context=vm.createContext({selectedProfileValue:()=>profile,document:{querySelector:s=>nodes[s]}});
  vm.runInContext(code,context);context.syncProfileSpecificUi();
  assert.equal(field.hidden,false);assert.equal(quantity.value,'1');assert.equal(quantity.max,'1');
  assert.equal(quantity.readOnly,true);assert.equal(quantity.disabled,false);assert.match(hint.textContent,/短信息不另计条数/);
  profile='mix';context.syncProfileSpecificUi();
  assert.equal(quantity.value,'4');assert.equal(quantity.max,'20');assert.equal(quantity.readOnly,false);
});

function novelFixture(api) {
  const f=hostFixture(),intents=[],stages=[];
  const view=createNovelNewsViews({api,escapeHtml,showToast(){}});
  view.renderPreview(f.host,{production_ready_count:1,opportunities:[opportunity('price_one')]},{
    businessId:'business_A',speakerId:'speaker_A',requestedQuantity:1,
    createPreparation(confirmation){intents.push(confirmation);
      const op=createPreparationOperation({api,confirmation,onStage:s=>stages.push(s)});
      return ()=>op.continue();},
  });
  return {...f,intents,stages};
}

test('Novel uses the shared confirmation and prepares sources once without generation or approval',async()=>{
  const calls=[],f=novelFixture(async(path,options)=>{
    calls.push({path,body:options.body ? JSON.parse(options.body) : null});return {result:{request_id:'gen_original_A'}};
  });
  assert.equal(calls.length,0);assert.match(f.html,/计划数量/);assert.match(f.html,/本次确认/);
  assert.doesNotMatch(f.html,/按这一个方向继续|选择一个新内容方向/);
  await Promise.all([f.button.click(),f.button.click()]);
  assert.deepEqual(calls.map(c=>c.path),['/api/create/confirm','/api/create/gen_original_A/resolve-sources']);
  assert.equal(f.intents.length,1);assert.equal(calls[0].body.selected_opportunity_id,'price_one');
  assert.equal(calls[0].body.requested_quantity,1);assert.equal(calls[0].body.confirmed_quantity,1);
});

test('a source interruption continues the original Novel Request and exact intent',async()=>{
  const calls=[],f=novelFixture(async(path,options)=>{
    calls.push({path,body:options.body ? JSON.parse(options.body) : null});
    if(calls.length===2)throw Error('source interrupted');
    return {result:{request_id:'gen_original_A'}};
  });
  await f.button.click();f.select('a_different_opportunity');await f.button.click();
  assert.equal(f.intents.length,1);
  assert.deepEqual(calls.map(c=>c.path),['/api/create/confirm','/api/create/gen_original_A/resolve-sources','/api/create/gen_original_A/resolve-sources']);
  assert.equal(f.intents[0].selected_opportunity_id,'price_one');
});

test('a lost Novel confirmation response reuses its exact key and selection',async()=>{
  const calls=[],f=novelFixture(async(path,options)=>{
    calls.push({path,body:options.body ? JSON.parse(options.body) : null});if(calls.length===1)throw Error('response lost');
    return {result:{request_id:'gen_original_A'}};
  });
  await f.button.click();await f.button.click();
  assert.deepEqual(calls[0],calls[1]);assert.equal(f.intents.length,1);
});

test('Novel cannot upgrade unsupported, old, or inconsistent coverage into a confirm action',()=>{
  for(const projection of [
    {production_ready_count:0,opportunities:[opportunity('price_one','unsupported')]},
    {production_ready_count:0,opportunities:[opportunity('price_one')]},
    {production_ready_count:1,opportunities:[{...opportunity('price_one'),novelty_status:'already_communicated'}]},
  ]) {
    const f=hostFixture();createNovelNewsViews({api(){throw Error('Unexpected API');},escapeHtml,showToast(){}})
      .renderPreview(f.host,projection,{businessId:'business_A',speakerId:'speaker_A',createPreparation(){throw Error('Unauthorized confirmation');}});
    assert.doesNotMatch(f.html,/data-confirm-novel/);
  }
});

test('Repurpose replays the original request identity after a lost response',async()=>{
  const f=hostFixture('repurpose'),calls=[],restores=[];
  const view=createNewsDeliveryViews({escapeHtml,showToast(){},api:async(path,options)=>{
    calls.push({path,body:options.body ? JSON.parse(options.body) : null});if(calls.length===1)throw Error('response lost');
    return {result:{request:{request_id:'news_original_B'},recovered:true}};
  }});
  view.renderPreview(f.host,{available:true,business_id:'business_B',speaker_id:'speaker_B',eligible_sources:[{
    source_content_id:'price_one',source_title:'已批准的历史内容',recommended_slot_count:4,
  }]},{onRequestCreated:rid=>restores.push(rid)});
  assert.match(f.html,/计划数量/);assert.match(f.html,/4 段短信息/);assert.doesNotMatch(f.html,/建议 4 条/);
  await f.button.click();await f.button.click();await f.button.click();
  assert.equal(calls.length,2);assert.deepEqual(calls[0],calls[1]);
  assert.ok(calls.every(c=>c.path==='/api/create/news/request'));
  assert.deepEqual(restores,['news_original_B','news_original_B']);
});
