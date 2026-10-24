import test from 'node:test';
import assert from 'node:assert/strict';
import { makeTypeConfirmation,typeConfirmationMarkup } from '../../static/assets/case-type-confirmation.mjs';
import { shareConfirmation } from '../../static/assets/case-share-confirmation.mjs';
import { escapeHtml } from '../../static/assets/list-ui.mjs';
const context={catalog:{ref:{path:'app/case_video_type_catalog.json',sha256:'a'.repeat(64)},value:{entries:[
 {type_id:'news',label:'新闻体',confirmable:true},{type_id:'persona',label:'人设型',confirmable:true},{type_id:'other',label:'其它',confirmable:true},
 {type_id:'future_type',label:'后续目录类型',confirmable:true},{type_id:'unknown',label:'待判断',confirmable:false}]}},source:{profile:'mix',suggested_type:'故事型'}};
test('explicit null does not promote the Excel suggestion',()=>{
 const value=makeTypeConfirmation(context);
 assert.equal(value.type_id,null);assert.equal(value.profile_conflict_resolution,'defer');assert.equal(value.explicitly_confirmed,true);
 assert.equal(value.catalog,context.catalog.ref);
});
test('corrected hint and independent profile require a Human reason',()=>{
 assert.throws(()=>makeTypeConfirmation(context,{typeId:'persona'}),/原因/);
 assert.equal(makeTypeConfirmation(context,{typeId:'persona',reason:'实际证据为人物观点'}).profile_conflict_resolution,'correct_suggestion_with_reason');
 assert.equal(makeTypeConfirmation({...context,source:{profile:'mix',suggested_type:null}},{typeId:'news',reason:'制作方式独立'}).profile_conflict_resolution,'preserve_dimensions_with_reason');
});
test('other note stays private and source catalog remains extensible',()=>{
 assert.throws(()=>makeTypeConfirmation(context,{typeId:'other',reason:'核对'}),/其它/);
 assert.equal(makeTypeConfirmation(context,{typeId:'other',otherNote:'仅审核说明',reason:'核对'}).other_note,'仅审核说明');
 assert.equal(makeTypeConfirmation({...context,source:{profile:'mix',suggested_type:null}},{typeId:'future_type'}).type_id,'future_type');
 assert.throws(()=>makeTypeConfirmation(context,{typeId:'forged'}),/目录/);
});
test('new review starts unclassified with accessible labels and escaped suggestions',()=>{
 const html=typeConfirmationMarkup({...context,source:{profile:'mix',suggested_type:'<img onerror=x>'}},escapeHtml);
 assert.match(html,/<option value="">暂不确定类型<\/option>/);assert.match(html,/label for="case-video-type"/);
 assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img|selected/);
});
test('the only final confirmation clearly includes explicit null and safe fields',()=>{
 const value=shareConfirmation({mode:'approve_and_share',preview_sha256:'a'.repeat(64),blocker_sha256:null,
  preview:{type_confirmation:{type_id:null},display:{title:'安全标题',industry:null,video_type:null,duration_seconds:6,structure_summary:'仅结构'}}});
 assert.match(value.description,/暂不确定类型/);assert.match(value.description,/安全标题/);assert.equal(value.confirmLabel,'确认收录并共享');
});
