const id=/^[a-z][a-z0-9_-]{1,127}$/;
export function nativePrepareInput(record,item,operationId){
 const op=record.operations.find(v=>v.intent.operation_id===operationId);
 const binding=op?.intent.row_source_bindings.find(v=>v.row_id===item.ref.row_id);
 if(!op?.result || !item.row || !binding || binding.row_sha256!==item.ref.row_sha256)throw Error('请先核对原保存记录。');
 return {schema_version:'case-excel-native-prepare-input-v1.0-proposal',batch_id:record.batch.batch_id,row_id:item.ref.row_id,
  import_operation_id:operationId,expected_row_sha256:item.ref.row_sha256,expected_import_intent_sha256:op.intent_sha256,
  expected_import_head_sha256:record.head_sha256,source_upload_id:binding.native_upload_ref?.upload_id || null,
  action:'analyze_new',reason:'',expected_prior_attempt:null};
}
export function nativeSubmissionInput(preview,operation){
 if(!id.test(operation) || preview?.schema_version!=='case-excel-native-preview-v1.0-proposal' || preview.can_submit!==true ||
    preview.case_approved!==false || preview.shared_published!==false || !preview.source || !preview.origin)throw Error('当前来源尚不能开始解析。');
 return {schema_version:'case-excel-native-submission-input-v1.0-proposal',submission_operation_id:operation,origin:preview.origin,
  expected_submission_parent_sha256:null,source_upload_id:preview.source.source_upload_id,confirmed_submit_analysis:true,
  preflight_sha256:preview.preflight_sha256,action:'analyze_new',reason:'',expected_prior_attempt:null};
}
export function nativeNotesMarkup(value,escape){
 if(value?.schema_version!=='case-excel-bound-notes-projection-v1.0-proposal' || value.trust!=='unverified_submitter_candidate' ||
    value.evidence_promoted!==false || value.case_approved!==false || value.shared_published!==false)throw Error('投稿说明版本无法核对。');
 const labels={source_title:'投稿标题',profile_hint:'原制作方式建议',video_content_type_hint:'投稿类型建议',other_type_note:'其它类型说明',
  topic:'内容主题',hook_candidate:'开头建议',structure_summary:'结构说明',narration_excerpt:'人工口播摘录',visual_observation:'人工画面观察',
  creative_reference:'结构参考',risk_notes:'待核实事项',observation_basis:'观察依据',source_verification:'来源核对声明',
  text_display_rights_claim:'文字展示许可声明',cover_rights_claim:'封面许可声明',media_reuse_claim:'素材复用声明',privacy_risk_claim:'隐私风险声明',rights_risk_notes:'许可风险说明'};
 const fields=Object.entries({...value.notes.case_notes,...value.notes.rights_claims}).filter(([key,text])=>labels[key] && text)
  .map(([key,text])=>`<div><dt>${labels[key]}</dt><dd>${escape(text)}</dd></div>`).join('');
 const segments=value.notes.segments.map(s=>`<li>第 ${escape(s.segment_order || '—')} 段：${escape(s.narration_excerpt || s.visual_or_ocr_observation || s.structural_value || '')}</li>`).join('');
 return `<h2>投稿人补充说明</h2><p class="muted">未经核验。类型、口播、分段、秒数和许可声明仅供对照，不能替代原始媒体证据。</p><dl>${fields}</dl>${segments?`<ol>${segments}</ol>`:''}`;
}
