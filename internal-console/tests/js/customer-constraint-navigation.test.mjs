import assert from "node:assert/strict";
import {createCustomerViews} from "../../static/assets/customer-views.js";
let html = "";
globalThis.document = {querySelectorAll(){return [];}, querySelector(){return null;}};
globalThis.location = {hash: "", pathname: "/customers/fictional-business"};
const detail = {
  business_id: "fictional-business", display_name: "虚构客户", status: "approved", industry: "餐饮",
  business_persona: {approved: true, facts: []}, current_business_persona: {approved: true},
  speakers: [{speaker_id:"fictional-speaker", display_name:"虚构出镜人", status:"approved"}],
  creation_entry_ready: false, production_constraint_blocked: true,
  creation_constraints: {blocked:true,items:[{constraint_id:"legacy-conflict",title:"两个主体关系待核实",reason:"请确认主体及数据口径 <script>",source_intake_id:"legacy-intake"}]},
};
const views = createCustomerViews({app:{set innerHTML(value){html=value;},querySelector(){return null;},querySelectorAll(){return [];}}, api:async()=>detail,
  navigate(){throw Error("Unexpected navigation");}, shell:(_,content)=>content,bindCommonActions(){},
  pageHeading:(_,title,description,actions="")=>`<h1>${title}</h1><p>${description}</p>${actions}`,
  skeletonPage(){},showToast(){},renderLoadError(_,e){throw e;}});
await views.renderCustomerDetail(detail.business_id);
assert.match(html,/1 位已确认/);
assert.match(html,/创作受限/);
assert.doesNotMatch(html,/需要至少一位已确认出镜人|>添加出镜人<|完成出镜人信息确认/);
location.hash="#constraints";
await views.renderCustomerDetail(detail.business_id);
assert.match(html,/两个主体关系待核实/);
assert.match(html,/请确认主体及数据口径 &lt;script&gt;/);
assert.match(html,/legacy-conflict/);
assert.match(html,/supplement\?gap=critical_constraints/);
assert.doesNotMatch(html,/<script>/);
detail.status = "fact_review_required";
detail.current_business_persona = null;
await views.renderCustomerDetail(detail.business_id);
assert.match(html,/两个主体关系待核实/);
assert.match(html,/返回资料核对/);
assert.doesNotMatch(html,/supplement\?gap=critical_constraints|客户档案与已确认出镜人继续保留/);
for (const status of ["analyzing", "failed"]) {
  detail.status = status;
  detail.task = {task_id: "fictional-task", status: "queued"};
  await views.renderCustomerDetail(detail.business_id);
  assert.match(html,/两个主体关系待核实/);
}
console.log("CUSTOMER_CONSTRAINT_NAVIGATION_PASS");
