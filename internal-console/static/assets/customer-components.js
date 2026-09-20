import { escapeHtml } from "./case-components.js";
import { formatProfileValue } from "./profile-components.js?v=productized-stage2-3";

export const CUSTOMER_PROGRESS_STAGES = [
  ["保存客户资料", 20],
  ["整理公开信息", 35],
  ["提取客户信息", 75],
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
};

export function customerFieldLabel(field) {
  return FIELD_LABELS[field] || field;
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
        <strong>${Number(task.progress || 0)}%</strong>
      </div>

      <div class="progress-track">
        <span style="width:${Math.max(
          0,
          Math.min(100, Number(task.progress || 0)),
        )}%"></span>
      </div>

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
  return `
    <a
      class="customer-row"
      href="/customers/${encodeURIComponent(customer.business_id)}"
      data-route
    >
      <div class="customer-row-main">
        <div>
          <strong>${escapeHtml(customer.display_name)}</strong>
          <p>${escapeHtml(customer.industry || "行业待确认")}</p>
        </div>
      </div>
      <div class="customer-row-end">
        <span class="customer-speaker-count">${Number(customer.speaker_count || 0)} 位出镜人</span>
        ${customerStatusPill(customer.status)}
        <span class="case-chevron" aria-hidden="true">›</span>
      </div>
    </a>`;
}
