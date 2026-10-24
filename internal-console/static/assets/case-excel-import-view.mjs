import { escapeHtml as esc } from './case-components.js?v=flow-closure-2';

const issueLabels={
  REQUIRED:'必填项未填写',SOURCE_REQUIRED:'请提供视频链接或待上传的视频文件名',
  OTHER_NOTE_REQUIRED:'选择其它类型时请填写说明',PROFILE_TYPE_REVIEW_REQUIRED:'制作方式与类型建议不一致，需要审核人核对',
  MEDIA_UPLOAD_BINDING_REQUIRED:'尚未上传对应视频，可先保存，之后补充来源',TEXT_ONLY_NEEDS_EVIDENCE:'仅有文字说明，保存后仍需补充证据',
  EXTERNAL_KEY_INVALID_OR_RESERVED:'请填写有效案例编号，不能使用示例的 DEMO 编号',
  DUPLICATE_SOURCE_IN_WORKBOOK:'本文件中已存在同一视频来源，请去掉重复行',ORPHAN_CASE_KEY:'此案例编号在案例清单中不存在',
  SEGMENT_ORDER_NOT_CONTIGUOUS_UNIQUE:'分段序号必须从 1 开始、连续且不重复',
  OBSERVATION_REQUIRES_PERSONAL_VIEWING:'未亲自观看时不能填写画面观察或时长',
  TYPE_HINT_UNKNOWN:'请使用模板中的视频类型选项',PROFILE_HINT_UNKNOWN:'请使用模板中的制作方式选项',
  OBSERVATION_BASIS_UNKNOWN:'请使用模板中的观察依据选项',TIME_HINT_INVALID:'请填写有效的非负秒数',
  END_NOT_AFTER_START:'结束时间必须晚于开始时间',END_BEYOND_UNVERIFIED_DURATION_HINT:'分段结束时间不能超过所填视频时长',
  SEGMENT_ORDER_INVALID:'请填写从 1 开始的正整数分段序号',RIGHTS_DUPLICATE:'每个案例只保留一条来源与许可说明',
  MEDIA_FILENAME_UNSAFE:'请只填写视频文件名，不要填写磁盘路径',
};
const fieldLabels={external_case_key:'案例编号',source_platform:'来源平台',submission_mode:'提交方式',source_url:'视频链接',
  media_filename:'视频文件名',source_title:'内容标题',profile_hint:'制作方式建议',video_content_type_hint:'视频类型建议',
  other_type_note:'其它类型说明',topic:'主题',structure_summary:'结构摘要',observation_basis:'观察依据',
  segment_order:'分段序号',start_seconds_hint:'开始秒数',end_seconds_hint:'结束秒数',duration_seconds_hint:'时长参考',
  segment_basis:'分段依据',visual_or_ocr_observation:'画面观察'};

export function issuesMarkup(issues) {
  return `<ul class="excel-row-issues">${issues.map(issue=>`<li data-severity="${issue.severity==='error'?'error':'note'}"><strong>${issue.severity==='error'?'需修改':issue.severity==='pending'?'待补充':'待核对'}</strong><span>${esc(issueLabels[issue.code] || '请核对原文件中的此项填写')}<small>${esc(issue.sheet)} · 第 ${esc(issue.row)} 行 · ${esc(fieldLabels[issue.field] || '填写内容')}</small></span></li>`).join('')}</ul>`;
}

export function importSelectionMarkup(preview) {
  return `<div class="excel-selection-heading"><div><h2>选择要保存的案例</h2><p class="excel-help">填写无误的案例已勾选，你可以调整本次保存范围。</p></div><span class="excel-badge">私有 · 待核验</span></div>
    <div class="excel-case-list">${preview.rows.map(row=>`<article class="excel-import-selection ${row.status==='invalid'?'excel-row-invalid':''}"><label class="excel-case-choice"><input type="checkbox" data-import-row="${row.row}" ${row.status==='invalid'?'disabled':'checked'}><span><strong>${esc(row.raw.source_title || row.external_case_key || '未命名案例')}</strong><small>Excel 第 ${row.row} 行 · 编号 ${esc(row.external_case_key)}</small></span><span class="excel-badge ${row.status==='invalid'?'excel-badge-warning':''}">${row.status==='invalid'?'需修改':'待核验'}</span></label>
      <div class="excel-case-body"><p class="excel-case-meta"><span>${esc(row.raw.video_content_type_hint || '待判断')} · 投稿建议</span><span>正式类型：尚未审核</span></p>
      ${row.status==='invalid'?'<p class="excel-row-guidance">请修改原 Excel 中的问题后重新上传，此行暂不能选择。</p>':''}
      ${issuesMarkup(row.issues || preview.issues?.filter(i=>i.sheet==='案例清单' && i.row===row.row) || [])}
      ${row.canonical_source_key && row.status!=='invalid'?`<details class="excel-media-details"><summary>补充对应视频（可选）</summary><p class="excel-help">已填写来源：${esc(row.raw.source_url)}</p>
        <label>本行对应的视频文件<input type="file" accept=".mp4,.mov,.m4v,.webm" data-import-video="${row.row}"></label>
        <label class="excel-upload-consent"><input type="checkbox" data-import-rights="${row.row}"> 我有权上传此视频，且文件与本行来源链接对应。</label><p class="excel-help">上传不授予生产复用权；视频上传后 24 小时内有效，保存时会重新核对。</p></details>`:''}</div></article>`).join('')}</div>
    <p class="excel-help excel-private-note">保存后仅你可见，内容与许可仍待核验，不开始分析或共享。</p>`;
}

export async function fileBase64(file) {
  const bytes=new Uint8Array(await file.arrayBuffer()); let value='';
  for(let n=0;n<bytes.length;n+=32768) value+=String.fromCharCode(...bytes.subarray(n,n+32768));
  return btoa(value);
}

