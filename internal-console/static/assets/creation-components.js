import { escapeHtml } from "./case-components.js?v=productized-stage1-5";

const INTERNAL_LANGUAGE = /(?:authority|canonical|artifact|generation request|request id|profile|source planning handoff|generation source plan|content plan|script generation|generation batch|content ledger|semantic ledger|approved projection|historical exposure|presentation history|approved pattern|eligible cases|coverage code|central claim|human review|human revision|known fact|authority field|cross-profile repurpose|remote model|local model|[A-Z][A-Z0-9_]{3,})/i;

export function safeCreationMessage(value, fallback) {
  const text = String(value || "").trim();
  if (!text || INTERNAL_LANGUAGE.test(text)) return fallback;
  return text;
}

export function CreationHeader({ title, description = "", eyebrow = "" } = {}) {
  return `
    <header class="creation-header">
      ${eyebrow ? `<span class="creation-eyebrow">${escapeHtml(eyebrow)}</span>` : ""}
      <h2>${escapeHtml(title || "继续创作")}</h2>
      ${description ? `<p>${escapeHtml(description)}</p>` : ""}
    </header>`;
}

export function CreationStepper({ steps = [], currentIndex = 0 } = {}) {
  return `
    <ol class="creation-stepper" aria-label="创作进度">
      ${steps.map((label, index) => `
        <li class="creation-step ${index < currentIndex ? "done" : index === currentIndex ? "current" : ""}">
          <span>${index < currentIndex ? "✓" : index + 1}</span>
          <strong>${escapeHtml(label)}</strong>
        </li>`).join("")}
    </ol>`;
}

export function CreationSummary(items = []) {
  const visible = items.filter((item) => item?.value !== undefined && item?.value !== null && String(item.value).trim() !== "");
  if (!visible.length) return "";
  return `
    <dl class="creation-summary">
      ${visible.map((item) => `
        <div class="creation-summary-row ${item.wide ? "wide" : ""}">
          <dt>${escapeHtml(item.label || "")}</dt>
          <dd>${escapeHtml(item.value)}</dd>
        </div>`).join("")}
    </dl>`;
}

export function CreationMetricRow(items = []) {
  return `
    <dl class="creation-metric-row">
      ${items.map((item) => `
        <div>
          <dt>${escapeHtml(item.label || "")}</dt>
          <dd>${escapeHtml(item.value ?? "—")}</dd>
        </div>`).join("")}
    </dl>`;
}

export function CreationState({ tone = "neutral", eyebrow = "", title, body = "", content = "", actions = "", className = "" } = {}) {
  return `
    <section class="work-surface creation-state creation-state-${escapeHtml(tone)} ${escapeHtml(className)}">
      ${CreationHeader({ title, description: body, eyebrow })}
      ${content}
      ${actions ? `<div class="creation-actions">${actions}</div>` : ""}
    </section>`;
}

export function TopicRow({ index, title, audienceNeed = "", coreExpression = "" } = {}) {
  return `
    <article class="topic-row">
      <span class="topic-index">${Number(index) || 1}</span>
      <div class="topic-copy">
        <h3>${escapeHtml(title || "待命名选题")}</h3>
        ${audienceNeed ? `<p><span>用户关心</span>${escapeHtml(audienceNeed)}</p>` : ""}
        ${coreExpression ? `<p class="topic-core"><span>核心表达</span>${escapeHtml(coreExpression)}</p>` : ""}
      </div>
    </article>`;
}

export function TopicList(items = []) {
  return `
    <div class="topic-list">
      ${items.map((item, index) => TopicRow({ ...item, index: index + 1 })).join("")}
    </div>`;
}

export function CreationEvidenceDisclosure({ label = "查看生成依据", rows = [] } = {}) {
  const visible = rows.filter((row) => row?.value !== undefined && row?.value !== null && String(row.value).trim() !== "");
  if (!visible.length) return "";
  return `
    <details class="creation-evidence">
      <summary>${escapeHtml(label)}</summary>
      <dl>
        ${visible.map((row) => `
          <div>
            <dt>${escapeHtml(row.label || "")}</dt>
            <dd>${escapeHtml(row.value)}</dd>
          </div>`).join("")}
      </dl>
    </details>`;
}

export function ContentDecisionControl({ namespace, itemId, rejectDisabled = false, rejectReason = "" } = {}) {
  const name = `${namespace || "content"}-${itemId || "item"}`;
  return `
    <div class="content-decision-control">
      <label>
        <input type="radio" name="${escapeHtml(name)}" value="approved" data-content-decision>
        <span>通过</span>
      </label>
      <label>
        <input type="radio" name="${escapeHtml(name)}" value="revised" data-content-decision>
        <span>修改</span>
      </label>
      <label class="decision-reject ${rejectDisabled ? "disabled" : ""}">
        <input type="radio" name="${escapeHtml(name)}" value="rejected" data-content-decision ${rejectDisabled ? "disabled" : ""}>
        <span>不采用</span>
      </label>
      ${rejectDisabled && rejectReason ? `<p class="decision-constraint">${escapeHtml(rejectReason)}</p>` : ""}
    </div>`;
}

export function ContentReviewItem({
  namespace,
  itemId,
  index,
  eyebrow = "",
  title,
  body = "",
  bodyLabel = "文案",
  coreExpression = "",
  flags = [],
  evidenceRows = [],
  editorMode = "mix",
  rejectDisabled = false,
  rejectReason = "",
} = {}) {
  const warnings = (flags || []).filter(Boolean);
  return `
    <article class="content-review-item" data-content-review-item data-item-id="${escapeHtml(itemId || "")}">
      <div class="content-review-heading">
        <span>${Number(index) || 1}</span>
        <div>
          ${eyebrow ? `<small>${escapeHtml(eyebrow)}</small>` : ""}
          <h3>${escapeHtml(title || "待审核内容")}</h3>
        </div>
      </div>
      ${body ? `
        <div class="content-review-copy">
          <span>${escapeHtml(bodyLabel)}</span>
          <p>${escapeHtml(body)}</p>
        </div>` : ""}
      ${coreExpression ? `<p class="content-core-expression"><span>核心表达</span>${escapeHtml(coreExpression)}</p>` : ""}
      ${warnings.length ? `
        <div class="content-review-warning">
          <strong>需要注意</strong>
          ${warnings.map((flag) => `<p>${escapeHtml(flag)}</p>`).join("")}
        </div>` : ""}
      ${CreationEvidenceDisclosure({ rows: evidenceRows })}
      ${ContentDecisionControl({ namespace, itemId, rejectDisabled, rejectReason })}
      <div class="content-revision-editor" data-content-revision-editor hidden>
        <p>可以调整表达，不能新增未经确认的事实。</p>
        <div class="field">
          <label>标题</label>
          <input type="text" data-revised-title value="${escapeHtml(title || "")}">
        </div>
        ${editorMode === "mix" ? `
          <div class="field">
            <label>文案</label>
            <textarea rows="7" data-revised-body>${escapeHtml(body || "")}</textarea>
          </div>` : ""}
      </div>
      <details class="creation-note-disclosure">
        <summary>添加审核备注</summary>
        <div class="field">
          <label>审核备注（可选）</label>
          <input type="text" data-content-review-note placeholder="补充本次判断依据">
        </div>
      </details>
    </article>`;
}

export function ContentReviewList(items = []) {
  return `<div class="content-review-list">${items.join("")}</div>`;
}

export function ExportSummary(items = []) {
  return CreationSummary(items);
}

export function CreationCompletedState({ title = "已完成", description = "", summary = [], downloadHref = "", downloadLabel = "下载 Excel", secondaryHref = "/create", secondaryLabel = "开始新的创作" } = {}) {
  return CreationState({
    tone: "success",
    eyebrow: "创作完成",
    title,
    body: description,
    content: ExportSummary(summary),
    actions: `
      ${downloadHref ? `<a class="btn btn-primary" href="${escapeHtml(downloadHref)}">${escapeHtml(downloadLabel)}</a>` : ""}
      ${secondaryHref ? `<a class="btn btn-secondary" href="${escapeHtml(secondaryHref)}" data-route>${escapeHtml(secondaryLabel)}</a>` : ""}`,
    className: "creation-completed-state",
  });
}
