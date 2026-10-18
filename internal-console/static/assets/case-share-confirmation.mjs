import { escapeHtml, formatCaseDuration } from './list-ui.mjs?v=case-share-ux2';

export function sharePreviewCard(bundle) {
  const display = bundle.preview.display;
  const duration = formatCaseDuration(display.duration_seconds);
  const tags = [display.industry || '行业暂未确认', display.video_type, duration].filter(Boolean);
  return `<div class="share-preview-cover" aria-label="未获封面展示许可，使用品牌占位图">
      <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><rect x="5" y="5" width="22" height="22" rx="6"/><path d="m13 11 8 5-8 5z"/></svg><span>品牌占位封面</span>
    </div><div class="share-preview-content"><h3>${escapeHtml(display.title || '尚未设置展示标题')}</h3>
      <div class="share-preview-meta">${tags.map(tag=>`<span>${escapeHtml(tag)}</span>`).join('')}</div>
      <div class="share-preview-reference"><span>结构参考</span><p>${escapeHtml(display.structure_summary || '暂未添加结构参考。')}</p></div>
    </div>`;
}

export function sharePreviewPanel(bundle) {
  const draft = bundle.draft_only;
  const display = bundle.preview.display;
  const status = draft ? '请先核对展示内容，再继续批准。'
    : bundle.blocker?.message || '审核通过后同步共享，无需再次发布。';
  return `<section class="panel case-share-preview" aria-labelledby="share-preview-heading" data-preview-state="${draft?'draft':'ready'}">
    <header class="share-preview-heading"><div><h2 id="share-preview-heading">${draft?'核对共享展示内容':'共享展示预览'}</h2><p>${draft?'修改展示信息后，重新核对预览':bundle.mode==='approve_only'?'本次仅批准入库，不会共享':'审核通过后，平台用户可见以下信息'}</p></div><span class="share-preview-audience">${draft?'待核对':bundle.mode==='approve_only'?'仅预览':'平台内共享'}</span></header>
    <div class="share-preview-card" data-share-preview-card>${sharePreviewCard(bundle)}</div>
    <div class="share-preview-notes"><p data-share-preview-feedback role="status">${escapeHtml(status)}</p><span>原视频与素材使用权不随案例共享</span></div>
    <details class="share-preview-editor"${draft?' open':''}>
      <summary>编辑展示内容<span aria-hidden="true">⌄</span></summary>
      <div class="share-preview-fields"><p class="share-preview-edit-hint">可摘取原标题和结构摘要中的准确内容，不增加来源之外的主张。</p>
        <div class="field"><label for="share-preview-title">展示标题</label><input id="share-preview-title" maxlength="120" value="${escapeHtml(display.title)}"></div>
        <div class="field"><label for="share-preview-summary">结构参考摘要</label><textarea id="share-preview-summary" maxlength="1000" rows="3">${escapeHtml(display.structure_summary)}</textarea></div>
        <div class="share-preview-edit-actions"><button type="button" class="btn btn-primary" data-save-share-preview${draft?'':' disabled'}>保存并核对</button>${draft?'':'<button type="button" class="btn btn-ghost" data-cancel-share-preview>放弃修改</button>'}</div>
      </div>
    </details>
  </section>`;
}

export function shareConfirmation(bundle) {
  if (!bundle) return null;
  const share = bundle.mode === "approve_and_share";
  const display = bundle.preview.display;
  const fields = [display.title && `标题：${display.title}`, display.industry && `行业：${display.industry}`,
    display.video_type && `视频类型：${display.video_type}`,
    display.duration_seconds != null && `时长：${display.duration_seconds} 秒`,
    display.structure_summary && `结构参考：${display.structure_summary}`, "封面：品牌占位图，未授权原封面"].filter(Boolean).join("；");
  return {
    title: share ? "确认收录并共享案例？" : "确认批准入库？",
    confirmLabel: share ? "确认收录并共享" : "确认批准入库",
    description: share ? `请确认案例来源、视频内容和分析结果准确，且具有创作参考价值。审核通过后，将把以下允许展示的信息分享给平台用户。${fields}。共享不授予原视频使用权。`
      : `${bundle.blocker.message} 本次只批准入库，不产生共享许可。`,
    decision: {schema_version:"case-human-display-decision-v1.0",decision:share?"publish_exact_preview":"approve_only",
      preview_sha256:bundle.preview_sha256,preview:bundle.preview,blocker_sha256:bundle.blocker_sha256,
      origin:"human_joint_final_confirmation"}
  };
}

export function shareResultMessage(result) {
  return result.sharing_state === "approved_shared" ? "案例已收录并共享"
    : result.sharing_state === "approved_withdrawn" ? "案例已收录，共享已撤回"
    : result.sharing_state === "approved_reconfirm" ? "案例已收录，需重新核对展示内容" : "案例已收录，共享尚未完成";
}
