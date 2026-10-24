import assert from "node:assert/strict";
import {test} from "node:test";
import {taskListRows,taskSourceResults,taskActivityRows} from "../../static/assets/task-list-view.mjs";
const escapeHtml=x=>String(x??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll('"',"&quot;");
const options={escapeHtml,icons:{tasks:'<svg></svg>',cases:'<svg></svg>',customers:'<svg></svg>',arrow:'<svg></svg>'},humanTaskType:x=>({case_analysis:"案例分析",customer_analysis:"客户资料整理",speaker_analysis:"出镜人资料整理"}[x]||x)};
const task={task_id:"case-exact_attempt",task_type:"case_analysis",status:"awaiting_review",stage:"等待分类核对",updated_at:"2026-09-30T16:00:00Z",payload:{}};
test("execution status cannot imply Case or media approval",()=>{
  const html=taskListRows([task,{...task,task_id:"another-task",status:"completed"}],options);
  assert.match(html,/待人工处理/);assert.match(html,/执行完成/);
  assert.doesNotMatch(html,/已收录|已入库|pill-approved|一键批准|生产可用/);
  assert.equal((html.match(/<a /g)||[]).length,2);assert.doesNotMatch(html,/<button/);
});
test("exact Task routes and source-only names stay escaped",()=>{
  const html=taskListRows([{...task,task_id:'unsafe"/id',task_type:"customer_analysis",payload:{customer_name:'<img src=x onerror="bad">'}},{...task,payload:{case_title:"AI 建议不可当作正式标题"}}],options);
  assert.match(html,/href="\/tasks\/unsafe%22%2Fid"/);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img|AI 建议不可当作正式标题/);
});
test("new execution or approved Case preserves historical failure distinction",()=>{
  const html=taskListRows([{...task,status:"failed",current_active_task_id:"new-task"},{...task,status:"failed",current_case_status:"approved"}],options);
  assert.equal((html.match(/历史执行未完成/g)||[]).length,4);
  assert.doesNotMatch(html,/pill-failed|href="\/tasks\/new-task|retry|重新分析/);
});
test("unavailable source differs from real empty and keeps other source usable",()=>{
  const activity={events:[],accounts:[]};
  assert.deepEqual(taskSourceResults([{status:"rejected"},{status:"fulfilled",value:activity}]),{tasks:null,activity});
  assert.deepEqual(taskSourceResults([{status:"fulfilled",value:{tasks:[]}},{status:"rejected"}]),{tasks:[],activity:null});
  assert.equal(taskSourceResults([{status:"fulfilled",value:{}},{status:"rejected"}]).tasks,null);
});
test("Shanghai time and absent dates are accurate",()=>{
  assert.match(taskListRows([task],options),/2026\/10\/01 00:00/);
  assert.doesNotMatch(taskListRows([{...task,updated_at:"invalid"}],options),/<time|00:00/);
});
test("activity uses trusted event data and escapes private text",()=>{
  const html=taskActivityRows([{at:task.updated_at,kind:"客户审核",subject:"<客户>",actor:{phone_masked:"139****0001"},status:"approved"}],options);
  assert.match(html,/2026\/10\/01 00:00/);assert.match(html,/&lt;客户>/);assert.doesNotMatch(html,/<客户>/);
});
