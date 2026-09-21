import { escapeHtml } from "./case-components.js";

function hasDisplayValue(value) {
  if (value == null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function valueLabel(value) {
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value ?? "");
}

function objectRows(value, labelFor, depth = 0) {
  return Object.entries(value || {})
    .filter(([, item]) => hasDisplayValue(item))
    .map(([key, item]) => {
      const label = labelFor?.(key) || key.replaceAll("_", " ");
      return `
        <div class="profile-object-row">
          <dt>${escapeHtml(label)}</dt>
          <dd>${formatProfileValue(item, { labelFor, depth: depth + 1 })}</dd>
        </div>`;
    })
    .join("");
}

export function formatProfileValue(
  value,
  { labelFor, depth = 0 } = {},
) {
  if (!hasDisplayValue(value)) {
    return `<span class="muted-value">暂未填写</span>`;
  }

  if (Array.isArray(value)) {
    const simple = value.every(
      (item) => item == null || typeof item !== "object",
    );
    if (simple) {
      return `<ul class="profile-value-list">${value
        .map((item) => `<li>${escapeHtml(valueLabel(item))}</li>`)
        .join("")}</ul>`;
    }
    return `
      <details class="profile-detail-disclosure">
        <summary>查看详细信息</summary>
        <div class="profile-detail-content">
          ${value
            .map(
              (item, index) => `
                <div class="profile-detail-item">
                  <strong>第 ${index + 1} 项</strong>
                  ${
                    item && typeof item === "object"
                      ? `<dl class="profile-object-list">${objectRows(
                          item,
                          labelFor,
                          depth + 1,
                        )}</dl>`
                      : `<p>${escapeHtml(valueLabel(item))}</p>`
                  }
                </div>`,
            )
            .join("")}
        </div>
      </details>`;
  }

  if (typeof value === "object") {
    const simple = Object.values(value).every(
      (item) => item == null || typeof item !== "object",
    );
    const rows = objectRows(value, labelFor, depth);
    if (simple && depth < 1) {
      return `<dl class="profile-object-list">${rows}</dl>`;
    }
    return `
      <details class="profile-detail-disclosure">
        <summary>查看详细信息</summary>
        <dl class="profile-object-list profile-detail-content">${rows}</dl>
      </details>`;
  }

  return `<p class="profile-value-text">${escapeHtml(valueLabel(value))}</p>`;
}

export function ProfileRow({ label, value, labelFor } = {}) {
  if (!hasDisplayValue(value)) return "";
  return `
    <div class="profile-row">
      <dt>${escapeHtml(label)}</dt>
      <dd>${formatProfileValue(value, { labelFor })}</dd>
    </div>`;
}

export function ProfileSection({ title, description = "", rows = [] } = {}) {
  const content = rows.filter(Boolean).join("");
  if (!content) return "";
  return `
    <section class="profile-section">
      <div class="profile-section-heading">
        <h2>${escapeHtml(title)}</h2>
        ${description ? `<p>${escapeHtml(description)}</p>` : ""}
      </div>
      <dl class="profile-rows">${content}</dl>
    </section>`;
}

export function ProfileSummary(items = []) {
  return `
    <div class="profile-summary">
      ${items
        .filter((item) => item && item.value != null)
        .map(
          (item) => `
            <div class="profile-summary-item">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(item.value)}</strong>
              ${item.note ? `<p>${escapeHtml(item.note)}</p>` : ""}
            </div>`,
        )
        .join("")}
    </div>`;
}

export function ProfileTabs(items, active) {
  return `
    <nav class="profile-tabs" aria-label="客户详情导航">
      ${items
        .map(
          (item) => `
            <a
              class="profile-tab ${item.id === active ? "active" : ""}"
              href="#${encodeURIComponent(item.id)}"
              data-profile-tab="${escapeHtml(item.id)}"
              ${item.id === active ? 'aria-current="page"' : ""}
            >${escapeHtml(item.label)}</a>`,
        )
        .join("")}
    </nav>`;
}

export function EvidenceDisclosure(excerpt) {
  if (!String(excerpt || "").trim()) return "";
  return `
    <details class="evidence-disclosure">
      <summary>查看依据</summary>
      <p>${escapeHtml(excerpt)}</p>
    </details>`;
}

export function DecisionControl({ namespace = "profile" } = {}) {
  return `
    <div class="decision-control" role="group" aria-label="确认方式">
      <button class="decision-option" type="button" data-review-choice="reject" data-review-namespace="${escapeHtml(namespace)}">不采用</button>
      <button class="decision-option" type="button" data-review-choice="edit" data-review-namespace="${escapeHtml(namespace)}">修改</button>
      <button class="decision-option decision-confirm" type="button" data-review-choice="approve" data-review-namespace="${escapeHtml(namespace)}">确认</button>
    </div>`;
}

export function ReviewRow({ candidate, label, namespace, editableValue } = {}) {
  return `
    <article class="review-list-row" data-review-row="${escapeHtml(candidate.candidate_id)}">
      <div class="review-list-heading">
        <strong>${escapeHtml(label)}</strong>
        <span class="pill pill-review">需要确认</span>
      </div>
      <div class="review-list-value">${formatProfileValue(candidate.value)}</div>
      ${EvidenceDisclosure(candidate.source_excerpt)}
      ${DecisionControl({ namespace })}
      <div class="review-edit-panel" hidden>
        <label>修改后的信息</label>
        <textarea rows="4">${escapeHtml(editableValue)}</textarea>
        <span>列表内容请一行填写一项。</span>
      </div>
    </article>`;
}

export function ReviewList({ items, labelFor, namespace, editableValueFor } = {}) {
  return `
    <div class="review-list">
      ${(items || [])
        .map((candidate) =>
          ReviewRow({
            candidate,
            label: labelFor(candidate.field),
            namespace,
            editableValue: editableValueFor(candidate.value),
          }),
        )
        .join("")}
    </div>`;
}

export function bindDecisionControls({ root = document, submitSelector } = {}) {
  const rows = [...root.querySelectorAll("[data-review-row]")];
  const submitButton = root.querySelector(submitSelector);
  const progress = root.querySelector("[data-review-progress]");

  const update = () => {
    const completed = rows.filter((row) => row.dataset.decision).length;
    if (progress) progress.textContent = `已确认 ${completed} / ${rows.length}`;
    if (submitButton) submitButton.disabled = completed !== rows.length;
  };

  rows.forEach((row) => {
    row.querySelectorAll("[data-review-choice]").forEach((button) => {
      button.addEventListener("click", () => {
        row.dataset.decision = button.dataset.reviewChoice;
        row.querySelectorAll("[data-review-choice]").forEach((item) => {
          item.classList.toggle("active", item === button);
        });
        const edit = row.querySelector(".review-edit-panel");
        edit.hidden = button.dataset.reviewChoice !== "edit";
        if (!edit.hidden) edit.querySelector("textarea")?.focus();
        update();
      });
    });
  });

  update();
  return rows;
}

export function NeedsInfoState({
  title = "还缺少一些关键信息",
  description = "补充后可以重新整理档案。",
  items = [],
  primaryHref,
  primaryLabel,
  actionButton,
  actionLabel,
  secondaryHref,
  secondaryLabel = "稍后处理",
} = {}) {
  return `
    <section class="panel needs-info-state">
      <span class="state-icon state-icon-warning" aria-hidden="true">!</span>
      <div>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(description)}</p>
        ${
          items.length
            ? `<div class="needs-info-list"><span>缺少：</span><ul>${items
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("")}</ul></div>`
            : ""
        }
        <div class="needs-info-actions">
          ${
            primaryHref
              ? `<a class="btn btn-primary" href="${escapeHtml(primaryHref)}" data-route>${escapeHtml(primaryLabel)}</a>`
              : ""
          }
          ${
            actionButton
              ? `<button class="btn btn-secondary" type="button" data-needs-info-action="${escapeHtml(actionButton)}">${escapeHtml(actionLabel)}</button>`
              : ""
          }
          ${
            secondaryHref
              ? `<a class="btn btn-secondary" href="${escapeHtml(secondaryHref)}" data-route>${escapeHtml(secondaryLabel)}</a>`
              : ""
          }
        </div>
      </div>
    </section>`;
}
