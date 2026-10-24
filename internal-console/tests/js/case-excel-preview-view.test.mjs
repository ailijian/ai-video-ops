import test from 'node:test';
import assert from 'node:assert/strict';
import { previewMarkup, privateCaseMarkup } from '../../static/assets/case-excel-preview-view.mjs';
import { importSelectionMarkup } from '../../static/assets/case-excel-import-view.mjs';

test('summary and selectable rows retain unverified boundaries without duplicate cases or technical codes',()=>{
 const result={schema_version:'case-excel-preview-v0.3',file_sha256:'a'.repeat(64),excluded_sheets:[1,2,3,4,5],authority:{can_persist:false,can_dispatch:false,can_approve:false,can_share:false},
  rows:[{row:5,external_case_key:'<img src=x>',raw:{source_title:'<script>bad()</script>',video_content_type_hint:'故事型'},status:'invalid'}],
  issues:[{severity:'error',sheet:'案例清单',row:5,field:'other_type_note',code:'OTHER_NOTE_REQUIRED'}]};
 const html=previewMarkup(result)+importSelectionMarkup(result);
 assert(html.includes('&lt;script&gt;') && !html.includes('<script>'));
 assert(html.includes('尚未审核') && html.includes('未保存任何案例或任务') && html.includes('其它类型时请填写说明'));
 assert(!html.includes('other_type_note') && !html.includes('OTHER_NOTE_REQUIRED'));
 assert.equal((html.match(/&lt;script&gt;bad\(\)&lt;\/script&gt;/g)||[]).length,1,'each case appears only once');
 assert.throws(()=>previewMarkup({...result,authority:{...result.authority,can_persist:true}}));
});

test('result cases distinguish saved, cancelled, invalid and unconfirmed rows without inventing approval',()=>{
 const row={raw_case:{source_title:'<script>private</script>',video_content_type_hint:'故事型'}};
 const saved=privateCaseMarkup({row,result:{state:'pending_source',candidate_ref_sha256:'a'.repeat(64)}});
 assert(saved.includes('&lt;script&gt;private&lt;/script&gt;') && !saved.includes('<script>'));
 assert(saved.includes('待核验') && saved.includes('来源待核对') && saved.includes('正式类型尚未审核'));
 const cancelled=privateCaseMarkup({sourceRow:6,result:{state:'cancelled',candidate_ref_sha256:null}});
 assert(cancelled.includes('未保存 · 已结束') && !cancelled.includes('保存结果尚未确认') && !cancelled.includes('已保留投稿说明'));
 assert.match(privateCaseMarkup({sourceRow:7,result:{state:'invalid'}}),/未保存 · 需修改/);
 assert.match(privateCaseMarkup({row,sourceRow:5}),/保存待确认/);
 assert(!privateCaseMarkup({row,sourceRow:5}).includes('已保留投稿说明'));
});

test('empty template and row counts do not confuse issues with case quantities',()=>{
 const base={schema_version:'case-excel-preview-v0.3',authority:{can_persist:false,can_dispatch:false,can_approve:false,can_share:false},rows:[],issues:[]};
 assert.match(previewMarkup(base),/从“案例清单”第 5 行开始填写/);
 const issue={severity:'error',sheet:'案例清单',row:6,field:'other_type_note',code:'OTHER_NOTE_REQUIRED'};
 const html=previewMarkup({...base,rows:[{row:5,status:'unverified_preview',issues:[]},{row:6,status:'invalid',issues:[issue]}],issues:[issue,{...issue,code:'DUPLICATE_SOURCE_IN_WORKBOOK'}]});
 assert.match(html,/<dt>读取案例<\/dt><dd>2/);
 assert.match(html,/<dt>可选保存<\/dt><dd>1/);
 assert.match(html,/<dt>需修改<\/dt><dd>1/);
 const orphan=previewMarkup({...base,issues:[{...issue,sheet:'<script>bad()</script>',code:'ORPHAN_CASE_KEY'}]});
 assert(orphan.includes('&lt;script&gt;') && !orphan.includes('<script>'));
});
