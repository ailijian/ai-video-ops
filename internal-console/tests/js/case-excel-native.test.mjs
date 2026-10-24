import test from 'node:test';
import assert from 'node:assert/strict';
import { nativePrepareInput,nativeSubmissionInput,nativeNotesMarkup } from '../../static/assets/case-excel-native.mjs';
import { safeExcelReturn,excelLoginPath } from '../../static/assets/routes.js';

test('Native preview binds one exact saved row and upload; hints never enter the DTO',()=>{
 const record={batch:{batch_id:'import_one'},head_sha256:'head',operations:[{intent_sha256:'intent',intent:{operation_id:'save_one',row_source_bindings:[{row_id:'row_5',row_sha256:'rowsha',native_upload_ref:{upload_id:'uploaded'}}]},result:{state:'saved'}}]};
 const item={ref:{row_id:'row_5',row_sha256:'rowsha'},row:{raw_case:{video_content_type_hint:'故事型'}}};
 const input=nativePrepareInput(record,item,'save_one');
 assert.equal(input.source_upload_id,'uploaded');assert.equal(input.expected_import_head_sha256,'head');assert.equal(input.action,'analyze_new');
 assert(!JSON.stringify(input).includes('故事型'));
 assert.throws(()=>nativePrepareInput(record,{...item,ref:{...item.ref,row_id:'row_other'}},'save_one'));
 assert.throws(()=>nativePrepareInput(record,item,'save_other'));
});

test('only a valid explicit Native confirmation produces a single-row submit DTO',()=>{
 const preview={schema_version:'case-excel-native-preview-v1.0-proposal',can_submit:true,case_approved:false,shared_published:false,
  source:{source_upload_id:'uploaded'},origin:{row_id:'row_5'},preflight_sha256:'original'};
 const input=nativeSubmissionInput(preview,'native_one');
 assert.equal(input.confirmed_submit_analysis,true);assert.equal(input.origin.row_id,'row_5');assert.equal(input.preflight_sha256,'original');
 assert.throws(()=>nativeSubmissionInput({...preview,can_submit:false},'native_one'));
 assert.throws(()=>nativeSubmissionInput({...preview,case_approved:true},'native_one'));
 assert.throws(()=>nativeSubmissionInput(preview,'../native_one'));
});

test('reload and login preserve the exact original analysis operation, never a new action',()=>{
 const path='/cases/excel-imports/import_'+'1'.repeat(32)+'?operation=save_one&view=cases&row=row_5&analysis_operation=native_one';
 assert.equal(safeExcelReturn(path),path);
 assert.equal(decodeURIComponent(excelLoginPath(path).split('return_to=')[1]),path);
 for(const invalid of [path.replace('native_one',''),path.replace('native_one','../other'),'/cases/excel-imports/import_one?analysis_operation=native_one'])assert.equal(safeExcelReturn(invalid),null);
});

test('reviewer notes stay unverified, escaped and outside formal review fields',()=>{
 const value={schema_version:'case-excel-bound-notes-projection-v1.0-proposal',trust:'unverified_submitter_candidate',evidence_promoted:false,case_approved:false,shared_published:false,
  notes:{case_notes:{video_content_type_hint:'故事型',narration_excerpt:'<script>claim()</script>'},segments:[],rights_claims:{media_reuse_claim:'投稿人声明'}}};
 const escape=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
 const html=nativeNotesMarkup(value,escape);
 assert(html.includes('未经核验') && html.includes('投稿类型建议') && html.includes('&lt;script&gt;'));
 assert(!html.includes('<script>') && !html.includes('<input') && !html.includes('<button'));
 assert.throws(()=>nativeNotesMarkup({...value,evidence_promoted:true},escape));
});
