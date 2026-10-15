export function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

export const searchIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>';
const videoIcon = '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><rect x="5" y="5" width="22" height="22" rx="6"/><path d="m13 11 8 5-8 5z"/></svg>';

export function listEmpty(title, message) {
  return `<section class="list-empty"><span class="list-empty-symbol">${videoIcon}</span><h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p></section>`;
}

export function listSkeleton() {
  return `<div class="list-skeleton" aria-label="正在读取列表" role="status">${Array.from({length:4},()=>'<div class="list-skeleton-row"><span></span><div><i></i><i></i></div></div>').join("")}</div>`;
}

export function formatCaseDuration(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return "";
  if (value < 1) return "少于 1 秒";
  const seconds = Math.round(value), minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2,"0")}:${String(seconds % 60).padStart(2,"0")}`
    : `${String(minutes).padStart(2,"0")}:${String(seconds % 60).padStart(2,"0")}`;
}

export const caseStateLabels = {
  queued:"待解析", running:"解析中", needs_confirmation:"待分类核对", awaiting_review:"待审核",
  approved:"已收录", rejected:"未收录", failed:"解析失败", completed:"本次处理已结束", submitted:"投稿已记录", archived:"历史记录",
};

export function caseListCard(item, _statusPill, returnPath = "") {
  const shared = item.visibility === "shared";
  const href = item.href || `/cases/${encodeURIComponent(item.case_id)}${shared ? "?shared=1" : ""}`;
  const destination = href + (returnPath ? `${href.includes("?") ? "&" : "?"}return=${encodeURIComponent(returnPath)}` : "");
  const duration = formatCaseDuration(item.duration_seconds);
  const state = caseStateLabels[item.status] || "待处理";
  const cover = item.cover_url ? `<img src="${escapeHtml(item.cover_url)}" alt="" loading="lazy" decoding="async">` : "";
  return `<a class="case-library-card" href="${escapeHtml(destination)}" data-route data-case-status="${escapeHtml(item.status)}" data-case-id="${escapeHtml(item.case_id || "")}">
    <span class="case-card-cover">${cover}<span class="case-cover-placeholder" ${cover ? "hidden" : ""}>${videoIcon}<small>暂无封面</small></span>${duration ? `<span class="case-card-duration">${duration}</span>` : ""}</span>
    <span class="case-card-content"><span class="case-card-heading"><strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong>${shared ? "" : `<span class="list-status ${item.status === "failed" || item.status === "rejected" ? "list-status-attention" : ""}">${state}</span>`}</span>
      <span class="case-card-tags"><span>${escapeHtml(item.industry || "行业待确认")}</span><span class="case-type-label">${escapeHtml(item.video_type || "视频类型暂未标注")}</span></span>
      ${shared ? '<span class="case-card-hint">结构参考</span>' : `<span class="case-card-hint">${escapeHtml(item.failure_reason || item.review_reason || item.next_action || "查看案例")}</span>`}
    </span><span class="case-card-entry" aria-hidden="true">›</span>
  </a>`;
}
