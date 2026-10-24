import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { customerCard } from "../../static/assets/customer-components.js";
import { createCustomerViews } from "../../static/assets/customer-views.js";
import { createContentViews } from "../../static/assets/content-views.js";
import { CreationRecordsPanel, createContentOperationsViews } from "../../static/assets/content-operations-views.js";

const row = {business_id:"fictional_one",display_name:"虚构餐厅",industry:null,region:null,
  detail_url:"/customers/fictional_one",approved_speaker_count:0,creation_record_count:null,pending_count:2,
  operation:{status:"待核对",kind:"review",note:"待核对",primary:{url:"/customers/fictional_one",label:"去核对资料"}}};
let html = customerCard(row);
assert.match(html,/行业待确认/);
assert.match(html,/尚无已批准出镜人/);
assert.match(html,/创作记录暂不可读/);
assert.match(html,/2 项待处理/);
assert.doesNotMatch(html,/customer-operation-metrics|<dd>/);
assert.doesNotMatch(html,/主出镜人|上海|生日|经营年限/);
assert.match(customerCard({...row,display_name:'<img onerror="boom">'}),/&lt;img/);
assert.match(CreationRecordsPanel({total:0,records:[]}),/还没有创作记录/);
assert.match(CreationRecordsPanel({total:1,records:[{profile:"mix",label:"待审核",url:"/create?business_id=fictional_one&request_id=original_one"}]}),/request_id=original_one/);

const elements = new Map();
function element(key) {
  if (!elements.has(key)) elements.set(key,{value:"",events:{},addEventListener(name,fn){this.events[name]=fn;}});
  return elements.get(key);
}
globalThis.document = {querySelector:key=>element(key),querySelectorAll:()=>[]};
globalThis.window = {location:{search:"?search=餐饮&filter_by=pending&sort_by=updated&page=2"}};
const app = {innerHTML:""}, calls = [], navigation = [];
const views = createCustomerViews({app,api:async url=>{calls.push(url);return {customers:[row],total:21,page_size:20,filter_counts:{all:21,pending:2,ready:0}};},
  shell:(_,body)=>body,pageHeading:()=>"",skeletonPage:()=>{},bindCommonActions:()=>{},
  navigate:url=>navigation.push(url),renderLoadError:(_,error)=>{throw error;},showToast:()=>{}});
await views.renderCustomers();
assert.equal(calls.length,1); // no per-card HTTP requests
assert.match(calls[0],/\/api\/customers\/operations/);
assert.match(calls[0],/page=2/);
assert.match(app.innerHTML,/全部搜索匹配/);
element("#customer-search").value="虚构零售";
element("#customer-search-form").events.submit({preventDefault(){}});
let query = new URL("http://localhost"+navigation[0]).searchParams;
assert.equal(query.get("search"),"虚构零售");
assert.equal(query.get("page"),"1");
assert.equal(query.get("filter_by"),"pending");
element("#customer-sort").events.change({target:{value:"action"}});
assert.equal(new URL("http://localhost"+navigation[1]).searchParams.get("sort_by"),"action");

// A legacy unscoped route is now an explicit customer-selection path, with no auto task or fallback.
window.location.search="";
let reads=[];
const creation = createContentViews({app,api:async (url,options)=>{reads.push([url,options]);throw Error("unexpected API");},
  shell:(_,body)=>body,pageHeading:(_,title)=>`<h1>${title}</h1>`,skeletonPage:()=>{},bindCommonActions:()=>{},showToast:()=>{},renderLoadError:(_,error)=>{throw error;}});
await creation.renderCreate();
assert.match(app.innerHTML,/先选择一个客户/);
assert.match(app.innerHTML,/href="\/customers"/);
assert.equal(reads.length,0);
window.location.search="?business_id=missing_customer";
let errors=[];
const invalid = createContentViews({app,api:async url=>{reads.push([url]);throw Error("客户不存在");},
  shell:(_,body)=>body,pageHeading:()=>"",skeletonPage:()=>{},bindCommonActions:()=>{},showToast:()=>{},renderLoadError:(title,error)=>errors.push(error.message)});
await invalid.renderCreate();
assert.match(reads[0][0],/business_id=missing_customer/);
assert.deepEqual(errors,["客户不存在"]);

// A late task poll must not replace the customer/request page after navigation.
const appSource = await readFile(new URL("../../static/assets/app.js", import.meta.url), "utf8");
const taskDetail = appSource.slice(appSource.indexOf("let stopContentTaskPolling = null;"), appSource.indexOf("let renderedRoutePath"));
let pollCallbacks;
const taskApp = {innerHTML:""};
const context = vm.createContext({
  location:{pathname:"/tasks/original-task"}, app:taskApp,
  api:async()=>({task:{task_type:"content_generation",task_id:"original-task",status:"queued",payload:{request_id:"original-request"}}}),
  skeletonPage:()=>{}, shell:(_,body)=>body, pageHeading:()=>"", humanTaskType:()=>"创作任务",
  progressPanel:()=>"原任务进度", bindCommonActions:()=>{},
  startTaskPolling:options=>{pollCallbacks=options; return ()=>{};},
});
await vm.runInContext(taskDetail+"\nrenderTaskDetail('original-task');",context);
assert.match(taskApp.innerHTML,/original-request/);
context.location.pathname="/create";
taskApp.innerHTML="正确客户的原创作";
pollCallbacks.onUpdate({task_type:"content_generation",payload:{request_id:"original-request"}});
assert.equal(taskApp.innerHTML,"正确客户的原创作");
assert.match(appSource,/async function renderRoute\(\)\s*\{[\s\S]*?stopContentTaskPolling\?\.\(\);/);

// Back navigation while a slow history read is pending must keep the list.
let releaseRead;
const response = new Promise(resolve=>{releaseRead=resolve;});
window.location.href="http://localhost/customers/fictional_one/content";
const slowViews = createContentOperationsViews({app,api:()=>response,
  shell:(_,body)=>body,pageHeading:()=>"",skeletonPage:()=>{},bindCommonActions:()=>{},renderLoadError:()=>{throw Error('stale render');}});
const slowRead=slowViews.renderContentOperations("fictional_one");
window.location.href="http://localhost/customers?search=餐饮&filter_by=ready";
app.innerHTML="搜索结果";
releaseRead({records:[],total:0,page_size:20});
await slowRead;
assert.equal(app.innerHTML,"搜索结果");
console.log("CUSTOMER_OPERATIONS_NAVIGATION_PASS");
