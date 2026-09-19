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

export function progressPanel(task, { compact = false } = {}) {
  const activeIndex = currentStageIndex(task);
  const terminal = ["awaiting_review", "completed"].includes(task.status);
  const failed = task.status === "failed";
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
    : failed
      ? `<div class="next-action">
          <strong>下一步</strong>
          <span>返回添加案例，检查视频链接后重新提交。</span>
        </div>`
      : `<p class="progress-note">
          你可以离开这个页面，任务进度会保留在“任务记录”中。
        </p>`;
  return `<section class="card task-progress ${compact ? "compact" : ""}" data-task-progress>
    <div class="task-progress-head"><div><h2>${failed ? "案例分析未完成" : terminal ? "分析完成，等待审核" : "案例分析中"}</h2>
      <p>${escapeHtml(failed ? task.error_message || "请稍后重试。" : task.stage || "等待开始")}</p></div>
      <strong>${Number(task.progress || 0)}%</strong></div>
    <div class="progress-track"><span style="width:${Math.max(0, Math.min(100, Number(task.progress || 0)))}%"></span></div>
    <ol class="progress-steps">${stages}</ol>
    ${failureAction}
  </section>`;
}

export function caseCard(caseItem, statusPill) {
  const duration = caseItem.duration_seconds == null ? "时长未知" : `${Math.round(caseItem.duration_seconds)} 秒`;
  const source = caseItem.platform === "douyin" ? "抖音" : "视频来源";
  return `<article class="card case-card" data-case-status="${escapeHtml(caseItem.status)}">
    <div class="case-card-top"><h3>${escapeHtml(caseItem.title)}</h3>${statusPill(caseItem.status)}</div>
    <div class="case-meta"><span>${source} · ${escapeHtml(duration)}</span><span>${escapeHtml(caseItem.profile)}</span><span>${escapeHtml(caseItem.industry)}</span></div>
    ${caseItem.summary ? `<p class="case-summary">${escapeHtml(caseItem.summary)}</p>` : ""}
    <a class="inline-link" href="/cases/${encodeURIComponent(caseItem.case_id)}" data-route><span>查看案例</span><span aria-hidden="true">›</span></a>
  </article>`;
}

function paragraphList(values) {
  return (values || []).filter(Boolean).map((value) => `<p>${escapeHtml(value)}</p>`).join("");
}

export function caseReviewContent(detail, statusPill) {
  const development = paragraphList(detail.how_it_tells?.development);
  const reviewMedia = detail.review_media || {};
  const sourceUrl = reviewMedia.source_url || "";
  const mediaSurface = reviewMedia.local_available
    ? `<video controls playsinline preload="metadata" src="${escapeHtml(reviewMedia.local_url)}"></video>`
    : `<iframe class="douyin-review-player" src="${escapeHtml(reviewMedia.remote_embed_url)}" title="抖音原视频审核预览" loading="lazy" allowfullscreen></iframe>`;
  const sourceLink = sourceUrl
    ? `<a class="source-video-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">在抖音打开原视频</a>`
    : "";
  const cleanupNotice = reviewMedia.local_available
    ? ""
    : `<div class="transient-media-notice"><strong>原始媒体已在分析完成后自动清理。</strong><span>请根据抖音原始来源确认分析结果；如原视频已无法访问，请勿批准该案例。</span></div>`;
  const shots = (detail.full_breakdown?.shots || []).map((shot) => `<article class="breakdown-shot">
    <div class="shot-time">画面 ${shot.number} · ${Number(shot.start || 0).toFixed(1)}–${Number(shot.end || 0).toFixed(1)} 秒</div>
    ${shot.narration ? `<p><strong>口播</strong>${escapeHtml(shot.narration)}</p>` : ""}
    ${shot.scene ? `<p><strong>画面</strong>${escapeHtml(shot.scene)}</p>` : ""}
    ${shot.onscreen_text ? `<p><strong>画面文字</strong>${escapeHtml(shot.onscreen_text)}</p>` : ""}
    ${shot.function ? `<p><strong>作用</strong>${escapeHtml(shot.function)}</p>` : ""}
  </article>`).join("");
  return `<main class="page case-review-page">
    <div class="case-review-heading"><a class="back-link" href="/cases" data-route>← 返回案例库</a><div>${statusPill(detail.status)}</div></div>
    <section class="review-layout">
      <div class="review-primary">
        <section class="card video-card">
          ${mediaSurface}
          <div class="video-meta"><h1>${escapeHtml(detail.title)}</h1>
            <p>${detail.platform === "douyin" ? "抖音" : "视频来源"} · ${detail.duration_seconds == null ? "时长未知" : `${Math.round(detail.duration_seconds)} 秒`}</p>
            ${detail.description ? `<p>${escapeHtml(detail.description)}</p>` : ""}
            ${sourceLink}
          </div>
        </section>
        ${cleanupNotice}
        <div class="rights-banner"><strong>案例仅用于内部结构研究。</strong><span>批准入库不代表原视频素材可以用于客户生产。</span></div>
        <section class="card review-section"><h2>这个视频在讲什么</h2>
          ${detail.what_it_says?.topic ? `<div class="review-row"><span>内容主题</span><p>${escapeHtml(detail.what_it_says.topic)}</p></div>` : ""}
          ${detail.what_it_says?.core_expression ? `<div class="review-row"><span>核心表达</span><p>${escapeHtml(detail.what_it_says.core_expression)}</p></div>` : ""}
        </section>
        <section class="card review-section"><h2>它是怎么讲的</h2>
          ${detail.how_it_tells?.opening ? `<div class="review-row"><span>开头</span><p>${escapeHtml(detail.how_it_tells.opening)}</p></div>` : ""}
          ${development ? `<div class="review-row"><span>中段</span><div>${development}</div></div>` : ""}
          ${detail.how_it_tells?.ending ? `<div class="review-row"><span>结尾</span><p>${escapeHtml(detail.how_it_tells.ending)}</p></div>` : ""}
        </section>
        <section class="card review-section"><h2>值得学习的结构</h2>${paragraphList(detail.reusable_observations)}</section>
        <details class="card full-breakdown"><summary>查看完整拆解 <span>口播与画面逐段对照</span></summary>
          <div class="breakdown-body">${detail.full_breakdown?.narration ? `<section><h3>完整口播</h3><p class="narration-text">${escapeHtml(detail.full_breakdown.narration)}</p></section>` : ""}
          <section><h3>画面拆解</h3><div class="breakdown-list">${shots}</div></section></div>
        </details>
      </div>
      <aside class="review-aside"><section class="card review-decision"><h2>人工审核</h2>
        ${detail.review?.approved ? `<div class="approved-message"><strong>已进入案例库</strong><p>结构研究已批准；原视频素材使用权没有改变。</p></div>` : `<p>请对照原视频确认内容理解、叙事顺序与画面拆解是否可靠。</p>
          <button class="btn btn-primary btn-wide" type="button" data-review-action="approve">批准入库</button>
          <button class="btn btn-secondary btn-wide" type="button" data-review-action="reanalyze">退回重新分析</button>
          <button class="btn btn-quiet btn-wide danger-text" type="button" data-review-action="reject">不收录</button>`}
      </section></aside>
    </section>
  </main>`;
}
