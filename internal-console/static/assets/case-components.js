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

export function progressPanel(task, { compact = false, embedded = false } = {}) {
  const activeIndex = currentStageIndex(task);
  const terminal = ["awaiting_review", "completed"].includes(task.status);
  const failed = task.status === "failed";
  const isCaseTask = task.task_type === "case_analysis";
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

  const failureAction = mediaDuplicate
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
    : isCaseTask && task.status === "awaiting_review"
      ? `<div class="next-action"><a class="btn btn-primary" href="${caseHref}">去审核案例</a></div>`
      : isCaseTask && task.status === "completed"
        ? `<div class="next-action"><a class="btn btn-primary" href="${caseHref}">查看案例</a></div>`
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
    <div class="task-progress-head"><div><h2>${isCaseTask ? (failed ? "案例分析未完成" : task.status === "completed" ? "案例已入库" : terminal ? "分析完成，等待审核" : "案例分析中") : (failed ? "任务未完成" : terminal ? "任务已完成" : "任务进行中")}</h2>
      <p>${escapeHtml(failed ? task.error_message || "请稍后重试。" : task.stage || "等待开始")}</p></div>
      <strong>${Number(task.progress || 0)}%</strong></div>
    <div class="progress-track"><span style="width:${Math.max(0, Math.min(100, Number(task.progress || 0)))}%"></span></div>
    <ol class="progress-steps">${stages}</ol>
    ${failureAction}
  </section>`;
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

export function caseCard(caseItem, statusPill) {
  const duration = caseItem.duration_seconds == null ? "时长未知" : `${Math.round(caseItem.duration_seconds)} 秒`;
  const source = caseItem.platform === "douyin" ? "抖音" : "视频来源";
  const optionalMeta = `<span>行业：${escapeHtml(caseItem.industry || "待分类")}</span>`;
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
  const annotationAction = detail.can_annotate_profile && !detail.operator_profile_hint
    ? `<button class="btn btn-secondary" type="button" data-profile-annotation>${detail.profile_annotation ? "修改历史补充" : "补充结构类型"}</button>` : "";
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
