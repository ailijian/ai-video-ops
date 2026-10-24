import assert from "node:assert/strict";
import {caseListCard,formatCaseDuration,caseStateLabels} from "../../static/assets/list-ui.mjs";
import {customerCard} from "../../static/assets/customer-components.js";

for(const value of [null,undefined,0,-1,NaN,Infinity,"45",false]) assert.equal(formatCaseDuration(value),"");
assert.equal(formatCaseDuration(45),"00:45");assert.equal(formatCaseDuration(72),"01:12");
assert.equal(formatCaseDuration(.4),"少于 1 秒");
const item={case_id:"7999999999999999901",visibility:"shared",status:"approved",title:'<img src=x onerror="boom">',industry:"餐饮",duration_seconds:null,video_type:null};
let html=caseListCard(item,null,"/cases?view=shared&search=餐饮");
assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img src=x|<video|iframe|已收录|00:00|素材混剪|新闻体/);
assert.match(html,/视频类型暂未标注|暂无封面/);assert.match(html,/return=%2Fcases/);
assert.notEqual(caseStateLabels.failed,caseStateLabels.rejected);
html=caseListCard({...item,visibility:"mine",status:"failed",failure_reason:"解析失败"});
assert.match(html,/解析失败/);
html=customerCard({business_id:"fictional",display_name:"很长的虚构客户名称",detail_url:"/customers/fictional",industry:"餐饮",
  approved_speaker_count:0,creation_record_count:0,pending_count:0,operation:{kind:"ready",status:"可创作",primary:{url:"/create?business_id=fictional",label:"开始创作"}}});
assert.doesNotMatch(html,/customer-operation-metrics|<dd>|>0</);
assert.match(html,/暂无创作记录/);assert.match(html,/\/create\/config\?business_id=fictional/);
console.log("BRAND_LIST_RENDERING_CONTRACT_PASS");

const imported={source_kind:'excel_import',visibility:'mine',status:'import_source_pending',
 title:'<script>private title</script>',video_type:null,video_type_hint:'<img>故事型',
 href:'/cases/excel-imports/import_owned?operation=op_saved&view=cases&row=row_1',next_action:'查看导入详情与下一步'};
html=caseListCard(imported);
assert.match(html,/Excel 导入 · 私有未核/);assert.match(html,/来源待核对/);
assert.match(html,/投稿建议：&lt;img&gt;故事型/);assert.match(html,/视频类型暂未标注/);
assert.doesNotMatch(html,/<script>|<img>|已收录|待审核|已共享/);
assert.match(html,/operation=op_saved&amp;view=cases&amp;row=row_1/);
