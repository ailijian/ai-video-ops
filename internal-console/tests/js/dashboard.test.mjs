import assert from "node:assert/strict";
import { test } from "node:test";
import { dashboardMarkup, dashboardSkeleton, dashboardTime } from "../../static/assets/dashboard-view.mjs";
const escapeHtml = value => String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll('"',"&quot;");
const icons = Object.fromEntries(["arrow","inbox","home","customers","cases","tasks","alert"].map(k=>[k,`<svg data-icon="${k}"></svg>`]));
const metric = value => ({available:true,value,label:"准确指标",url:"/customers",note:"已验证来源"});
const data = {list:{section:"overview",items:[],total:0,page:1,page_size:20,complete:true},period:{today:"2026-10-15"},sources:{tasks:{available:true,label:"执行任务"}},metrics:{customers:metric(0),pending:metric(0),running:metric(0),materials:metric(0)},attention:[],recent:[],shortcuts:[{title:"管理客户",url:"/customers",description:"继续客户工作",icon:"customers"},{title:"案例库",url:"/cases",description:"共享案例与本人投稿",icon:"cases"}]};
test("real empty values, exact shortcuts and no invented completion or creation entry",()=>{
  const html=dashboardMarkup(data,{escapeHtml,icons});
  assert.match(html,/欢迎回来|目前没有需要处理/);assert.match(html,/data-metric="running">0/);
  assert.doesNotMatch(html,/本月完成|增长|href="\/create|通知|我的最近|需要你处理/);
  assert.equal((html.match(/class="dash-shortcut"/g)||[]).length,2);
  assert.doesNotMatch(html,/dash-welcome-mark|data-icon="home"/);
});
test("priority rows keep one reason and timestamp; trace IDs remain accessible",()=>{
  const value=structuredClone(data);
  value.attention=[{kind:"case_classification",name:"可信的视频原始标题",reason:"分类需要核对。",status:"needs_confirmation",
    updated_at:"2026-10-01T00:00:00Z",case_id:"7999999999999999999",task_id:"case-exact-attempt",
    action:{url:"/cases/7999999999999999999/classification",label:"核对分类"}}];
  value.metrics.materials.note="待处理事项中的资料核对";
  const html=dashboardMarkup(value,{escapeHtml,icons});
  assert.match(html,/待处理事项中的资料核对/);
  assert.match(html,/data-case-id="7999999999999999999"/);assert.match(html,/Task ID: case-exact-attempt/);
  assert.equal((html.match(/<time /g)||[]).length,1);
  assert.doesNotMatch(html,/待分类核对|<\/time> · 记录时间/);
});
test("source failure stays unknown and user text cannot become HTML",()=>{
  const partial=structuredClone(data);partial.partial=true;partial.sources.tasks.available=false;
  partial.metrics.running={...metric(null),available:false};partial.attention=[{kind:"task_recovery",name:'<img src=x onerror="boom">',reason:"失败原因",action:{url:"/tasks/exact-task",label:"处理失败任务"}}];
  const html=dashboardMarkup(partial,{escapeHtml,icons});
  assert.match(html,/data-metric="running">—/);assert.match(html,/部分信息暂时无法读取/);
  assert.match(html,/最近工作暂时无法完整读取/);assert.doesNotMatch(html,/还没有工作记录/);
  assert.match(html,/href="\/tasks\/exact-task"/);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img src=x/);
});
test("time uses business timezone; loading never flashes fake zero",()=>{
  assert.match(dashboardTime("2026-09-30T16:00:00Z"),/10\/01.*00:00/);
  assert.equal(dashboardTime("invalid"),"");assert.equal(dashboardTime(null),"");
  assert.match(dashboardSkeleton(),/aria-busy="true"/);assert.doesNotMatch(dashboardSkeleton(),/>0</);
});
