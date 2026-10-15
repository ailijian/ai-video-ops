import { escapeHtml } from "./case-components.js";
import { formatProfileValue } from "./profile-components.js?v=productized-stage2-3";

export const CUSTOMER_PROGRESS_STAGES = [
  ["保存客户原始资料", 20],
  ["隐私检查", 35],
  ["正在整理客户业务信息", 68],
  ["正在查找可能的出镜人", 82],
  ["检查信息完整度", 90],
  ["准备确认内容", 99],
];

const FIELD_LABELS = {
  public_display_name: "客户名称",
  company_short_name: "简称",
  industry: "行业",
  years_in_business: "经营年限",
  service_area: "服务区域",
  location_public_area: "公开位置",
  primary_products_or_services: "主要产品 / 服务",
  secondary_products_or_services: "其他产品 / 服务",
  core_audience: "主要顾客",
  customer_use_cases: "顾客使用场景",
  customer_pains: "顾客问题",
  differentiators: "差异点",
  selection_reasons: "顾客选择理由",
  brand_story: "品牌故事",
  founder_or_operator_story: "经营者故事",
  important_turning_points: "重要经历",
  product_or_service_facts: "产品 / 服务事实",
  pricing_facts: "价格事实",
  included_service_facts: "包含服务",
  process_facts: "服务流程",
  service_process: "服务过程",
  service_time_facts: "服务时间",
  business_volume_fact: "业务量事实",
  time_efficiency_fact: "效率事实",
  authorized_customer_cases_or_feedback: "已授权顾客案例 / 反馈",
  values: "价值观",
  business_principles: "经营原则",
  beliefs: "经营观点",
  tone_preferences: "表达偏好",
  business_identity: "还缺少客户名称或明确的产品 / 服务信息",
  customer_use_context: "还缺少顾客或使用场景信息",
  production_bearing_facts: "还缺少可用于内容创作的真实业务信息",
  critical_constraints: "还有关键冲突或边界需要确认",
};

const LEGACY_BLOCKER_CAPABILITY = {
  public_display_name: "business_identity",
  company_short_name: "business_identity",
  industry: "business_identity",
  primary_products_or_services: "business_identity",
  core_audience: "customer_use_context",
  customer_use_cases: "customer_use_context",
  customer_pains: "customer_use_context",
  differentiators: "production_bearing_facts",
};

export function customerFieldLabel(field) {
  return FIELD_LABELS[field] || field;
}

export function customerReadinessGaps(blockers = []) {
  return [...new Set(blockers.map((field) => LEGACY_BLOCKER_CAPABILITY[field] || field))];
}

export function customerStatusPill(status) {
  const values = {
    approved: ["已确认", "pill-approved"],
    fact_review_required: ["信息待确认", "pill-review"],
    persona_review_required: ["档案待确认", "pill-review"],
    analyzing: ["分析中", "pill-review"],
    analysis_pending: ["待分析", "pill-review"],
    needs_more_info: ["需补充", "pill-review"],
    failed: ["分析失败", "pill-failed"],
    draft: ["未完成", "pill-archived"],
  };

  const [label, className] =
    values[status] || ["待处理", "pill-archived"];

  return `<span class="pill ${className}">${escapeHtml(label)}</span>`;
}

function stageIndex(task) {
  const exact = CUSTOMER_PROGRESS_STAGES.findIndex(
    ([label]) => label === task.stage,
  );

  if (exact >= 0) return exact;

  const next = CUSTOMER_PROGRESS_STAGES.findIndex(
    ([, threshold]) => Number(task.progress || 0) < threshold,
  );

  return next < 0
    ? CUSTOMER_PROGRESS_STAGES.length - 1
    : next;
}

export function customerProgressPanel(task, { compact = false } = {}) {
  const failed = task.status === "failed";
  const waiting = task.status === "awaiting_review";
  const completed = task.status === "completed";
  const terminal = waiting || completed;

  const active = stageIndex(task);

  const stages = CUSTOMER_PROGRESS_STAGES.map(
    ([label, threshold], index) => {
      const done =
        terminal || Number(task.progress || 0) >= threshold;

      const current =
        !failed && !done && index === active;

      return `
        <li class="progress-step ${done ? "done" : ""} ${current ? "active" : ""}">
          <span class="progress-marker">
            ${done ? "✓" : current ? "→" : "○"}
          </span>
          <span>${escapeHtml(label)}</span>
        </li>`;
    },
  ).join("");

  let title = "正在整理客户信息";

  if (failed) title = "客户信息分析未完成";
  else if (waiting) title = "信息已经整理好";
  else if (completed) title = "客户信息已确认";

  const footer = failed
    ? `<div class="next-action">
        <strong>分析没有完成</strong>
        <span>${escapeHtml(
          task.error_message || "请检查任务后重新处理。",
        )}</span>
      </div>`
    : `<p class="progress-note">
        你可以离开这个页面，任务会在后台继续运行。
      </p>`;

  return `
    <section class="task-progress profile-progress ${compact ? "compact" : ""}">
      <div class="task-progress-head">
        <div>
          <h2>${title}</h2>
          <p>${escapeHtml(task.stage || "等待开始")}</p>
        </div>
      </div>
      <p class="field-hint">按已保存的处理阶段显示，不预估剩余时间。</p>

      <ol class="progress-steps">${stages}</ol>
      ${footer}
    </section>`;
}

export function displayFactValue(value) {
  return formatProfileValue(value, { labelFor: customerFieldLabel });
}

export function editableFactValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join("\n");
  }

  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }

  return String(value ?? "");
}

export function parseEditedFactValue(originalValue, text) {
  const normalized = String(text || "").trim();

  if (!normalized) {
    throw new Error("修改后的内容不能为空。");
  }

  if (Array.isArray(originalValue)) {
    const values = normalized
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);

    if (!values.length) {
      throw new Error("修改后的内容不能为空。");
    }

    return values;
  }

  if (originalValue && typeof originalValue === "object") {
    try {
      return JSON.parse(normalized);
    } catch {
      throw new Error("这条信息需要保持有效的 JSON 结构。");
    }
  }

  if (typeof originalValue === "number") {
    const number = Number(normalized);
    if (!Number.isFinite(number)) throw new Error("请输入有效数字。");
    return number;
  }

  return normalized;
}

export function customerCard(customer) {
  const operation = customer.operation || {};
  const speaker = customer.speaker;
  const records = customer.creation_record_count === null || customer.creation_record_count === undefined ? "创作记录暂不可读"
    : customer.creation_record_count ? `${customer.creation_record_count} 个创作记录` : "暂无创作记录";
  const pending = customer.pending_count === null || customer.pending_count === undefined ? "待办暂不可读" : customer.pending_count ? `${customer.pending_count} 项待处理` : "";
  return `
    <article class="customer-operation-card" data-customer-id="${escapeHtml(customer.business_id)}">
      <div class="customer-operation-heading">
        <span class="customer-symbol" aria-hidden="true">${escapeHtml(Array.from(customer.display_name || "客")[0])}</span>
        <div class="customer-operation-identity">
          <div class="customer-title-line"><a class="customer-operation-name" href="${escapeHtml(customer.detail_url)}" data-route title="${escapeHtml(customer.display_name)}">${escapeHtml(customer.display_name)}</a><span class="list-status ${operation.kind === "ready" ? "list-status-ready" : operation.kind === "error" || operation.kind === "blocked" ? "list-status-attention" : ""}">${escapeHtml(operation.status || "待核对")}</span></div>
          <p>${escapeHtml(customer.industry || "行业待确认")}${customer.region ? ` · ${escapeHtml(customer.region)}` : ""}</p>
        </div>
      </div>
      <div class="customer-operation-speaker">${speaker
        ? `<span><strong>${escapeHtml(speaker.display_name)}${speaker.public_role ? `<em> · ${escapeHtml(speaker.public_role)}</em>` : ""}</strong><small>${customer.approved_speaker_count == null ? "出镜人数量暂不可读" : `${customer.approved_speaker_count} 位已确认出镜人`}</small></span>`
        : `<span class="list-muted">${customer.approved_speaker_count === null ? "出镜人状态暂时无法读取" : "尚无已批准出镜人"}</span>`}
      </div>
      <div class="customer-operation-progress"><span class="customer-operation-stats">${escapeHtml(records)}${pending ? ` · ${escapeHtml(pending)}` : ""}</span>${operation.note && operation.note !== operation.status && operation.note !== operation.primary?.label ? `<p class="customer-operation-note">${escapeHtml(operation.note)}</p>` : ""}</div>
      <div class="customer-operation-actions">
        <a class="btn btn-primary btn-compact" href="${escapeHtml(operation.primary?.url || customer.detail_url)}" data-route>${escapeHtml(operation.primary?.label || "查看客户")}</a>
        <a class="section-link" href="${escapeHtml(operation.secondary?.url || `${customer.detail_url}/content`)}" data-route>查看作品记录</a>
      </div>
    </article>`;
}
