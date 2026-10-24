import test from 'node:test';
import assert from 'node:assert/strict';
import { previewMarkup, privateCaseMarkup, privateNotesMarkup } from '../../static/assets/case-excel-preview-view.mjs';
import { importSelectionMarkup, updateVideoSelection } from '../../static/assets/case-excel-import-view.mjs';

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

test('owned original notes escape all fields and retain their unverified evidence boundary',()=>{
 const html=privateNotesMarkup({raw_case:{source_platform:'抖音',source_url:'<script>source</script>',
   narration_excerpt:'<img src=x onerror=boom>',structure_summary:'未核人工摘要',observation_basis:'仅阅读文案'},
   raw_segments:[{segment_order:1,narrative_role_hint:'<script>role</script>',narration_excerpt:'<b>segment</b>'}],
   raw_rights:{rights_status:'granted'}});
 assert.match(html,/查看投稿原文（未经核验）/);
 assert.match(html,/不能代替真实媒体证据/);
 assert.match(html,/不授予共享或素材复用权/);
 assert.match(html,/&lt;script&gt;source/);
 assert.match(html,/&lt;b&gt;segment/);
 assert.doesNotMatch(html,/<script>|<img|<b>|granted|rights_status/);
});

test('source supplement exposes supported video controls without inventing text/local-only bindings',()=>{
 const p={rows:[{row:5,external_case_key:'A',canonical_source_key:'douyin:fixture',status:'unverified_preview',raw:{source_title:'有链接',source_url:'https://www.douyin.com/video/7999999999999999999'}},
  {row:6,external_case_key:'B',canonical_source_key:null,status:'unverified_preview',raw:{source_title:'仅文字'}}],issues:[]};
 const html=importSelectionMarkup(p,{expandMedia:true});
 assert.equal((html.match(/class="excel-media-details" open/g)||[]).length,1);
 assert.equal((html.match(/data-import-video=/g)||[]).length,1);
 assert.match(html,/data-import-rights="5"/);assert.match(html,/我有权上传此视频/);
 assert.match(html,/data-import-pick="5"/);assert.match(html,/先选文件，再确认来源/);
 assert.match(html,/data-import-rights="5"[^>]*disabled/);
 assert.match(html,/仅填写文件名或文字说明并未上传视频/);
 assert.doesNotMatch(html,/data-import-video="6"/);
});

test('video steps explain missing file, missing confirmation and ready-to-save without minting uploaded state',()=>{
 const file={dataset:{importVideo:'5'},files:[]},rights={checked:true},picker={},name={},clear={},status={dataset:{}};
 const nodes={'data-import-rights':rights,'data-import-pick':picker,'data-import-video-name':name,'data-import-clear':clear,'data-import-video-status':status};
 const root={querySelectorAll:()=>[file],querySelector:selector=>nodes[Object.keys(nodes).find(key=>selector.includes(key))]};
 let summary=updateVideoSelection(root,[5]);
 assert.equal(summary.picked.length,0);assert.equal(rights.checked,false);assert.equal(rights.disabled,true);
 assert.match(status.textContent,/还缺视频文件/);assert.equal(picker.disabled,false);
 file.files=[{name:'<img src=x>.mp4'}];summary=updateVideoSelection(root,[5]);
 assert.equal(rights.disabled,false);assert.equal(summary.unconfirmed.length,1);assert.match(status.textContent,/还需勾选/);
 assert.equal(name.textContent,'<img src=x>.mp4');assert.equal(rights.checked,false);
 rights.checked=true;summary=updateVideoSelection(root,[5]);
 assert.equal(summary.unconfirmed.length,0);assert.match(status.textContent,/尚未开始解析/);
 assert.doesNotMatch(status.textContent,/已经上传|审核通过/);
 summary=updateVideoSelection(root,[]);assert.equal(summary.picked.length,0);assert.equal(picker.disabled,true);assert.equal(rights.disabled,true);
 assert.match(status.textContent,/本次不会上传或保存/);
});

test('supplement summary preserves the already-saved context',()=>{
 const result={schema_version:'case-excel-preview-v0.3',authority:{can_persist:false,can_dispatch:false,can_approve:false,can_share:false},rows:[{row:5,status:'unverified_preview'}],issues:[]};
 const html=previewMarkup(result,{supplement:true});assert.match(html,/已保存的投稿会保留/);assert.doesNotMatch(html,/尚未保存任何案例/);
});
