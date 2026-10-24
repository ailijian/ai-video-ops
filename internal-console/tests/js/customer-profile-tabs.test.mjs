import test from 'node:test';
import assert from 'node:assert/strict';
import {createCustomerViews} from '../../static/assets/customer-views.js';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function tabFixture({authorized=true,pending=true,speakers=[],readApi}={}) {
  let renders=0,amendment=null,recovery=false;const requests=[],bindings=[];
  let shortcut=null,panelHtml='';
  const actions={innerHTML:''},feedback={hidden:true,textContent:''};
  const panel={dataset:{activeProfileTab:'overview'},get innerHTML(){return panelHtml;},set innerHTML(html){
    panelHtml=html;
    shortcut=html.includes('data-open-customer-correction')?{events:{},addEventListener(n,fn){this.events[n]=fn;}}:null;
  },querySelector:s=>s==='[data-open-customer-correction]'?shortcut:null};
  const createAmendment=()=>({field:'public_display_name',value:'原资料',open:false,hidden:false,focused:false,scrolled:false,
    querySelector(){return {focus(){amendment.focused=true;}};},scrollIntoView(){this.scrolled=true;}});
  const tabs=['overview','profile','speakers','content'].map(id=>({dataset:{profileTab:id},events:{},
    classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(n,fn){this.events[n]=fn;}}));
  const main={querySelectorAll:()=>[],firstElementChild:{},insertAdjacentHTML(position,html){
    if(html.includes('data-review-amendment')) amendment=createAmendment();
    if(html.includes('review-recovery')) recovery=true;
  }};
  const app={set innerHTML(value){renders++;amendment=null;recovery=false;
    panel.dataset.activeProfileTab=value.match(/data-active-profile-tab="([^"]+)"/)?.[1] || 'overview';
    panel.innerHTML=value;
    if(value.includes('data-review-amendment')) amendment=createAmendment();
  },querySelector:s=>s==='main'||s==='.customer-detail-page'?main:s==='.profile-tab-panel'?panel:s==='[data-review-amendment]'?amendment:s==='[data-customer-profile-actions]'?actions:s==='[data-speaker-status-feedback]'?feedback:null};
  const detail={business_id:'fictional',display_name:'虚构客户',status:'approved',industry:'餐饮',
    business_persona:{facts:[{field:'public_display_name',state:'known',value:'虚构客户'}]},
    amendable_fields:['public_display_name'],approval_context:authorized?{token:'opaque-context'}:null,speakers};
  const view=createCustomerViews({app,api:async(url,options)=>{requests.push({url,options});if(readApi) {const result=await readApi(url,detail);if(result) return result;}return url.includes('review-commands')?
    {operations:pending?[{request_path:'/api/customers/fictional/approve',payload:{},operation_id:'original',can_discard:false}]:[]}:detail;},
    shell:(_,html)=>html,bindCommonActions:root=>bindings.push(root),pageHeading:()=>'',skeletonPage(){},renderLoadError(_,e){throw e;}});
  return {view,app,panel,tabs,requests,bindings,detail,actions,feedback,get renders(){return renders;},get amendment(){return amendment;},get recovery(){return recovery;},get shortcut(){return shortcut;}};
}

async function withPage(options,run) {
  const old={document:globalThis.document,location:globalThis.location,history:globalThis.history};
  const f=tabFixture(options);
  globalThis.document=Object.assign(new EventTarget(),{visibilityState:'visible',querySelector:()=>null,querySelectorAll:s=>s.includes('data-profile-tab')?f.tabs:[]});
  globalThis.location={pathname:'/customers/fictional',hash:options.hash || ''};
  globalThis.history={replaceState(_,__,url){location.hash=url.slice(url.indexOf('#'));}};
  try {await f.view.renderCustomerDetail('fictional');await run(f);}
  finally {f.view.stopTaskPolling();Object.assign(globalThis,old);}
}

test('finished speaker analysis updates the existing customer tab and actions without losing correction drafts or recovery',async()=>{
  const oldWindow=globalThis.window;
  const win=new EventTarget(),timers=new Map();let timerId=0;
  win.setTimeout=fn=>{timers.set(++timerId,fn);return timerId;};win.clearTimeout=id=>timers.delete(id);globalThis.window=win;
  const speaker={speaker_id:'person',display_name:'虚构人物',status:'analyzing',task:{task_id:'task-person',task_type:'speaker_analysis',subject_ref:'person',status:'running',payload:{business_id:'fictional'}}};
  let terminal=false;
  try {
    await withPage({hash:'#speakers',speakers:[speaker],readApi:async(url,detail)=>{
      if(url==='/api/tasks/task-person') return {task:{...speaker.task,status:terminal?'awaiting_review':'running'}};
      if(url==='/api/customers/fictional' && terminal) return {...detail,speakers:[{...speaker,status:'fact_review_required',task:{...speaker.task,status:'awaiting_review'}}]};
    }},async f=>{
      await new Promise(setImmediate);
      assert.equal(f.requests.filter(v=>v.url==='/api/tasks/task-person').length,1);
      const form=f.amendment;form.open=true;form.value='未提交更正';
      terminal=true;const tick=[...timers.values()][0];assert.ok(tick);tick();await new Promise(setImmediate);
      assert.match(f.panel.innerHTML,/信息待确认/);assert.match(f.actions.innerHTML,/确认出镜人信息/);
      assert.equal(location.hash,'#speakers');assert.equal(f.renders,1);assert.equal(f.amendment,form);
      assert.equal(form.value,'未提交更正');assert.equal(form.open,true);assert.equal(form.hidden,true);assert.equal(f.recovery,true);
      assert.ok(f.requests.every(v=>v.options===undefined));assert.equal(timers.size,0);
    });
  } finally {globalThis.window=oldWindow;}
});

test('tab navigation preserves the existing correction form, draft and original recovery entry',async()=>{
  await withPage({},async f=>{
    const form=f.amendment;assert.ok(form&&f.recovery);
    form.open=true;form.field='public_display_name';form.value='尚未提交的更正';
    for(const id of ['profile','speakers','overview','overview']) {
      f.tabs.find(t=>t.dataset.profileTab===id).events.click({preventDefault(){}});
      assert.equal(f.renders,1,'switching a tab must not replace the whole customer page');
      assert.equal(f.amendment,form);assert.equal(f.amendment.value,'尚未提交的更正');assert.equal(f.amendment.open,true);
      assert.equal(form.hidden,id!=='profile','the retained form belongs only to customer information');
      assert.equal(f.recovery,true);assert.equal(f.panel.dataset.activeProfileTab,id);
    }
    assert.equal(f.requests.length,2);assert.ok(f.requests.every(r=>r.options===undefined));
    assert.ok(f.bindings.slice(1).every(root=>root===f.panel),'only the replaced panel gets route bindings');
  });
});

test('tab navigation cannot create a correction form without its authorized context',async()=>{
  await withPage({authorized:false,pending:false},async f=>{
    for(const id of ['profile','overview']) f.tabs.find(t=>t.dataset.profileTab===id).events.click({preventDefault(){}});
    assert.equal(f.amendment,null);assert.equal(f.recovery,false);assert.equal(f.renders,1);
    assert.equal(f.shortcut,null,'no correction shortcut without the authorized form');
  });
});

test('overview shortcut switches to customer information and opens the same form in one action',async()=>{
  await withPage({},async f=>{
    const form=f.amendment;assert.equal(form.hidden,true);assert.equal(form.open,false);
    assert.ok(f.shortcut);
    f.shortcut.events.click({preventDefault(){}});
    assert.equal(location.hash,'#profile');assert.equal(f.panel.dataset.activeProfileTab,'profile');
    assert.equal(f.amendment,form);assert.equal(form.hidden,false);assert.equal(form.open,true);
    assert.equal(form.focused,true);assert.equal(form.scrolled,true);assert.equal(f.shortcut,null);
    assert.equal(f.recovery,true);assert.equal(f.renders,1);
    assert.equal(f.requests.length,2);assert.ok(f.requests.every(r=>r.options===undefined));
  });
});

test('direct links show corrections only on the owning tab, while recovery stays available',async()=>{
  for(const id of ['overview','profile','speakers','content']) {
    await withPage({hash:`#${id}`},async f=>{
      assert.equal(f.panel.dataset.activeProfileTab,id);
      assert.equal(f.amendment.hidden,id!=='profile');assert.equal(f.amendment.open,false);
      assert.equal(Boolean(f.shortcut),id==='overview');assert.equal(f.recovery,true);
    });
  }
});

test('binding a replacement panel never adds duplicate listeners to persistent account controls',()=>{
  const makeButton=()=>({listeners:[],addEventListener(_,fn){this.listeners.push(fn);}});
  const logout=makeButton(),password=makeButton(),route=makeButton();
  const app={querySelector:()=>null,querySelectorAll:s=>s.includes('logout')?[logout]:s.includes('change-password')?[password]:[]};
  const panel={querySelector:()=>null,querySelectorAll:s=>s==='[data-route]'?[route]:[]};
  const source=readFileSync(new URL('../../static/assets/app.js',import.meta.url),'utf8');
  const start=source.indexOf('function bindCommonActions('),end=source.indexOf('\nfunction pageHeading(',start);
  const scope=vm.createContext({app,navigate(){},logout(){}});vm.runInContext(source.slice(start,end),scope);
  scope.bindCommonActions();scope.bindCommonActions(panel);
  assert.equal(logout.listeners.length,1);assert.equal(password.listeners.length,1);assert.equal(route.listeners.length,1);
});
