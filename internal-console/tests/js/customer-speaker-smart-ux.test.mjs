import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createCustomerViews, intakeSteps, customerReviewGroups, customerConstraintReview, bindCustomerConstraintControls, bindCustomerReviewControls, customerSubmissionSummary, CUSTOMER_INDUSTRIES } from "../../static/assets/customer-views.js";
import { customerProgressPanel } from "../../static/assets/customer-components.js";
import { speakerProgressPanel, speakerStatusPill } from "../../static/assets/speaker-components.js";
const root = new URL("../../static/", import.meta.url);
let html = "";
const handlers = new Map();
const element = {value:"", classList:{remove(){},add(){}}, addEventListener(name, handler){handlers.set(name, handler);}};
globalThis.document = {querySelector(){return element;}, querySelectorAll(){return [];}};

const views = createCustomerViews({app:{set innerHTML(value){html=value;}}, api:()=>{throw Error("empty analysis sent");}, navigate(){}, shell:(_,content)=>content, bindCommonActions(){}, pageHeading:(_,title,description)=>`<h1>${title}</h1><p>${description}</p>`, showToast(){}});
views.renderCustomerNew();
assert.match(html,/开始整理资料/);
assert.match(html,/先保存，稍后补充/);
assert.doesNotMatch(html,/customer-industry/);
await handlers.get("submit")({preventDefault(){}});
assert.equal(element.textContent,"请填写客户名称。");
assert.match(intakeSteps(2),/aria-current="step"/);
const grouped = customerReviewGroups([{candidate_id:"one", field:"service_process", value:["真实步骤"],source_excerpt:"真实来源"}]);
assert.match(grouped,/真实业务信息/);
assert.match(grouped,/查看依据/);
assert.equal((grouped.match(/data-review-row=/g)||[]).length,1);
for(const panel of [customerProgressPanel,speakerProgressPanel]) assert.doesNotMatch(panel({status:"running", progress:68,stage:"整理事实"}),/68%|width:68/);
assert.match(speakerStatusPill("revalidation_required"),/需复核关联/);
const caseDictionary = readFileSync(new URL("assets/case-industry.mjs",root),"utf8");
for(const industry of CUSTOMER_INDUSTRIES) assert.ok(caseDictionary.includes(industry));
const css = readFileSync(new URL("assets/styles.css",root),"utf8");
assert.match(css,/profile-review-page .sticky-action.*bottom:calc\(72px \+ env\(safe-area-inset-bottom\)\)/s);
console.log("CUSTOMER_SPEAKER_SMART_UX_PASS");

// Exercise the actual task poller and Customer renderer. Completion navigates
// into Human review with GETs only, including a task recovered by page refresh.
for (const terminal of ["awaiting_review", "completed", "failed"]) {
  const doc = new EventTarget();
  doc.visibilityState = "visible";
  const win = new EventTarget();
  const timers = new Map();
  let timer = 0, detailReads = 0;
  win.setTimeout = callback => {timers.set(++timer, callback); return timer;};
  win.clearTimeout = id => timers.delete(id);
  const progress = {innerHTML:""};
  const control = {addEventListener(){}, disabled:false};
  doc.querySelectorAll = () => [];
  doc.querySelector = selector => selector === "[data-customer-progress]"
    ? (html.includes("data-customer-progress") ? progress : null)
    : ["#submit-fact-review", "[data-review-progress]", "#retry-customer-analysis"].includes(selector) ? control : null;
  globalThis.document = doc;
  globalThis.window = win;
  const requests = [];
  const detail = {business_id:"test-customer",display_name:"测试客户",industry:"其他",fact_candidates:[],speaker_candidates:[],speaker_discovery_status:"completed",task:{task_id:"task-one",status:terminal}};
  const screen = createCustomerViews({
    app:{set innerHTML(value){html=value;}}, shell:(_, content)=>content,
    api:async (url, options) => {
      requests.push({url,options});
      if (url === "/api/tasks/task-one") return {task:{task_id:"task-one",status:terminal}};
      assert.equal(url,"/api/customers/test-customer");
      return {...detail, status:detailReads++ === 0 ? "analyzing" : terminal === "failed" ? "failed" : "fact_review_required"};
    },
    navigate(){throw Error("No synthetic approval navigation");}, bindCommonActions(){},
    pageHeading:(_, title)=>`<h1>${title}</h1>`, skeletonPage(){html="";},
    showToast(){},renderLoadError(_, error){throw error;},
  });
  await screen.renderCustomerDetail("test-customer");
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(detailReads,2);
  assert.equal(timers.size,0);
  assert.ok(requests.every(request=>request.options === undefined));
  assert.doesNotMatch(html,/客户信息已经整理好，可以开始确认/);
  if (terminal !== "failed") {
    assert.match(html,/<h1>检查 AI 整理的客户资料<\/h1>/);
    assert.match(html,/aria-current="step"><span>3<\/span>/);
    assert.match(html,/重新查找出镜人/);
    assert.match(html,/确认并保存已核对的信息/);
    assert.match(control.textContent,/将采用 0 项/);
  } else {
    assert.match(html,/分析没有完成/);
  }
}
console.log("CUSTOMER_AUTO_REVIEW_READ_ONLY_TRANSITION_PASS");

// Founder requested UI preselection. A prior explicit Human deselection wins;
// neither rendering mode submits any request or changes canonical candidates.
for (const confirmation of [undefined, {selected:false}, {selected:true}]) {
  let requested = 0;
  const candidate = {candidate_id:"person-one",name:"测试人物",public_role:"负责人",
    candidate_status:"explicit_speaker",default_selected:false,confirmation,
    personal_material_quotes:[],evidence_quotes:["来源中的姓名与职责"]};
  const original = JSON.stringify(candidate);
  const screen = createCustomerViews({
    app:{set innerHTML(value){html=value;}}, shell:(_, content)=>content,
    api:async (url, options)=>{
      assert.equal(url,"/api/customers/test-customer");
      assert.equal(options,undefined); requested++;
      return {business_id:"test-customer",display_name:"测试客户",status:"fact_review_required",
        fact_candidates:[],industry:"其他",speaker_candidates:[candidate],speaker_discovery_status:"completed"};
    },
    navigate(){},bindCommonActions(){},pageHeading:(_, title)=>`<h1>${title}</h1>`,
    skeletonPage(){html="";},showToast(){},renderLoadError(_,error){throw error;},
  });
  await screen.renderCustomerDetail("test-customer");
  assert.equal(requested,1);
  assert.equal(JSON.stringify(candidate),original);
  assert.equal(/data-speaker-select checked/.test(html),confirmation?.selected !== false);
  assert.match(html,/确认后保存资料，之后仍需单独确认人物档案/);
}
console.log("SPEAKER_UI_PRESELECTION_PRESERVES_HUMAN_DESELECTION_PASS");

// Human type wins; an absent hint is never silently shown as generic.
for (const [hint, human, expected] of [[null,null,""],["generic",null,"generic"],["generic","owner_founder","owner_founder"]]) {
  const candidate = {candidate_id:"typed-person",name:"虚构人物",public_role:"虚构身份",
    candidate_status:"potential_representative",speaker_type_hint:hint,
    confirmation:human ? {selected:true,speaker_type:human} : null,evidence_quotes:["虚构身份原文"]};
  const screen = createCustomerViews({app:{set innerHTML(value){html=value;}},shell:(_,body)=>body,
    api:async()=>({business_id:"test-customer",display_name:"虚构客户",status:"fact_review_required",fact_candidates:[],speaker_candidates:[candidate]}),
    bindCommonActions(){},pageHeading:(_,title)=>title,skeletonPage(){},renderLoadError(_,error){throw error;}});
  await screen.renderCustomerDetail("test-customer");
  assert.match(html,new RegExp(`<option value="${expected}" selected>`));
  if (!expected) assert.doesNotMatch(html,/<option value="generic" selected>/);
}

// The final persisted result produces one feedback message, including partial
// Customer readiness and an independently saved Speaker Draft.
{
  const listeners = new Map(), toasts=[];
  globalThis.document={querySelector(selector){return selector==="#submit-fact-review" ? {addEventListener(n,f){listeners.set(n,f);}} : selector==="[data-review-progress]" ? {} : null;},querySelectorAll(){return [];}};
  const screen=createCustomerViews({app:{set innerHTML(value){html=value;}},shell:(_,body)=>body,
    api:async(url,options)=>options ? {review:{status:"completed_persona_blocked"},speaker_confirmation:{drafts:[{speaker_id:"one"}]}}
      : {business_id:"test-customer",display_name:"虚构客户",status:"fact_review_required",fact_candidates:[],speaker_candidates:[]},
    bindCommonActions(){},pageHeading:(_,title)=>title,skeletonPage(){},showToast(message){toasts.push(message);},renderLoadError(_,error){throw error;}});
  await screen.renderCustomerDetail("test-customer");
  await listeners.get("click")();
  assert.deepEqual(toasts,["客户已核对的信息和出镜人资料均已保存。本次事实审核已完成，仍有信息需要处理；客户档案尚未批准。"]);
}
console.log("E2_C_NULL_HUMAN_PRIORITY_AND_SINGLE_FEEDBACK_PASS");

{
  const screen=createCustomerViews({app:{set innerHTML(value){html=value;}},shell:(_,body)=>body,
    api:async()=>({business_id:"test-customer",display_name:"虚构客户",status:"fact_review_required",fact_candidates:[],
      constraint_candidates:[{constraint_id:"current",constraint_type:"identity_conflict",source:{evidence_quote:"核实当前主体"}}],
      constraint_resolution_targets:[1,2].map(n=>({constraint_id:"legacy-reused",source_intake_id:`intake_000${n}`,constraint_sha256:`sha${n}`,constraint_type:"identity_conflict",evidence_quote:"核实历史主体"}))}),
    bindCommonActions(){},pageHeading:(_,title)=>title,skeletonPage(){},renderLoadError(_,error){throw error;}});
  await screen.renderCustomerDetail("test-customer");
  assert.match(html,/<option value="legacy-reused\|intake_0001\|sha1">/);
  assert.match(html,/<option value="legacy-reused\|intake_0002\|sha2">/);
}
console.log("E2_EXACT_LEGACY_SOURCE_SELECTION_PASS");

// Presentation keeps every typed decision and exact source intact; rendering
// never confirms a restriction or promotes its related claim to a Known Fact.
{
  const candidates = ["publication_prohibition", "unverified_claim", "identity_conflict", "conditional_fact"]
    .map((constraint_type, index) => ({constraint_id:`restriction-${index}`,constraint_type,
      source:{evidence_quote:`虚构来源 ${index} <script>未经核实</script>`}}));
  const before = JSON.stringify(candidates);
  const markup = customerConstraintReview({constraint_candidates:candidates});
  for (const title of ["宣传禁用", "待核实宣传", "身份与主体冲突", "适用条件"]) assert.ok(markup.includes(title));
  assert.equal((markup.match(/data-constraint-action/g)||[]).length,4);
  assert.equal((markup.match(/data-constraint-evidence-panel hidden/g)||[]).length,4);
  assert.equal((markup.match(/value="exclude"/g)||[]).length,1);
  for (const action of ["confirm", "defer", "dismiss", "resolve"])
    assert.equal((markup.match(new RegExp(`value="${action}"`,"g"))||[]).length,4);
  assert.ok(markup.includes("&lt;script&gt;未经核实&lt;/script&gt;"));
  assert.doesNotMatch(markup,/<script>/);
  assert.equal(JSON.stringify(candidates),before);
  assert.equal(customerConstraintReview({constraint_candidates:[]}),"");
}

// Only correction/resolution needs extra evidence. Toggling that panel must
// retain an unsaved quote and note, and must not turn a choice into a saved review.
{
  const rows = Array.from({length:4}, () => {
    const change = new Map(), classes = new Set();
    const elements = {
      "[data-constraint-action]":{value:"",addEventListener(name,listener){change.set(name,listener);}},
      "[data-constraint-evidence-panel]":{hidden:false},
      "[data-constraint-status]":{textContent:""},
      "[data-constraint-evidence]":{value:"虚构且准确的原文"},
      "[data-constraint-note]":{value:"尚未提交的人工核对说明"},
    };
    return {querySelector(selector){return elements[selector];},
      classList:{toggle(name,on){if(on) classes.add(name); else classes.delete(name);}},
      elements,change,classes};
  });
  const progress = {textContent:""};
  bindCustomerConstraintControls({querySelectorAll(){return rows;},querySelector(){return progress;}});
  assert.ok(rows.every(row => row.elements["[data-constraint-evidence-panel]"].hidden));
  assert.match(progress.textContent,/0 \/ 4/);
  for (const value of ["confirm", "defer", "exclude", "dismiss", "resolve", ""]) {
    const row = rows[0];
    row.elements["[data-constraint-action]"].value=value;
    row.change.get("change")();
    assert.equal(row.elements["[data-constraint-evidence-panel]"].hidden,!["dismiss","resolve"].includes(value));
    assert.equal(row.elements["[data-constraint-status]"].textContent,value ? "待统一确认" : "本次暂不处理");
    assert.equal(row.classes.has("has-selection"),Boolean(value));
    assert.match(progress.textContent,value ? /1 \/ 4/ : /0 \/ 4/);
    assert.match(progress.textContent,/提交后保存核对结果/);
    assert.equal(row.elements["[data-constraint-evidence]"].value,"虚构且准确的原文");
    assert.equal(row.elements["[data-constraint-note]"].value,"尚未提交的人工核对说明");
  }
  rows.forEach(row => {row.elements["[data-constraint-action]"].value="confirm";});
  rows[3].change.get("change")();
  assert.match(progress.textContent,/4 \/ 4/);
  assert.ok(rows.every(row => row.elements["[data-constraint-status]"].textContent==="待统一确认"));
}
console.log("CUSTOMER_CONSTRAINT_REVIEW_POLISH_PASS");

// Default choices are page-local, exceptional rows are unselected, and only
// the unified action can persist decisions. Speaker controls stay independent.
{
  const source = [{candidate_id:"safe", field:"primary_products_or_services", value:["虚构堂食"],source_excerpt:"虚构堂食",default_review_selection:"approve"},
    {candidate_id:"risky",field:"years_in_business",value:"未核实数字",source_excerpt:"未核实数字",review_exception_reason:"数字待核实"}];
  const before = JSON.stringify(source);
  const markup = customerReviewGroups(source);
  assert.match(markup,/data-review-row="safe" data-decision="approve"/);
  assert.match(markup,/data-review-row="risky" data-decision=""/);
  assert.doesNotMatch(markup,/>确认<\/button>/);
  assert.match(markup,/暂不处理/);
  assert.equal(JSON.stringify(source),before);
  assert.deepEqual(customerSubmissionSummary(["approve","edit","edit","reject", "", ""],[
    {type:"unverified_claim",decision:"defer"},{type:"identity_conflict",decision:"defer"}]),
    {adopted:3,edited:2,rejected:1,pending:2,deferred:2,conflicts:1});
  const controls = customerConstraintReview({constraint_candidates:[{constraint_id:"award",constraint_type:"unverified_claim",source:{evidence_quote:"虚构奖项待核实"}}]});
  assert.match(controls,/value="defer" selected/);
  assert.doesNotMatch(controls,/value="exclude" selected/);
  assert.match(controls,/AI 的待提交建议/);
}
console.log("CUSTOMER_EXCEPTION_REVIEW_SELECTION_AND_SUMMARY_PASS");

// Changing an edited fact back to adoption must show the original value that
// will actually be submitted. This is a real control transition, not markup QA.
{
  const buttons = ["edit", "approve", "reject", ""].map(choice => ({dataset:{reviewChoice:choice},
    addEventListener(_, fn){this.click=fn;}}));
  const textarea = {value:"人工修改后的服务", focus(){},addEventListener(_, fn){this.input=fn;}};
  const elements = {"textarea":textarea,"[data-fact-value]":{},"[data-fact-status]":{},".review-edit-panel":{},
    '[data-review-choice="approve"]':buttons[1]};
  const row={dataset:{reviewRow:"source-one",decision:"approve"},classList:{toggle(){}},
    querySelector(s){return elements[s];},querySelectorAll(){return buttons;}};
  const summary={}, submit={};
  const root={querySelectorAll(s){return s==="[data-review-row]" ? [row] : [];},
    querySelector(s){return s==="[data-review-progress]" ? summary : s==="#submit-fact-review" ? submit : null;}};
  const original={candidate_id:"source-one",value:["原始服务"]};
  bindCustomerReviewControls({fact_candidates:[original],constraint_candidates:[]},root);
  buttons[0].click();
  assert.match(elements["[data-fact-value]"].innerHTML,/人工修改后的服务/);
  assert.match(summary.textContent,/已修改 1 项/);
  buttons[1].click();
  assert.match(elements["[data-fact-value]"].innerHTML,/原始服务/);
  assert.doesNotMatch(elements["[data-fact-value]"].innerHTML,/人工修改后的服务/);
  buttons[2].click();
  assert.equal(row.dataset.decision,"reject");
  assert.match(summary.textContent,/不采用 1 项/);
  assert.deepEqual(original.value,["原始服务"]);
}

// Saving an independently selected Speaker must remain possible without
// forging an empty Customer review or claiming its facts have been reviewed.
{
  const listeners=new Map(), calls=[], toasts=[];
  globalThis.CSS={escape:v=>v};
  const row={querySelector(s){return s==="[data-speaker-select]" ? {checked:true}
    : {value:s==="[data-speaker-type]" ? "owner_founder" : "虚构资料"};}};
  globalThis.document={querySelector(s){return s==="#submit-fact-review" ? {addEventListener(n,f){listeners.set(n,f);}}
    : s.startsWith("[data-speaker-candidate=") ? row : null;},querySelectorAll(){return [];}};
  const screen=createCustomerViews({app:{set innerHTML(v){html=v;}},shell:(_,v)=>v,
    api:async(url,options)=>{calls.push({url,options});return options ? {speaker_confirmation:{drafts:[{speaker_id:"draft-one"}]}}
      : {business_id:"test-customer",display_name:"虚构客户",status:"fact_review_required",fact_candidates:[],
        speaker_candidates:[{candidate_id:"person-one",name:"虚构人物",candidate_status:"explicit_speaker"}]};},
    bindCommonActions(){},pageHeading:(_,v)=>v,skeletonPage(){},showToast(v){toasts.push(v);},renderLoadError(_,e){throw e;}});
  await screen.renderCustomerDetail("test-customer");
  await listeners.get("click")();
  assert.equal(calls.filter(c=>c.options).length,1);
  assert.match(calls.find(c=>c.options).url,/speaker-discovery\/confirm$/);
  assert.deepEqual(toasts,["出镜人选择已保存。客户事实尚未提交审核，客户档案尚未批准。"]);
}
console.log("CUSTOMER_REVIEW_PREVIEW_AND_INDEPENDENT_DRAFT_COMPATIBILITY_PASS");

// Ten server-eligible page-local defaults are submitted in one explicit Human
// action. Opening the page does not call POST, and none grants Persona approval.
{
  const listeners=new Map(), posts=[];
  const candidates=Array.from({length:10},(_,n)=>({candidate_id:`ordinary-${n}`,field:"primary_products_or_services",
    value:[`虚构服务${n}`],source_excerpt:`虚构服务${n}`,state:"requires_review",default_review_selection:"approve"}));
  globalThis.document={querySelector(s){
    if(s==="#submit-fact-review") return {addEventListener(n,f){listeners.set(n,f);}};
    const candidate=candidates.find(v=>s===`[data-review-row="${v.candidate_id}"]`);
    return candidate ? {dataset:{decision:"approve"}} : null;
  },querySelectorAll(){return [];}};
  const screen=createCustomerViews({app:{set innerHTML(v){html=v;}},shell:(_,v)=>v,
    api:async(url,options)=>{if(options){posts.push(JSON.parse(options.body));return {review:{status:"completed_persona_review_required"}};}
      return {business_id:"test-customer",display_name:"虚构客户",status:"fact_review_required",fact_candidates:candidates,speaker_candidates:[],review_context:{token:"server-context"}};},
    bindCommonActions(){},pageHeading:(_,v)=>v,skeletonPage(){},showToast(){},renderLoadError(_,e){throw e;}});
  await screen.renderCustomerDetail("test-customer");
  assert.equal(posts.length,0);
  assert.equal((html.match(/data-decision="approve"/g)||[]).length,10);
  await listeners.get("click")();
  assert.equal(posts.length,1);
  assert.equal(posts[0].decisions.length,10);
  assert.ok(posts[0].decisions.every(v=>v.decision==="approve"));
  assert.equal(posts[0].review_context,"server-context");
}
console.log("TEN_DEFAULT_FACTS_ONE_EXPLICIT_HUMAN_SUBMISSION_PASS");

// Native SPA Back navigation must also protect unsaved review edits. Exercise
// the actual installed handler with a small router boundary, not client facts.
{
  const router=readFileSync(new URL("assets/app.js",root),"utf8");
  const start=router.indexOf('window.addEventListener("popstate", () => {');
  const end=router.indexOf('\nbootstrap();',start);
  assert.ok(start>0 && end>start);
  let listener, renders=0, restored=[];
  const win={__customerReviewDirty:true,confirm:()=>false,addEventListener(_,fn){listener=fn;}};
  Function("window","history","renderRoute","renderedRoutePath",router.slice(start,end))(
    win,{pushState(_,__,path){restored.push(path);}},()=>renders++,"/customers/fictional-review");
  listener();
  assert.equal(renders,0);assert.deepEqual(restored,["/customers/fictional-review"]);
  assert.equal(win.__customerReviewDirty,true);
  win.confirm=()=>true;listener();
  assert.equal(renders,1);assert.equal(win.__customerReviewDirty,false);
}
console.log("UNSAVED_REVIEW_BROWSER_BACK_PROTECTION_PASS");
