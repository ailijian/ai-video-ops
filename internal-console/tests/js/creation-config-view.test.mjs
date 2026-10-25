import test from "node:test";
import assert from "node:assert/strict";
import { createCreationConfigViews, configurationFailureMarkup, scopedConfigurationContext } from "../../static/assets/creation-config-view.mjs";
import { createConfiguration, changeConfiguration } from "../../static/assets/creation-config-model.mjs";

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const options = { customer_context: { business_id: "fictional" }, customers: [{ business_id: "fictional", display_name: "虚构客户",
  business_persona_status: "approved", creation_ready: true, speakers: [{ speaker_id: "speaker", status: "approved", display_name: "虚构人物" }] }] };
test("qualified customer cannot start a batch while deployment availability is closed", () => {
  const context = scopedConfigurationContext({ ...options, creation_batch: { available: false } }, "fictional");
  assert.equal(context.blocked, true);
  assert.match(context.blockReason, /批量创作当前未开放/);
  assert.equal(scopedConfigurationContext({ ...options, creation_batch: { available: true } }, "fictional").blocked, false);
});
function browser() {
  let elements = new Map(), writes = 0, focused = null;
  const previous = { window: globalThis.window, document: globalThis.document };
  globalThis.window = { location: { href: "http://fixture/create/config?business_id=fictional", search: "?business_id=fictional" } };
  function element(id) {
    if (!elements.has(id)) elements.set(id, { id, type: id === "config-cyclesConfirmed" || id === "config-repurposeEnabled" ? "checkbox" : "number",
      handlers: {}, dataset: {}, addEventListener(event, handler) { this.handlers[event] = handler; }, focus() { focused = id; }, scrollIntoView() {},
      firstChild: { textContent: "" }, querySelector() { return element(id + "-child"); }, append(child) { (this.children ||= []).push(child); } });
    return elements.get(id);
  }
  globalThis.document = { getElementById: element, createElement: tag => element(`created-${tag}`), querySelector: element, querySelectorAll(selector) {
    if (selector === "[data-config-mode]" || selector === "[data-config-stage]") return [];
    if (selector === '[data-quantity-step]' || selector.startsWith('[data-quantity-target=') || selector === '[data-repurpose-source]') return [];
    if (selector === ".batch-config-totals dd") return [element("total"), element("delivery"), element("semantic"),element('presentation')];
    return [...elements.values()];
  } };
  const app = { set innerHTML(value) { this.markup = value; elements = new Map(); writes += 1; } };
  return { app, element, get writes() { return writes; }, get focused() { return focused; },
    restore() { globalThis.window = previous.window; globalThis.document = previous.document; } };
}
function view(dom, api, navigate=()=>{}) {
  return createCreationConfigViews({ app: dom.app, api, navigate, shell: (_, html) => html, bindCommonActions() {}, skeletonPage() {}, renderLoadError(title, error) { throw error; } });
}
test('capacity explanation follows the edited Novel target and hides an invalid target',async()=>{
  const dom=browser();
  try {
    await view(dom,async path=>path.includes('options')?options:{revision:0,draft:null}).renderConfiguration();
    assert.match(dom.app.markup,/id="config-capacity-link"/);
    assert.match(dom.app.markup,/<section class="batch-capacity-entry" aria-labelledby="config-capacity-title">/);
    assert.match(dom.app.markup,/查看当前可用的新主题、改编来源/);
    for (const value of ['2','0','40']) {
      dom.element('config-novel').value=value;dom.element('config-novel').handlers.input();
      assert.equal(dom.element('config-capacity-link').hidden,false);
      const url=new URL(dom.element('config-capacity-link').href,'http://fixture');
      assert.equal(url.searchParams.get('novel_target'),value);
      assert.equal(url.searchParams.get('business_id'),'fictional');assert.equal(url.searchParams.get('speaker_id'),'speaker');
    }
    for (const value of ['', '41','-1','1.5']) {
      dom.element('config-novel').value=value;dom.element('config-novel').handlers.input();
      assert.equal(dom.element('config-capacity-link').hidden,true);
      assert.match(dom.element('config-capacity-hint').textContent,/请先填写有效/);
    }
  } finally {dom.restore();}
});
test('restoring an incomplete draft does not turn its missing Novel target into zero',async()=>{
  const dom=browser();
  try {
    const configuration=changeConfiguration(createConfiguration(),'novel','');
    await view(dom,async path=>path.includes('options')?options:{revision:1,draft:{speaker_id:'speaker',configuration}}).renderConfiguration();
    assert.match(dom.app.markup,/id="config-capacity-link" hidden/);
    dom.element('config-novel').value='2';dom.element('config-novel').handlers.input();
    assert.equal(dom.element('config-capacity-link').hidden,false);
    assert.match(dom.element('config-capacity-link').href,/novel_target=2$/);
  } finally {dom.restore();}
});
test("validation links focus the existing field without history navigation or draft replacement", async () => {
  const dom = browser();
  try {
    await view(dom, async path => path.includes("options") ? options : { revision: 0, draft: null }).renderConfiguration();
    const writes = dom.writes; let prevented = false;
    const click = () => dom.element("batch-config-errors").handlers.click({ target: { closest: () => ({ hash: "#config-persona" }) }, preventDefault() { prevented = true; } });
    click(); assert.equal(prevented, true); assert.equal(dom.focused, "config-persona"); assert.equal(dom.writes, writes);
    dom.element("config-persona").value = "7";
    dom.element("config-persona").handlers.input(); // Rebuilds the error links.
    prevented = false; click(); assert.equal(prevented, true); assert.equal(dom.writes, writes);
  } finally { dom.restore(); }
});

test('an obsolete confirmation cannot navigate away from reopened configuration',async()=>{
  const dom=browser(),pending=deferred(),entered=deferred(),navigations=[];
  const state=changeConfiguration(createConfiguration('free'),'persona',1);
  const saved={revision:1,operation_id:'original',draft:{speaker_id:'speaker',configuration:state}};
  const api=async(path,request={})=>{
    if(path.includes('options'))return options;
    if(path.endsWith('batches/preview'))return {preview:{can_confirm:true,batch_id:'old',actual_target:1,source_configuration_sha256:'a'.repeat(64)}};
    if(path.endsWith('batches/confirm')){entered.resolve();return pending.promise;}
    return saved;
  };
  try {
    const views=view(dom,api,path=>navigations.push(path));await views.renderConfiguration();
    dom.element('batch-config-form').handlers.submit({preventDefault(){}});
    await new Promise(resolve=>setImmediate(resolve));
    const old=dom.element('config-confirm').handlers.click();await entered.promise;
    await views.renderConfiguration();const markup=dom.app.markup,writes=dom.writes;
    pending.resolve({result:{batch_id:'old'}});await old;
    assert.deepEqual(navigations,[]);assert.equal(dom.app.markup,markup);assert.equal(dom.writes,writes);
  } finally {dom.restore();}
});

test('a blocked original confirmation keeps an explicit new-draft route without adopting old authority',async()=>{
  const dom=browser(),writes=[];
  const state=changeConfiguration(createConfiguration('free'),'persona',1);
  const saved={revision:1,operation_id:'old',confirmation_blocked:{code:'CREATION_BATCH_ACTOR_CONFLICT'},
    draft:{speaker_id:'speaker',configuration:state}};
  const api=async(path,request={})=>{
    if(path.includes('options'))return options;
    if(request.method==='PUT'){writes.push(JSON.parse(request.body));return {revision:2,operation_id:'new'};}
    return saved;
  };
  try {
    await view(dom,api).renderConfiguration();
    assert.match(dom.app.markup,/此前确认需要重新核对权限/);
    assert.doesNotMatch(dom.app.markup,/查看原批进度与成果/);
    dom.element('config-new-batch').handlers.click();
    await dom.element('config-save').handlers.click();
    assert.equal(writes[0].payload.configuration.revision,state.revision+1);
    assert.doesNotMatch(dom.app.markup,/此前确认需要重新核对权限/);
  } finally {dom.restore();}
});

test("editing quantity clears the old delivery estimate and updates the explicit source count without losing focus", async () => {
  const dom=browser();
  const state=changeConfiguration(changeConfiguration(createConfiguration("free"),"repurposeEnabled",true),"repurpose",1);
  try {
    await view(dom,async path=>path.includes("options") ? options : {revision:1,operation_id:"saved",
      draft:{speaker_id:"speaker",configuration:state}}).renderConfiguration();
    const writes=dom.writes;
    dom.element("delivery").firstChild.textContent="最多 1 条";
    dom.element("config-repurpose").value="2";
    dom.element("config-repurpose").handlers.input();
    assert.equal(dom.element("delivery").firstChild.textContent,"待核对");
    assert.match(dom.element("config-repurpose-selection").innerHTML,/已选择 0 条内容，本次需要 2 条/);
    assert.equal(dom.writes,writes);
  } finally {dom.restore();}
});
test("older options, draft and mutation callbacks cannot replace a reopened view at the same URL", async () => {
  for (const boundary of ["options", "draft", "mutation"]) {
    const dom = browser(), pending = deferred(), entered = deferred(); let first = true;
    const state = changeConfiguration(createConfiguration("free"), "persona", 1);
    const saved = { revision: 1, operation_id: "server_key", draft: { speaker_id: "speaker", configuration: state } };
    const api = async (path, request = {}) => {
      const kind = request.method === "PUT" ? "mutation" : path.includes("options") ? "options" : "draft";
      if (kind === boundary && first) { first = false; entered.resolve(); return pending.promise; }
      return kind === "options" ? options : saved;
    };
    try {
      const views = view(dom, api);
      let old;
      if (boundary === "mutation") { await views.renderConfiguration(); old = dom.element("config-save").handlers.click(); }
      else old = views.renderConfiguration();
      await entered.promise;
      // New invocation for the same URL supersedes an older pending invocation.
      await views.renderConfiguration();
      const writes = dom.writes, markup = dom.app.markup;
      pending.resolve(boundary === "options" ? options : saved); await old;
      assert.equal(dom.writes, writes, boundary); assert.equal(dom.app.markup, markup, boundary);
    } finally { dom.restore(); }
  }
});

const newsPreview=(extra={})=>({preview:{schema_version:'news-delivery-preview-v1.0',business_id:'fictional',speaker_id:'speaker',
  target_profile:'news',reuse_intent:'cross_profile_repurpose',eligible_sources:[{source_content_id:'source-a',source_title:'已审核原内容',source_status:'exported'}],...extra}});

test('typed adaptation quantity is the saved Native intent; zero removes the old selected identity',async()=>{
  const dom=browser(),saved=[];
  try{
    await view(dom,async(path,request={})=>{
      if(path.includes('options'))return options;
      if(request.method==='PUT'){saved.push(JSON.parse(request.body).payload);return{revision:saved.length,operation_id:'saved'};}
      return{revision:0,draft:null};
    }).renderConfiguration();
    dom.element('config-repurpose').value='2';dom.element('config-repurpose').handlers.input();
    await dom.element('config-save').handlers.click();
    assert.equal(saved[0].configuration.quantities.repurpose,2);assert.equal(saved[0].configuration.repurposeEnabled,true);
    assert.match(dom.app.markup,/选择已有内容/);assert.doesNotMatch(dom.app.markup,/id="config-repurposeEnabled"/);
    dom.element('config-repurpose').value='0';dom.element('config-repurpose').handlers.input();
    await dom.element('config-save').handlers.click();
    assert.equal(saved[1].configuration.quantities.repurpose,0);assert.equal(saved[1].configuration.repurposeEnabled,false);
    assert.deepEqual(saved[1].configuration.repurposeSourceIds,[]);
  }finally{dom.restore();}
});

test('ambiguous old intent is displayed and saved without guessing, then explicitly reconfirmed',async()=>{
  const dom=browser(),saved=[];
  const state={...changeConfiguration(createConfiguration('free'),'repurpose',1),repurposeEnabled:false,repurposeSourceIds:['source-a']};
  try{
    await view(dom,async(path,request={})=>{
      if(path.includes('options'))return options;
      if(path.endsWith('news/preview'))return newsPreview();
      if(request.method==='PUT'){saved.push(JSON.parse(request.body).payload);return{revision:saved.length+1,operation_id:'new'};}
      return{revision:1,operation_id:'old',draft:{speaker_id:'speaker',configuration:state}};
    }).renderConfiguration();
    assert.match(dom.app.markup,/旧草稿的改编数量/);
    await dom.element('config-save').handlers.click();assert.equal(saved[0].configuration.repurposeEnabled,false);
    dom.element('config-reconfirm-news').handlers.click();
    await dom.element('config-save').handlers.click();assert.equal(saved[1].configuration.repurposeEnabled,true);
    assert.deepEqual(saved[1].configuration.repurposeSourceIds,['source-a']);
  }finally{dom.restore();}
});

test('source reads reject a foreign customer or unknown Reader version before displaying private titles',async()=>{
  for(const extra of [{business_id:'foreign'}, {schema_version:'news-delivery-preview-v99'}]){
    const dom=browser(),state=changeConfiguration(createConfiguration('free'),'repurpose',1);
    try{
      await view(dom,async path=>path.includes('options')?options:path.endsWith('news/preview')?newsPreview(extra):
        {revision:1,operation_id:'old',draft:{speaker_id:'speaker',configuration:state}}).renderConfiguration();
      assert.doesNotMatch(dom.app.markup,/已审核原内容/);
      assert.match(dom.app.markup,/历史来源无法对应/);
    }finally{dom.restore();}
  }
});

test('rereading history invalidates the checked preview and replaces its old success message',async()=>{
  const dom=browser();const state={...changeConfiguration(createConfiguration('free'),'repurpose',1),repurposeSourceIds:['source-a']};
  try{
    await view(dom,async(path,request={})=>{
      if(path.includes('options'))return options;
      if(path.endsWith('news/preview'))return newsPreview();
      if(path.endsWith('batches/preview'))return{preview:{can_confirm:true,batch_id:'same',actual_target:1,new_content_target:0,source_configuration_sha256:'a'.repeat(64)}};
      return{revision:1,operation_id:'same',draft:{speaker_id:'speaker',configuration:state}};
    }).renderConfiguration();
    dom.element('batch-config-form').handlers.submit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
    assert.equal(dom.element('config-confirm').hidden,false);
    await dom.element('config-load-repurpose').handlers.click();
    assert.equal(dom.element('config-confirm').hidden,true);
    assert.match(dom.element('batch-config-status').textContent,/重新核对创作资格/);
    assert.doesNotMatch(dom.element('batch-config-status').textContent,/当前资料允许/);
  }finally{dom.restore();}
});

test('capacity failure is a focused visible alert with exact Native counts, safe recovery and no confirmation',async()=>{
  const dom=browser(),calls=[],saves=[],checked=deferred();
  const state=createConfiguration();
  const error=Object.assign(new Error('当前仅有 1 个符合条件的新主题，本次填写 10 条，请调整数量。'),
    {detail:{code:'CREATION_BATCH_SOURCE_CAPACITY',next_action:'不会减少目标或自动改用已有内容；调整后请重新核对创作资格。'}});
  const api=async(path,request={})=>{
    calls.push(path);
    if(path.includes('options'))return options;
    if(request.method==='PUT'){saves.push(JSON.parse(request.body).payload.configuration);return{revision:saves.length+1,operation_id:'same'};}
    if(path.endsWith('batches/preview')){checked.resolve();throw error;}
    return{revision:1,operation_id:'same',draft:{speaker_id:'speaker',configuration:state}};
  };
  try{
    await view(dom,api).renderConfiguration();
    dom.element('batch-config-form').handlers.submit({preventDefault(){}});await checked.promise;
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(dom.element('config-feedback').hidden,false);
    assert.match(dom.app.markup,/role="alert" aria-atomic="true"/);
    assert.match(dom.element('config-feedback').innerHTML,/创作资格未通过，暂不能开始/);
    assert.match(dom.element('config-feedback').innerHTML,/仅有 1 个符合条件的新主题，本次填写 10 条/);
    assert.match(dom.element('config-feedback').innerHTML,/不会减少目标或自动改用已有内容/);
    assert.equal(dom.element('batch-config-status').hidden,true);
    assert.equal(dom.focused,'config-feedback');
    assert.equal(dom.element('config-check').textContent,'重新核对创作资格');
    assert.equal(dom.element('config-confirm').hidden,true);
    dom.element('config-adjust-quantities').handlers.click();assert.equal(dom.focused,'config-quantities-heading');
    assert.deepEqual(saves,[state]); // The alert and its action never silently reduce the target.
    assert.equal(calls.filter(path=>path.endsWith('batches/confirm')).length,0);
    dom.element('config-novel').value='1';dom.element('config-novel').handlers.input();
    assert.equal(dom.element('config-feedback').hidden,true);
    assert.equal(dom.element('batch-config-status').hidden,false);
    assert.equal(dom.element('config-confirm').hidden,true);
    assert.match(dom.element('batch-config-status').textContent,/重新核对/);
    assert.equal(saves.length,1); // Editing does not save or launch automatically.
  }finally{dom.restore();}
});

test('error card escapes supplied text; other failed operations do not claim a capacity failure',()=>{
  const html=configurationFailureMarkup({checking:false,message:'保存失败 <img src=x onerror=alert(1)>',nextAction:'重新检查 & 保留草稿'});
  assert.match(html,/本次操作未完成/);assert.match(html,/&lt;img/);assert.match(html,/&amp;/);
  assert.doesNotMatch(html,/<img|config-adjust-quantities|创作资格未通过/);
});

test('missing production qualification explains administrator action without a false count adjustment',()=>{
  for (const code of ['CREATIVE_STYLE_QUALIFICATION_REQUIRED','CREATION_BATCH_ISOLATED_SCOPE_REQUIRED',
    'CREATION_PRODUCTION_ADMISSION_REQUIRED','CREATION_PRODUCTION_EXECUTION_NOT_AUTHORIZED']) {
    const html=configurationFailureMarkup({checking:true,code,
      message:'当前环境尚未激活可用于本次创作的正式版本。',nextAction:'请联系管理员；当前配置已保留。'});
    assert.match(html,/创作暂未开放/);assert.match(html,/管理员/);
    assert.doesNotMatch(html,/config-adjust-quantities|调整创作数量/);
  }
});

test('a lost confirmation response keeps the original checked identity for safe replay',async()=>{
  const dom=browser(),confirmations=[],navigations=[];
  const state=changeConfiguration(createConfiguration('free'),'persona',1);
  const api=async(path,request={})=>{
    if(path.includes('options'))return options;
    if(path.endsWith('batches/preview'))return{preview:{can_confirm:true,batch_id:'original',actual_target:1,
      new_content_target:1,source_configuration_sha256:'a'.repeat(64)}};
    if(path.endsWith('batches/confirm')){
      confirmations.push(JSON.parse(request.body));
      if(confirmations.length===1)throw Error('结果尚未确认，请保留当前配置后重试。');
      return{result:{batch_id:'original'}};
    }
    return{revision:1,operation_id:'same',draft:{speaker_id:'speaker',configuration:state}};
  };
  try{
    await view(dom,api,path=>navigations.push(path)).renderConfiguration();
    dom.element('batch-config-form').handlers.submit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));
    await dom.element('config-confirm').handlers.click();
    assert.match(dom.element('config-feedback').innerHTML,/本次操作未完成/);
    assert.doesNotMatch(dom.element('config-feedback').innerHTML,/创作资格未通过/);
    assert.equal(dom.element('config-confirm').hidden,false);
    await dom.element('config-confirm').handlers.click();
    assert.deepEqual(confirmations[0],confirmations[1]);
    assert.deepEqual(navigations,['/create/batch?batch_id=original']);
  }finally{dom.restore();}
});
