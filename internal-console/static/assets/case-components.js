import { DOUYIN_PLAYER_VIEWPORTS } from "./case-media-preview.mjs?v=case-media-fit-1";

export const CASE_PROGRESS_STAGES = [
  ["acquire", "获取视频", 12],
  ["transcribe", "提取语音", 32],
  ["visual", "分析画面", 58],
  ["structure", "理解内容结构", 84],
  ["review", "生成审核结果", 100],
];

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

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
  const caseApproved = isCaseTask && task.current_case_status === "approved";
  const currentTaskId = isCaseTask && task.current_active_task_id && task.current_active_task_id !== task.task_id
    ? task.current_active_task_id : null;
  const reviewConflict = caseApproved && task.status === "awaiting_review";
  const caseHref = task.subject_ref ? `/cases/${encodeURIComponent(task.subject_ref)}` : "/cases";
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

  const failureAction = currentTaskId
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
      ? `<div class="next-action"><a class="btn btn-primary" href="${caseHref}">去审核案例</a></div>`
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
    <div class="task-progress-head"><div><h2>${isCaseTask ? (failed && boundaryReview ? "分镜待确认" : failed ? "这次分析未完成" : reviewConflict ? "本次分析待核对" : task.status === "completed" ? (caseApproved ? "案例已入库" : "本次审核已结束") : terminal ? "分析完成，等待审核" : "案例分析中") : (failed ? "任务未完成" : terminal ? "任务已完成" : "任务进行中")}</h2>
      <p>${escapeHtml(reviewConflict ? "这个来源已有入库案例，本次结果仍待核对。" : failed && boundaryReview ? "分镜划分尚待人工确认。" : failed && caseApproved ? "历史分析未完成；当前案例已入库。" : failed ? task.error_message || "请稍后重试。" : task.stage || "等待开始")}</p>
      ${isCaseTask && task.payload?.acquisition_provider === "legacy_downloader" && !task.payload?.source_upload
        ? `<p class="task-acquisition-label">视频获取方式：原有下载方式（未使用付费解析）</p>` : ""}</div>
      <strong>${Number(task.progress || 0)}%</strong></div>
    <div class="progress-track"><span style="width:${Math.max(0, Math.min(100, Number(task.progress || 0)))}%"></span></div>
    <ol class="progress-steps">${stages}</ol>
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
  const observed = labels[item.observed_source_profile];
  return [
    submission ? `提交标记：${submission}` : annotation ? `历史补充：${annotation}` : "",
    observed ? `系统观察：${observed}` : "",
  ].filter(Boolean);
}

function caseIndustryMetadata(item) {
  const historical = item.industry_annotation?.industry;
  return historical ? `行业（历史补充）：${historical}` : `行业：${item.industry || "待分类"}`;
}

export function caseCard(caseItem, statusPill) {
  const duration = caseItem.duration_seconds == null ? "时长未知" : `${Math.round(caseItem.duration_seconds)} 秒`;
  const source = caseItem.platform === "douyin" ? "抖音" : "视频来源";
  const optionalMeta = `<span>${escapeHtml(caseIndustryMetadata(caseItem))}</span>`;
  const profileMeta = caseProfileMetadata(caseItem).map((text) => `<span>${escapeHtml(text)}</span>`).join("");
  return `<a class="case-row" href="/cases/${encodeURIComponent(caseItem.case_id)}" data-route data-case-status="${escapeHtml(caseItem.status)}">
    <span class="case-row-main"><strong>${escapeHtml(caseItem.title)}</strong><span class="case-meta"><span>${source} · ${escapeHtml(duration)}</span>${optionalMeta}${profileMeta}</span></span>
    <span class="case-row-end">${statusPill(caseItem.status)}<span class="case-chevron" aria-hidden="true">›</span></span>
  </a>`;
}

function paragraphList(values) {
  return (values || []).filter(Boolean).map((value) => `<p>${escapeHtml(value)}</p>`).join("");
}

export function caseReviewContent(detail, statusPill) {
  const profileLine = caseProfileMetadata(detail).join(" · ") || "未记录结构类型";
  const industryLine = caseIndustryMetadata(detail);
  const annotationAction = detail.can_annotate_profile && !detail.operator_profile_hint
    ? `<button class="btn btn-secondary" type="button" data-profile-annotation>${detail.profile_annotation ? "修改历史补充" : "补充结构类型"}</button>` : "";
  const industryAction = detail.can_annotate_industry && detail.industry === "待分类"
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
  const reviewDecision = detail.review?.approved
    ? `<div class="approved-message"><strong>已进入案例库</strong><p>这个案例已经完成审核。</p></div>`
    : detail.review?.approval_recovery_required
      ? `<p>上次批准尚未完整保存。继续后只会完成原有批准，不会重复审核。</p><button class="btn btn-primary btn-wide" type="button" data-review-action="approve">完成批准</button>`
      : `<p>请对照原视频检查内容理解、叙事顺序与画面拆解。</p>
        <button class="btn btn-primary btn-wide" type="button" data-review-action="approve">批准入库</button>
        <button class="btn btn-secondary btn-wide" type="button" data-review-action="reanalyze">重新分析</button>
        <button class="btn btn-ghost btn-wide danger-text" type="button" data-review-action="reject">不收录</button>`;
  return `<main class="page page-review case-review-page">
    <div class="case-review-heading"><a class="back-link" href="/cases" data-route>← 案例</a><div>${statusPill(detail.status)}</div></div>
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
        <section class="case-analysis"><h2>分析结果</h2>
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
      <aside class="review-aside"><section class="panel review-decision"><h2>人工审核</h2>
        ${reviewDecision}
        <p class="review-rights-note">批准不会改变原视频素材使用权。</p>
      </section></aside>
    </section>
  </main>`;
}
