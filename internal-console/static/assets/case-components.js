import { DOUYIN_PLAYER_VIEWPORTS } from "./case-media-preview.mjs?v=case-media-fit-1";
import { escapeHtml, caseListCard } from "./list-ui.mjs?v=case-joint-1";
import { accountLabel, formatConsoleTime } from "./ui-format.mjs?v=flow-closure-2";
import { evidenceWorkspace, reviewWorkspace } from "./case-evidence-workspace.mjs?v=case-review-ux1";
import { sharePreviewPanel } from "./case-share-confirmation.mjs?v=case-joint-1";
import { typeConfirmationMarkup } from './case-type-confirmation.mjs?v=case-joint-1';
import { caseRecovery, caseResultPanel } from "./case-review-result.mjs?v=case-joint-1";
export { escapeHtml };

export const CASE_PROGRESS_STAGES = [
  ["acquire", "获取视频", 12],
  ["transcribe", "提取语音", 32],
  ["visual", "分析画面", 58],
  ["structure", "理解内容结构", 84],
  ["review", "生成审核结果", 100],
];

function currentStageIndex(task) {
  const labels = CASE_PROGRESS_STAGES.map(([, label]) => label);
  const exact = labels.indexOf(task.stage);
  if (exact >= 0) return exact;
  return CASE_PROGRESS_STAGES.findIndex(([, , threshold]) => task.progress < threshold);
}

export function progressPanel(task, { compact = false, embedded = false, boundaryReview = null } = {}) {
  const activeIndex = currentStageIndex(task);
  const terminal = ["awaiting_review", "completed"].includes(task.status);
  const failed = task.status === "failed";
  const isCaseTask = task.task_type === "case_analysis";
  const isRevision = isCaseTask && Boolean(task.payload?.evidence_revision);
  const caseApproved = isCaseTask && task.current_case_status === "approved";
  const currentTaskId = isCaseTask && task.current_active_task_id && task.current_active_task_id !== task.task_id
    ? task.current_active_task_id : null;
  const reviewConflict = caseApproved && task.status === "awaiting_review";
  const classificationHref = task.subject_ref ? `/cases/${encodeURIComponent(task.subject_ref)}/classification` : "/cases";
  const caseHref = task.subject_ref ? `/cases/${encodeURIComponent(task.subject_ref)}${isRevision ? `?attempt_id=${encodeURIComponent(task.payload.evidence_revision.attempt_id)}` : ""}` : "/cases";
  const stages = CASE_PROGRESS_STAGES.map(([, label, threshold], index) => {
    const done = terminal || task.progress >= threshold;
    const active = !failed && !done && index === Math.max(0, activeIndex);
    return `<li class="progress-step ${done ? "done" : ""} ${active ? "active" : ""}">
      <span class="progress-marker">${done ? "✓" : active ? "→" : "○"}</span>
      <span>${label}</span>
    </li>`;
  }).join("");
    const mediaDuplicate =
    failed &&
    isCaseTask &&
    task.error_code === "MEDIA_DUPLICATE_CASE" &&
    task.payload?.duplicate?.existing_case_id;

  const failureAction = isRevision
    ? `<div class="next-action"><strong>${failed ? "修改已保存，校验尚未完成" : terminal ? "修订校验已结束" : "正在校验已保存的修改"}</strong>
        <span>${failed ? "恢复会继续原校验任务，保留修改，不会重新投稿。校验通过前不能批准旧分析结果。" : "返回案例核对当前修订结果；校验完成不等于批准入库。"}</span>
        ${failed && !caseApproved ? '<button class="btn btn-primary" type="button" data-retry-revision>继续校验</button>' : ""}
        <a class="btn btn-secondary" href="${caseHref}" data-route>返回案例审核</a></div>`
    : currentTaskId
    ? `<div class="next-action"><strong>已有新的分析任务</strong><span>这条记录保留本次分析的结果，请查看当前任务的真实进度。</span><a class="btn btn-primary" href="/tasks/${encodeURIComponent(currentTaskId)}" data-route>查看当前进度</a></div>`
    : failed && caseApproved
    ? `<div class="next-action"><strong>案例已经入库</strong><span>这次分析没有完成，但后续的案例已通过审核，无需重新分析。</span><a class="btn btn-primary" href="${caseHref}" data-route>查看已入库案例</a></div>`
    : mediaDuplicate
    ? `<div class="next-action">
        <strong>这个视频内容已经存在</strong>
        <span>虽然来源链接不同，但获取到的视频文件与已有案例完全相同。</span>
        <a class="btn btn-secondary"
           href="/cases/${encodeURIComponent(
             task.payload.duplicate.existing_case_id
           )}"
           data-route>
          查看已有案例
        </a>
      </div>`
    : reviewConflict
      ? `<div class="next-action"><strong>本次结果需要核对</strong><span>这个来源已有入库案例，但本次任务的审核记录未与其对应。</span><a class="btn btn-secondary" href="${caseHref}" data-route>查看已入库案例</a></div>`
    : isCaseTask && task.status === "awaiting_review"
      ? `<div class="next-action"><a class="btn btn-primary" href="${task.payload?.operator_profile_hint || task.payload?.profile ? caseHref : classificationHref}" data-route>查看并确认分类</a></div>`
      : isCaseTask && task.status === "completed" && caseApproved
        ? `<div class="next-action"><a class="btn btn-primary" href="${caseHref}">查看案例</a></div>`
      : isCaseTask && task.status === "completed"
        ? `<div class="next-action"><strong>本次任务已结束</strong><span>这条记录会保留；当前没有已入库案例需要查看。</span><a class="btn btn-secondary" href="/cases" data-route>返回案例库</a></div>`
      : isCaseTask && failed && boundaryReview
      ? `<div class="next-action"><strong>分镜需要确认</strong><span>请在下方对照原视频确认短镜头，确认后会继续本次分析，不会重新下载或重复分析画面。</span></div>`
      : isCaseTask && failed
      ? `<div class="next-action">
          <strong>下一步</strong>
          <span>${task.error_code === "SOURCE_ACQUISITION_FAILED" ? "未能获取原视频，尚未形成可审核案例。" : "分析未完成，尚未形成可审核案例。"}如需再次尝试，请显式重新分析。</span>
          <a class="btn btn-secondary" href="/cases/new?retry_task=${encodeURIComponent(task.task_id || "")}" data-route>返回添加案例</a>
        </div>`
      : failed
        ? `<div class="next-action"><strong>下一步</strong><span>本次任务未完成，请返回对应业务页面确认状态。</span><a class="btn btn-secondary" href="/tasks" data-route>返回任务记录</a></div>`
      : `<p class="progress-note">
          你可以离开这个页面，任务进度会保留在“任务记录”中。
        </p>`;
  return `<section class="${embedded ? "" : "card "}task-progress ${compact ? "compact" : ""} ${embedded ? "embedded" : ""}" data-task-progress>
    <div class="task-progress-head"><div><h2>${isRevision ? (failed ? "修订校验未完成" : terminal ? "修订校验已完成" : "修订校验中") : isCaseTask ? (failed && boundaryReview ? "分镜待确认" : failed ? "这次分析未完成" : reviewConflict ? "本次分析待核对" : task.status === "completed" ? (caseApproved ? "案例已入库" : "本次审核已结束") : terminal ? "分析完成，等待审核" : "案例分析中") : (failed ? "任务未完成" : terminal ? "任务已完成" : "任务进行中")}</h2>
      <p>${escapeHtml(reviewConflict ? "这个来源已有入库案例，本次结果仍待核对。" : failed && boundaryReview ? "分镜划分尚待人工确认。" : failed && caseApproved ? "历史分析未完成；当前案例已入库。" : failed ? task.error_message || "请稍后重试。" : task.stage || "等待开始")}</p>
      ${isCaseTask && task.payload?.acquisition_provider === "legacy_downloader" && !task.payload?.source_upload
        ? `<p class="task-acquisition-label">视频获取方式：原有下载方式（未使用付费解析）</p>` : ""}</div>
      ${isCaseTask ? "" : `<strong>${Number(task.progress || 0)}%</strong>`}</div>
    ${isCaseTask ? "" : `<div class="progress-track"><span style="width:${Math.max(0, Math.min(100, Number(task.progress || 0)))}%"></span></div>`}
    ${isRevision ? "" : `<ol class="progress-steps">${stages}</ol>`}
    ${failureAction}
  </section>`;
}

export function boundaryReviewPanel(review) {
  if (!review?.items?.length) return "";
  const rows = review.items.map((item, index) => {
    const issue = item.issues?.[0] || {};
    const start = Number(issue.start);
    const end = Number(issue.end);
    const span = Number.isFinite(start) && Number.isFinite(end)
      ? `${start.toFixed(2)}–${end.toFixed(2)} 秒`
      : Number.isFinite(start) ? `${start.toFixed(2)} 秒附近` : "请对照原视频";
    return `<fieldset class="boundary-review-row"><legend>分镜 ${index + 1} · ${span}</legend>
      <p>${issue.type === "short_shot" ? "这段镜头不足半秒，请确认是否为独立画面。" : "这个切换点需要人工确认。"}</p>
      <div class="boundary-review-choices">
        <label><input type="radio" name="boundary-${index}" value="keep" required>保留分镜</label>
        ${item.frame_id === "frame_000000000ms.jpg" || item.issues?.some(issue => issue.merge_allowed === false)
          ? "" : `<label><input type="radio" name="boundary-${index}" value="reject" required>合并相邻分镜</label>`}
      </div></fieldset>`;
  }).join("");
  return `<section class="panel boundary-review-panel"><h2>确认视频分镜</h2>
    <p>请先对照原视频逐项判断。保留或合并只影响分镜划分，不会自动批准案例。</p>
    ${review.source_url ? `<a href="${escapeHtml(review.source_url)}" target="_blank" rel="noopener noreferrer">在抖音打开原视频 ↗</a>` : ""}
    <form data-boundary-review data-shot-sha="${escapeHtml(review.shot_sha256)}">${rows}
      <button class="btn btn-primary" type="submit">确认并继续分析</button></form></section>`;
}

function caseProfileMetadata(item) {
  const labels = { mix: "混剪型", news: "新闻体", hybrid: "混合型", uncertain: "不确定" };
  const submission = labels[item.operator_profile_hint];
  const annotation = labels[item.profile_annotation?.operator_profile_hint];
  const classification = item.classification?.status === "confirmed" ? labels[item.classification.profile] : null;
  const observed = labels[item.observed_source_profile];
  return [
    submission ? `提交标记：${submission}` : "",
    annotation ? `人工标签：${annotation}` : "",
    classification ? `分类确认：${classification}` : "",
    observed ? `系统观察：${observed}` : "",
  ].filter(Boolean);
}

function caseIndustryMetadata(item) {
  if (item.classification?.status === "confirmed" && !item.industry_annotation)
    return `行业（人工确认）：${item.classification.industry || "未确定"}`;
  const historical = item.industry_annotation?.industry;
  return historical ? `行业（历史补充）：${historical}` : `行业：${item.industry || "待分类"}`;
}

export function caseCard(caseItem, statusPill) {
  const industry=caseItem.industry_annotation?.industry || (caseItem.classification?.status === "confirmed" ? caseItem.classification.industry : caseItem.industry);
  return caseListCard({...caseItem,industry},statusPill);
}

function paragraphList(values) {
  return (values || []).filter(Boolean).map((value) => `<p>${escapeHtml(value)}</p>`).join("");
}

export function caseReviewContent(detail, statusPill, {operations = [], recoveryUnavailable = false} = {}) {
  const profileLine = caseProfileMetadata(detail).join(" · ") || "未记录结构类型";
  const industryLine = caseIndustryMetadata(detail);
  const annotationAction = detail.can_annotate_profile
    ? `<button class="btn btn-secondary" type="button" data-profile-annotation>${detail.profile_annotation ? "修改历史补充" : "补充结构类型"}</button>` : "";
  const industryAction = detail.can_annotate_industry
    ? `<button class="btn btn-secondary" type="button" data-industry-annotation>${detail.industry_annotation ? "修改历史补充行业" : "补充行业"}</button>` : "";
  const development = paragraphList(detail.how_it_tells?.development);
  const reviewMedia = detail.review_media || {};
  const sourceUrl = reviewMedia.source_url || detail.source_url || "";
  const remoteEmbedUrl = reviewMedia.remote_embed_url || "";
  const sourceWidth = Number(reviewMedia.source_width) || 9;
  const sourceHeight = Number(reviewMedia.source_height) || 16;
  const orientation = sourceWidth > sourceHeight ? "landscape" : "portrait";
  const isRemotePlayer = !reviewMedia.local_available && Boolean(remoteEmbedUrl);
  const playerViewport = DOUYIN_PLAYER_VIEWPORTS[orientation];
  const mediaSurface = reviewMedia.local_available
    ? `<video controls playsinline preload="metadata" src="${escapeHtml(reviewMedia.local_url)}"></video>`
    : remoteEmbedUrl
      ? `<iframe class="douyin-review-player" width="${playerViewport.width}" height="${playerViewport.height}" src="${escapeHtml(remoteEmbedUrl)}" title="抖音原视频审核预览" loading="lazy" scrolling="no" allowfullscreen></iframe>`
      : `<div class="review-media-unavailable"><strong>预览暂时不可用</strong><span>请在抖音打开原视频完成审核。</span></div>`;
  const sourceLink = sourceUrl
    ? `<a class="source-video-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">在抖音打开原视频</a>`
    : "";
  const reviewSurfaceNote = reviewMedia.operator_uploaded
    ? `<p class="review-source-note">本次分析使用提交人上传的文件。请对照抖音原视频确认文件对应且内容完整；来源不可核实时请勿批准。</p>`
    : reviewMedia.local_available
    ? ""
    : `<p class="review-source-note">当前通过抖音原视频进行审核。</p>`;
  const shots = (detail.full_breakdown?.shots || []).map((shot) => `<article class="breakdown-shot">
    <div class="shot-time">画面 ${shot.number} · ${Number(shot.start || 0).toFixed(1)}–${Number(shot.end || 0).toFixed(1)} 秒</div>
    ${shot.narration ? `<p><strong>口播</strong>${escapeHtml(shot.narration)}</p>` : ""}
    ${shot.scene ? `<p><strong>画面</strong>${escapeHtml(shot.scene)}</p>` : ""}
    ${shot.onscreen_text ? `<p><strong>画面文字</strong>${escapeHtml(shot.onscreen_text)}</p>` : ""}
    ${shot.function ? `<p><strong>作用</strong>${escapeHtml(shot.function)}</p>` : ""}
  </article>`).join("");
  const evidenceReview = detail.evidence_review || null;
  const classificationPending = detail.classification_required && detail.classification?.status !== "confirmed";
  const canReview = detail.permissions?.can_review === true && detail.review?.can_review === true;
  const canConfirmEvidence = canReview && !classificationPending && !detail.review?.approved;
  const narrationQuestions = (evidenceReview?.narration_items || []).map((item) => `<label class="case-evidence-item">
    <span><strong>口播 ${Number(item.start || 0).toFixed(1)}–${Number(item.end || 0).toFixed(1)} 秒</strong>
      <small>当前拆解保留原始语音识别${item.suggested_text && item.suggested_text !== item.source_text ? "，未自动采用系统修正" : ""}。</small>
      ${item.source_text ? `<span class="case-evidence-text">${escapeHtml(item.source_text)}</span>` : ""}
    </span>
    ${canConfirmEvidence ? `<span class="case-evidence-check"><input type="checkbox" data-evidence-kind="narration" data-item-id="${escapeHtml(item.item_id)}">确认保留原识别</span>` : ""}
  </label>`).join("");
  const shotQuestions = (evidenceReview?.shot_items || []).map((item) => `<label class="case-evidence-item">
    <span><strong>分镜 ${Number(item.start || 0).toFixed(1)}${item.end == null ? "" : `–${Number(item.end).toFixed(1)}`} 秒</strong>
      <small>这一处的分镜划分需要核对，当前拆解暂时保留现有划分。</small></span>
    ${canConfirmEvidence ? `<span class="case-evidence-check"><input type="checkbox" data-evidence-kind="shot" data-item-id="${escapeHtml(item.item_id)}">确认保留当前分镜</span>` : ""}
  </label>`).join("");
  const workspace = reviewWorkspace(detail);
  // An editable draft is not a trusted preview or permission. It lets an
  // authorized reviewer repair display-only validation failures through the
  // same server preview Owner, while approval stays disabled until reissued.
  const shareDraft = detail.share_preview || (canReview && !classificationPending && workspace?.can_approve
    && detail.permissions?.can_review && !detail.review?.approved ? {draft_only:true,
      preview:{display:{title:String(detail.title || '').slice(0,120),structure_summary:'',industry:detail.classification?.industry}},
      blocker:{message:'请核对展示文字，再获取可信预览；通过前不能批准。'}} : null);
  const evidenceReviewSurface = workspace ? evidenceWorkspace(workspace,escapeHtml) : evidenceReview?.required
    ? evidenceReview.available
      ? `<section class="panel case-evidence-review"><h2>${canConfirmEvidence ? "入库前确认" : detail.review?.decision ? "分析疑点记录" : "待审核的分析疑点"}</h2><p>${canConfirmEvidence ? '请对照原视频核对以下疑点。确认只认可当前展示的原识别与分镜，不会自动采用系统猜测；不准确时请重新分析，暂不要批准。勾选尚未保存，点击“确认并批准入库”后提交。' : detail.review?.decision ? "本次审核已结束，以下保留原分析疑点供追溯，无需重新确认。" : "以下疑点由指定审核人在正式审核时核对；此处仅供查看，无需重复确认分类。"}</p>
          <div class="case-evidence-list">${narrationQuestions}${shotQuestions}</div>${canConfirmEvidence ? '<button class="btn btn-secondary" type="button" data-scroll-review-decision>前往提交审核</button>' : ""}</section>`
      : `<section class="panel case-evidence-review"><h2>分析证据</h2><p>待审核的分析证据暂时无法读取，请刷新后重试或联系管理员。</p></section>`
    : "";
  const reviewDecision = detail.review?.approved
    ? `<div class="approved-message"><strong>${escapeHtml(detail.sharing_label || "已加入正式案例库")}</strong><p>正式收录记录已保存。${escapeHtml(detail.sharing_next_action || "")}</p></div>`
    : detail.review?.decision
      ? `<p><strong>${detail.review.decision === "reanalyze" ? "本次分析已退回重新处理" : "本次投稿未收录"}</strong></p><p>${escapeHtml(detail.review.reason || "请查看已保存的人工审核决定。")}</p>
        <p class="review-source-note">${escapeHtml(accountLabel(detail.reviewed_by?.phone))}${detail.review.reviewed_at ? ` · ${escapeHtml(formatConsoleTime(detail.review.reviewed_at))}` : ""}</p>
        <p>原决定保留，新尝试不会覆盖本次审核记录。</p>${detail.permissions?.can_reanalyze ? `<a class="btn btn-secondary" href="/cases/new?reanalyze_case=${encodeURIComponent(detail.case_id)}&attempt_id=${encodeURIComponent(detail.review.attempt_id)}" data-route>重新分析这条投稿</a>` : ""}`
    : !detail.permissions?.can_review
      ? classificationPending
        ? `<p>先核对分类，再交由指定审核人处理。</p><a class="btn btn-primary" href="/cases/${detail.case_id}/classification" data-route>核对分类</a>`
        : `<p>${detail.classification?.status === "confirmed" ? "分类已确认，等待指定审核人完成审核。" : "投稿已整理，等待指定审核人完成审核。"}</p><p class="review-source-note">分类确认不等于正式收录，无需再次勾选审核疑点。</p>`
    : !canReview
      ? `<p>当前投稿状态暂不可审核，请刷新后查看最新进度。</p>`
    : classificationPending
      ? `<p>请先检查系统推荐的行业与视频结构，确认后继续审核。</p><a class="btn btn-primary" href="/cases/${detail.case_id}/classification" data-route>确认分类</a>`
    : detail.review?.approval_recovery_required
      ? `<p>上次批准尚未完整保存。继续后只会完成原有批准，不会重复审核。</p><button class="btn btn-primary btn-wide" type="button" data-review-action="approve">完成批准</button>`
      : `<p>请对照原视频检查内容理解、叙事顺序与画面拆解。</p>
        ${detail.share_preview_error ? `<p role="alert">${escapeHtml(detail.share_preview_error.message)} ${escapeHtml(detail.share_preview_error.next_action)}</p>` : ""}
        <button class="btn btn-primary btn-wide" type="button" data-review-action="approve"${(detail.approval_context?.version === "human-review-command-v1.2" && !detail.share_preview) || (workspace ? !workspace.can_approve : evidenceReview?.required && !evidenceReview.available) ? " disabled" : ""}>${detail.share_preview?.mode === "approve_and_share" ? "收录并共享" : detail.share_preview?.mode === "approve_only" ? "批准入库" : evidenceReview?.required ? "确认并批准入库" : "批准入库"}</button>
        <button class="btn btn-secondary btn-wide" type="button" data-review-action="reanalyze">重新分析</button>
        <button class="btn btn-ghost btn-wide danger-text" type="button" data-review-action="reject">不收录</button>`;
  return `<main class="page page-review case-review-page${detail.review?.approved ? ' case-review-complete' : ''}">
    <div class="case-review-heading"><a class="back-link" href="/cases" data-route>← 案例</a>${detail.review?.approved ? '' : `<div>${statusPill(detail.status)}</div>`}</div>
    ${caseResultPanel(detail, caseRecovery(detail, operations), escapeHtml, recoveryUnavailable)}
    <section class="review-layout">
      <div class="review-primary">
        <section class="panel media-summary">
          <div class="review-media-shell ${orientation}">
            <div class="review-media-player ${orientation}${isRemotePlayer ? " remote" : ""}">${mediaSurface}</div>
            <div class="review-media-meta"><h1>${escapeHtml(detail.title)}</h1>
              <p class="media-meta-line">${detail.platform === "douyin" ? "抖音" : "视频来源"} · ${detail.duration_seconds == null ? "时长未知" : `${Math.round(detail.duration_seconds)} 秒`}</p>
              <p class="media-meta-line">${escapeHtml(industryLine)}</p>
              ${industryAction}
              <p class="media-meta-line">${escapeHtml(profileLine)}</p>
              ${annotationAction}
              ${detail.description ? `<p class="media-description">${escapeHtml(detail.description)}</p>` : ""}
              ${sourceLink}
              ${reviewSurfaceNote}
            </div>
          </div>
        </section>
        ${evidenceReviewSurface}
        ${detail.review?.approved ? '' : typeConfirmationMarkup(detail.video_type_context,escapeHtml)}
        ${shareDraft ? sharePreviewPanel(shareDraft) : ""}
        <section class="case-analysis"><h2>${workspace?.state === "unavailable" ? "已有分析（审核范围尚未恢复）" : workspace && !["original","validated"].includes(workspace.state) ? "原分析（新修订尚未生效）" : "分析结果"}</h2>
        <div class="review-section"><h3>讲了什么</h3>
          ${detail.what_it_says?.topic ? `<div class="review-row"><span>内容主题</span><p>${escapeHtml(detail.what_it_says.topic)}</p></div>` : ""}
          ${detail.what_it_says?.core_expression ? `<div class="review-row"><span>核心表达</span><p>${escapeHtml(detail.what_it_says.core_expression)}</p></div>` : ""}
        </div>
        <div class="review-section"><h3>怎么讲</h3>
          ${detail.how_it_tells?.opening ? `<div class="review-row"><span>开头</span><p>${escapeHtml(detail.how_it_tells.opening)}</p></div>` : ""}
          ${development ? `<div class="review-row"><span>中段</span><div>${development}</div></div>` : ""}
          ${detail.how_it_tells?.ending ? `<div class="review-row"><span>结尾</span><p>${escapeHtml(detail.how_it_tells.ending)}</p></div>` : ""}
        </div>
        <div class="review-section"><h3>值得参考</h3>${paragraphList(detail.reusable_observations)}</div>
        </section>
        <details class="full-breakdown"><summary>完整拆解 <span>口播与画面逐段对照</span></summary>
          <div class="breakdown-body">${detail.full_breakdown?.narration ? `<section><h3>完整口播</h3><p class="narration-text">${escapeHtml(detail.full_breakdown.narration)}</p></section>` : ""}
          <section><h3>画面拆解</h3><div class="breakdown-list">${shots}</div></section></div>
        </details>
      </div>
      ${detail.review?.approved ? '' : `<aside class="review-aside"><section class="panel review-decision" id="case-review-decision" tabindex="-1"><h2>人工审核</h2>
        ${reviewDecision}
        <p class="review-rights-note">批准不会改变原视频素材使用权。</p>
      </section></aside>`}
    </section>
  </main>`;
}
