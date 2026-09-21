import { escapeHtml } from "./case-components.js";

export const SPEAKER_PROGRESS_STAGES = [
  ["保存出镜人资料", 20],
  ["整理经历与职责", 55],
  ["提取表达范围", 75],
  ["检查信息完整度", 90],
  ["准备确认内容", 99],
];

const FIELD_LABELS = {
  public_display_name: "出镜人姓名",
  public_role: "公开身份",
  speaker_role_facts: "本人职责 / 实践",
  first_person_allowed_topics: "可以第一人称讲",
  first_person_forbidden_claims: "额外明确限制",
  role_scope_constraints: "角色边界",
  unknown_facts: "暂时未知",
};

const TYPE_LABELS = {
  owner_founder: "店主 / 创始人",
  frontline_expert: "一线专业人员",
  brand: "品牌角色",
  generic: "其他出镜人",
};

export function speakerFieldLabel(field) {
  return FIELD_LABELS[field] || field;
}

export function speakerTypeLabel(type) {
  return TYPE_LABELS[type] || type || "未分类";
}

export function speakerStatusPill(status) {
  const values = {
    approved: ["已确认", "pill-approved"],
    fact_review_required: ["信息待确认", "pill-review"],
    persona_review_required: ["档案待确认", "pill-review"],
    analyzing: ["分析中", "pill-review"],
    analysis_pending: ["待分析", "pill-review"],
    pending_customer_profile: ["待客户档案确认", "pill-review"],
    needs_more_info: ["需补充", "pill-review"],
    failed: ["分析失败", "pill-failed"],
    draft: ["未完成", "pill-archived"],
  };

  const [label, className] =
    values[status] || ["待处理", "pill-archived"];

  return `<span class="pill ${className}">${escapeHtml(label)}</span>`;
}

function currentStageIndex(task) {
  const exact = SPEAKER_PROGRESS_STAGES.findIndex(
    ([label]) => label === task.stage,
  );

  if (exact >= 0) return exact;

  const next = SPEAKER_PROGRESS_STAGES.findIndex(
    ([, threshold]) => Number(task.progress || 0) < threshold,
  );

  return next < 0
    ? SPEAKER_PROGRESS_STAGES.length - 1
    : next;
}

export function speakerProgressPanel(task, { compact = false } = {}) {
  const failed = task.status === "failed";
  const waiting = task.status === "awaiting_review";
  const completed = task.status === "completed";
  const terminal = waiting || completed;

  const activeIndex = currentStageIndex(task);

  const stages = SPEAKER_PROGRESS_STAGES.map(
    ([label, threshold], index) => {
      const done =
        terminal || Number(task.progress || 0) >= threshold;

      const active =
        !failed &&
        !done &&
        index === activeIndex;

      return `
        <li class="progress-step ${done ? "done" : ""} ${active ? "active" : ""}">
          <span class="progress-marker">
            ${done ? "✓" : active ? "→" : "○"}
          </span>
          <span>${escapeHtml(label)}</span>
        </li>`;
    },
  ).join("");

  let title = "正在整理出镜人信息";

  if (failed) title = "出镜人信息分析未完成";
  else if (waiting) title = "出镜人信息已经整理好";
  else if (completed) title = "出镜人信息已确认";

  const footer = failed
    ? `
      <div class="next-action">
        <strong>分析没有完成</strong>
        <span>${escapeHtml(
          task.error_message || "请稍后重新处理。",
        )}</span>
      </div>`
    : `
      <p class="progress-note">
        你可以离开当前页面，任务会在后台继续运行。
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

export function speakerCard(speaker, businessId) {
  return `
    <a
      class="speaker-row"
      href="/customers/${encodeURIComponent(
        businessId,
      )}/speakers/${encodeURIComponent(speaker.speaker_id)}"
      data-route
    >
      <div class="speaker-row-main">
        <div>
          <strong>${escapeHtml(speaker.display_name)}</strong>
          <p>
            ${escapeHtml(speaker.public_role)}
          </p>
        </div>
      </div>
      <div class="speaker-row-end">
        ${speakerStatusPill(speaker.status)}
        <span class="case-chevron" aria-hidden="true">›</span>
      </div>
    </a>`;
}
