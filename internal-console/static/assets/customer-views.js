import {enhanceReviewDisclosures,bindReviewReturnLinks} from './customer-review-presentation.mjs?v=customer-speaker-scope-1';
import { batchHistoryMarkup } from './creation-batch-view.mjs?v=cbux1-b234-3';
import { bindFinalCustomerConfirmation } from "./customer-final-confirmation.mjs?v=customer-speaker-scope-1";
import {bindCustomerSpeakerConfirmation} from './customer-speaker-confirmation.mjs?v=customer-speaker-scope-1';
import { amendmentPanel, bindAmendment, bindingReviewPanel, mountRecovery } from "./review-workflow-ui.mjs?v=profile-correction-ui-1";
import {
  customerCard,
  customerConstraintPanel,
  customerFieldLabel,
  customerProgressPanel,
  customerStatusPill,
  editableFactValue,
  parseEditedFactValue,
} from "./customer-components.js?v=cbux1-b234-3";
import {
  speakerCard,
} from "./speaker-components.js?v=flow-closure-2";

import { escapeHtml } from "./case-components.js?v=flow-closure-2";
import { formatConsoleTime, accountLabel } from "./ui-format.mjs?v=ui-1";
import { listEmpty, searchIcon, listSkeleton } from "./list-ui.mjs?v=flow-closure-2";
import {bindLegacyScope} from "./legacy-scope-ui.mjs?v=legacy-scope-1";
import {
  ProfileRow,
  ProfileSection,
  ProfileSummary,
  ProfileTabs,
  EvidenceDisclosure,
  formatProfileValue,
} from "./profile-components.js?v=productized-stage2-3";
import { startTaskPolling } from "./task-progress.js";
import {watchCustomerSpeakerTasks} from './customer-speaker-status.mjs?v=speaker-status-sync-1';
import { ContentOperationsPanel } from "./content-operations-views.js?v=cbux1-b234-3";

const CUSTOMER_PROFILE_GROUPS = [
  {
    title: "基础信息",
    fields: [
      "public_display_name",
      "company_short_name",
      "industry",
      "years_in_business",
      "service_area",
      "location_public_area",
    ],
  },
  {
    title: "产品与服务",
    fields: [
      "primary_products_or_services",
      "secondary_products_or_services",
      "product_or_service_facts",
      "pricing_facts",
      "included_service_facts",
      "process_facts",
      "service_process",
      "service_time_facts",
    ],
  },
  {
    title: "客户与场景",
    fields: [
      "core_audience",
      "customer_use_cases",
      "customer_pains",
      "differentiators",
      "selection_reasons",
      "authorized_customer_cases_or_feedback",
    ],
  },
  {
    title: "经营与品牌",
    fields: [
      "brand_story",
      "founder_or_operator_story",
      "important_turning_points",
      "business_volume_fact",
      "time_efficiency_fact",
      "values",
      "business_principles",
      "beliefs",
      "tone_preferences",
    ],
  },
];

import { CASE_INDUSTRIES as CUSTOMER_INDUSTRIES } from "./case-industry.mjs?v=industry-2";
export { CUSTOMER_INDUSTRIES };

export function intakeSteps(active, amendment = false) {
  return `<ol class="intake-steps" aria-label="资料整理步骤">${(amendment ? ["提供更正依据", "保留原审核来源", "检查并确认"] : ["提供资料", "AI 自动整理", "检查并确认"]).map((label, index) => `<li ${active === index + 1 ? 'aria-current="step"' : ""}><span>${index + 1}</span>${label}</li>`).join("")}</ol>`;
}

function auditNote(detail) {
  const reviewer = accountLabel(detail.reviewed_by?.phone);
  const time = formatConsoleTime(detail.fact_review?.created_at || detail.fact_review?.reviewed_at);
  return reviewer ? `<p class="field-hint">信息审核：${escapeHtml(reviewer)}${time ? ` · ${escapeHtml(time)}` : ""}。客户与人物分别留存审核记录，素材使用权仍须单独检查。</p>` : "";
}

export function customerReviewGroups(items) {
  const groups = [
    ["客户是谁", ["public_display_name", "company_short_name", "industry", "years_in_business", "service_area", "location_public_area"]],
    ["主要产品与服务", ["primary_products_or_services", "secondary_products_or_services", "product_or_service_facts", "pricing_facts", "included_service_facts"]],
    ["客户通常遇到什么问题", ["core_audience", "customer_use_cases", "customer_pains", "selection_reasons"]],
    ["真实业务信息", ["differentiators", "brand_story", "founder_or_operator_story", "important_turning_points", "process_facts", "service_process", "service_time_facts", "business_volume_fact", "time_efficiency_fact", "authorized_customer_cases_or_feedback"]],
    ["重要限制", ["values", "business_principles", "beliefs", "tone_preferences"]],
  ];
  const assigned = new Set(groups.flatMap(([, fields]) => fields));
  groups.push(["其他待确认信息", items.filter(item => !assigned.has(item.field)).map(item => item.field)]);
  return groups.map(([title, fields]) => {
    const members = items.filter(item => fields.includes(item.field));
    return members.length ? `<section class="customer-review-group"><h3>${title}</h3>${members.map(item => `
      <article class="customer-fact-card ${item.default_review_selection ? "" : "is-exception"}" data-review-row="${escapeHtml(item.candidate_id)}" data-decision="${item.default_review_selection || ""}">
        <div class="customer-fact-heading"><h4>${escapeHtml(customerFieldLabel(item.field))}</h4><span data-fact-status>${item.default_review_selection ? "待统一确认" : "需要重点核对"}</span></div>
        <div class="customer-fact-value" data-fact-value>${formatProfileValue(item.value)}</div>
        ${item.review_exception_reason ? `<p class="field-hint">${escapeHtml(item.review_exception_reason)}</p>` : ""}
        <div class="customer-fact-footer">${EvidenceDisclosure(item.source_excerpt)}
        <div class="customer-fact-tools">
          <button type="button" class="btn btn-secondary" data-review-choice="approve" ${item.default_review_selection ? "hidden" : ""}>采用此信息</button>
          <details class="customer-fact-options"><summary aria-label="调整${escapeHtml(customerFieldLabel(item.field))}">调整</summary>
            <div class="customer-fact-actions">
              <button type="button" class="btn btn-ghost" data-review-choice="edit">修改</button>
              <button type="button" class="btn btn-ghost" data-review-choice="reject">不采用</button>
              <button type="button" class="btn btn-ghost" data-review-choice="">暂不处理</button>
            </div>
          </details>
        </div>
        </div>
        <div class="review-edit-panel" hidden><label>修改后的信息<textarea aria-label="修改${escapeHtml(customerFieldLabel(item.field))}" rows="3">${escapeHtml(editableFactValue(item.value))}</textarea></label><p class="field-hint">修改后的内容将在下方预览，提交后形成真实人审记录。</p></div>
      </article>`).join("")}</section>` : "";
  }).join("");
}

const CONSTRAINT_PRESENTATION = {
  publication_prohibition: ["宣传禁用", "确认后，相关表述会持续限制后续内容。"],
  unverified_claim: ["待核实宣传", "未经核实的宣传不能用于内容，可以明确排除或保留待核实。"],
  identity_conflict: ["身份与主体冲突", "涉及客户主体，需要准确来源和明确核对结果才能解除。"],
  conditional_fact: ["适用条件", "确认后，后续内容需保留原有适用条件。"],
};
const CONSTRAINT_DEFAULTS = {publication_prohibition: "confirm", unverified_claim: "defer", identity_conflict: "defer", conditional_fact: "confirm"};
const CONSTRAINT_ACTION_LABELS = {confirm: "按上述限制使用内容", exclude: "明确排除此项宣传", defer: "需要进一步核实，相关内容暂不使用", dismiss: "纠正识别", resolve: "补充核实资料，解决此项冲突"};

export function constraintReviewImpact(type, decision) {
  if (!decision) return "本次暂未处理，仍需核对后才能完成新客户档案批准。";
  if (["dismiss", "resolve"].includes(decision)) return "请补充准确原文和核对说明，保存时仍须通过正式校验。";
  if (type === "identity_conflict") return "主体冲突尚未解决，保存进度不会解除相关创作限制。";
  if (decision === "defer") return "保存后继续待核实，新客户档案暂不能批准。";
  if (decision === "exclude") return "此项宣传不用于创作，不表示它已核实；其余资料仍按原流程审核。";
  if (type === "conditional_fact") return "后续内容必须保留原有适用条件。";
  if (type === "publication_prohibition") return "相关表述会继续禁用，独立业务事实仍按原流程审核。";
  return "保留当前限制，后续仍需检查档案批准和内容使用条件。";
}

export function customerConstraintReview(detail) {
  const candidates = detail.constraint_candidates || [];
  const pendingCount = candidates.filter(item => !item.human_review).length;
  if (!candidates.length) return "";
  return `<section class="work-surface review-surface customer-constraint-surface" id="customer-review-constraints">
    <div class="review-surface-heading">
      <h2>重要限制与待核实内容 <span class="customer-section-count">${pendingCount} 项待核对${candidates.length > pendingCount ? ` · ${candidates.length - pendingCount} 项已保存` : ""}</span></h2>
      <p>${pendingCount ? "以下是 AI 的待提交建议，请对照原文核对。" : "以下限制已从保存的人审记录重新读取。"}暂不宣传不代表宣传主张已经核实。</p>
    </div>
    <div class="customer-constraint-list">
      ${candidates.map((item, index) => {
        const [title] = CONSTRAINT_PRESENTATION[item.constraint_type] || ["待核实内容"];
        const id = `constraint-${index}`;
        const targets = (detail.constraint_resolution_targets || []).filter(target => target.constraint_type === item.constraint_type);
        if (item.human_review) return `<article class="customer-constraint-card is-reviewed"><h3>${title} · 已保存</h3><p>${escapeHtml(item.source.evidence_quote)}</p><p>${escapeHtml(CONSTRAINT_ACTION_LABELS[item.human_review.decision])}</p>${item.human_review.amendment ? `<p>当前禁用：${escapeHtml((item.blocked_terms || []).join("、"))}；条件：${escapeHtml(item.condition || "无")}</p>` : ""}<p class="field-hint">${escapeHtml(accountLabel(item.human_review.reviewer))} · ${escapeHtml(formatConsoleTime(item.human_review.reviewed_at))}。已保存决定不能由新的批量提交覆盖。</p></article>`;
        const defaultAction = CONSTRAINT_DEFAULTS[item.constraint_type] || "";
        return `<article class="customer-constraint-card ${item.constraint_type === "identity_conflict" ? "is-critical" : ""}" data-constraint-id="${escapeHtml(item.constraint_id)}">
          <div class="customer-constraint-heading">
            <h3><span class="customer-constraint-number" aria-hidden="true">${String(index + 1).padStart(2, "0")}</span>${title}</h3>
            <span class="customer-constraint-status" data-constraint-status>AI 建议，待统一确认</span>
          </div>
          <div class="customer-constraint-body">
            <div class="customer-constraint-source"><span>资料中的原文</span><blockquote>${escapeHtml(item.source.evidence_quote)}</blockquote><p class="customer-constraint-scope">影响范围：${item.scope === "business" ? "客户主体与核心真实性（未解决仍会阻断）" : "相关宣传主张"}${item.condition ? `；成立条件：${escapeHtml(item.condition)}` : ""}。</p></div>
            <div class="field customer-constraint-action">
              <label for="${id}-action">处理方式</label>
              <select id="${id}-action" aria-label="限制审核决定" aria-describedby="${id}-hint" data-constraint-action>
                <option value="">本次暂不处理</option><option value="confirm" ${defaultAction === "confirm" ? "selected" : ""}>${item.constraint_type === "publication_prohibition" ? "禁止使用相关宣传" : item.constraint_type === "conditional_fact" ? "仅在原条件下使用" : "按原限制使用内容"}</option>
                ${item.constraint_type === "unverified_claim" ? '<option value="exclude">明确排除此项宣传，不用于内容</option>' : ""}
                <option value="defer" ${defaultAction === "defer" ? "selected" : ""}>${item.constraint_type === "unverified_claim" ? "暂不宣传，继续待核实" : "相关内容暂不能使用，继续核实"}</option><option value="dismiss">纠正识别</option><option value="resolve">补充核实资料，解决此项冲突</option>
              </select>
              <p class="customer-constraint-impact" id="${id}-hint" data-constraint-impact role="status">${constraintReviewImpact(item.constraint_type, defaultAction)}</p>
            </div>
          </div>
          ${["publication_prohibition", "conditional_fact"].includes(item.constraint_type) ? `<details class="customer-constraint-amendment"><summary>修改建议（需要来源依据）</summary><label><input type="checkbox" data-amend-enabled> 本次提交有来源的限制修订</label><div class="field"><label>禁用词（每行一个）<textarea data-amend-terms rows="3">${escapeHtml((item.blocked_terms || []).join("\n"))}</textarea></label></div><div class="field"><label>成立条件<input data-amend-condition value="${escapeHtml(item.condition || "")}"></label></div><div class="field"><label>影响的业务信息<select data-amend-fields multiple>${[...new Set([...(item.affected_fields || []), ...(detail.fact_candidates || []).map(v => v.field)])].map(field => `<option value="${escapeHtml(field)}" ${(item.affected_fields || []).includes(field) ? "selected" : ""}>${escapeHtml(customerFieldLabel(field))}</option>`).join("")}</select></label></div><div class="field"><label>准确原文<textarea data-amend-quote rows="3">${escapeHtml(item.source.evidence_quote)}</textarea></label></div><div class="field"><label>修改依据<textarea data-amend-reason rows="2"></textarea></label></div><div class="field"><label>对内容使用的影响<textarea data-amend-impact rows="2"></textarea></label></div><p class="field-hint">原候选永久保留。缩小禁用范围需要新的准确证据，成立条件不得丢失。</p></details>` : ""}
          <div class="customer-constraint-evidence" data-constraint-evidence-panel hidden>
            <h4>补充核对依据</h4><p>请引用准确原文，并说明核对结果。原记录会继续保留。</p>
            <div class="customer-constraint-evidence-fields">
              <div class="field"><label for="${id}-evidence">本轮已保存资料中的准确原文</label><textarea id="${id}-evidence" data-constraint-evidence rows="3" placeholder="引用本轮资料中的准确原文"></textarea></div>
              <div class="field"><label for="${id}-note">核对说明</label><textarea id="${id}-note" data-constraint-note rows="3" placeholder="说明误识别或冲突解决的核对结果"></textarea></div>
              <div class="field customer-constraint-target" ${targets.length ? "" : "hidden"}><label for="${id}-target">同时解决的历史条目（可选）</label><select id="${id}-target" data-constraint-target><option value="">仅处理本轮条目</option>${targets.map(target => `<option value="${escapeHtml([target.constraint_id, target.source_intake_id || "", target.constraint_sha256].join("|"))}">${escapeHtml(target.evidence_quote)}${target.source_intake_id ? `（历史资料 ${escapeHtml(target.source_intake_id.slice(-4))}）` : ""}</option>`).join("")}</select></div>
            </div>
          </div>
        </article>`;
      }).join("")}
    </div>
    ${pendingCount ? `<p class="customer-constraint-progress" data-constraint-progress aria-live="polite">处理方式已选择 0 / ${pendingCount}，提交后保存核对结果。</p>` : ""}
  </section>`;
}

export function bindCustomerConstraintControls(root = document, detail = {}) {
  const rows = [...root.querySelectorAll("[data-constraint-id]")];
  if (!rows.length) return;
  const progress = root.querySelector("[data-constraint-progress]");
  const update = () => {
    let selected = 0;
    rows.forEach(row => {
      const value = row.querySelector("[data-constraint-action]").value;
      selected += value ? 1 : 0;
      row.querySelector("[data-constraint-evidence-panel]").hidden = !["dismiss", "resolve"].includes(value);
      row.querySelector("[data-constraint-status]").textContent = value ? "待统一确认" : "本次暂不处理";
      row.classList.toggle("has-selection", Boolean(value));
      const impact = row.querySelector("[data-constraint-impact]");
      if (impact) {
        const type = detail.constraint_candidates?.find(item => item.constraint_id === row.dataset?.constraintId)?.constraint_type;
        impact.textContent = constraintReviewImpact(type, value);
        impact.classList.toggle("needs-attention", !value || value === "defer" || type === "identity_conflict");
      }
    });
    if (progress) progress.textContent = `处理方式已选择 ${selected} / ${rows.length}，提交后保存核对结果。`;
  };
  rows.forEach(row => row.querySelector("[data-constraint-action]").addEventListener("change", update));
  update();
}

export function customerSubmissionSummary(factChoices, constraintChoices) {
  const count = value => factChoices.filter(v => v === value).length;
  return {adopted: count("approve") + count("edit"), edited: count("edit"), rejected: count("reject"),
    pending: count("") + constraintChoices.filter(v => !v.decision).length,
    deferred: constraintChoices.filter(v => v.decision === "defer").length,
    conflicts: constraintChoices.filter(v => v.type === "identity_conflict" && !["resolve", "dismiss"].includes(v.decision)).length};
}

export function customerReviewConsequence(counts) {
  if (counts.conflicts) return "仍有主体冲突需要核实，保存进度不会解除相关创作限制。";
  if (counts.deferred) return `还有 ${counts.deferred} 项选择继续待核实，新客户档案暂不能批准。`;
  if (counts.pending) return `有 ${counts.pending} 项本次暂未处理，可保存进度后继续核对。`;
  return "保存本页核对结果后，客户与出镜人档案仍需分别批准。";
}

export function customerFinalPreview(value) {
  const approving = ["approve_business_profile","approve_customer_and_speakers"].includes(value.mode);
  const joint = value.schema_version === 'customer-final-confirmation-v1.1';
  const facts = Object.keys(value.projection.facts || {});
  const constraints = value.projection.constraints || [];
  const blockers = (value.blockers || []).map(item => ({
    critical_constraints:"重要限制仍需处理，当前不能批准客户档案。",
    business_identity:"客户基本身份信息尚不完整。",
    business_offer:"主要产品或服务信息尚不完整。",
    customer_use_context:"主要顾客及使用场景尚不完整。",
    production_bearing_facts:"还需要可用于内容的具体业务事实。",
  })[item] || (/^[a-z_]+$/.test(item) ? "仍有资料条件未满足，请继续核对或补充针对性来源。" : String(item)));
  return `<section class="customer-confirmation-scope" aria-label="本次客户确认范围">
    <dl class="customer-confirmation-metrics">
      <div><dt>客户信息</dt><dd>${facts.length} 项</dd></div>
      <div><dt>保留限制</dt><dd>${constraints.length} 项</dd></div>
      <div class="${blockers.length ? 'needs-attention' : ''}"><dt>待处理条件</dt><dd>${blockers.length} 项</dd></div>
    </dl>
    ${blockers.length ? `<ul class="customer-final-blockers">${blockers.map(v=>`<li>${escapeHtml(v)}</li>`).join("")}</ul>` : ''}
    ${constraints.length ? `<ul class="customer-confirmation-restrictions">${constraints.map(v=>`<li class="${['exclude','defer'].includes(v.decision) ? 'needs-attention' : ''}"><strong>${escapeHtml(CONSTRAINT_PRESENTATION[v.constraint_type]?.[0] || '重要事项')}</strong><span>${escapeHtml(CONSTRAINT_ACTION_LABELS[v.decision] || '仍待核对')}${v.condition ? `；${escapeHtml(v.condition)}` : ''}</span></li>`).join('')}</ul>` : ''}
    <div class="customer-confirmation-links" aria-label="返回核对资料">
      <button type="button" class="btn btn-ghost" data-review-section-target="customer-review-business">返回查看客户信息 ↑</button>
      ${constraints.length ? '<button type="button" class="btn btn-ghost" data-review-section-target="customer-review-constraints">返回查看重要限制 ↑</button>' : ''}
    </div>
    <p class="field-hint">${approving ? '确认后，客户信息及限制将用于后续创作资格检查。' : '本次只保存核对进度，不会批准客户或人物档案，也不会解除未解决的限制。'}${joint ? '' : '出镜人本人资料仍需独立审核。'}</p>
  </section>`;
}

export function bindCustomerReviewControls(detail, root = document, onChange = () => {}) {
  bindReviewReturnLinks(root);
  const rows = [...root.querySelectorAll("[data-review-row]")];
  const controls = [...root.querySelectorAll("[data-constraint-id]")];
  const update = () => {
    enhanceReviewDisclosures(root);
    const choices = controls.map(row => ({decision: row.querySelector("[data-constraint-action]").value,
      type: detail.constraint_candidates.find(v => v.constraint_id === row.dataset.constraintId)?.constraint_type}));
    const counts = customerSubmissionSummary(rows.map(row => row.dataset.decision || ""), choices);
    counts.conflicts = (detail.constraint_candidates || []).filter(v => v.constraint_type === "identity_conflict" && v.state !== "resolved").length;
    counts.edited += controls.filter(row => row.querySelector("[data-amend-enabled]")?.checked).length;
    const summary = root.querySelector("[data-review-progress]");
    if (summary) {
      summary.textContent = [!detail.unified_confirmation_enabled && `将采用 ${counts.adopted} 项业务信息`,
        counts.edited && `已修改 ${counts.edited} 项`, counts.rejected && `不采用 ${counts.rejected} 项`,
        counts.deferred && `待核实 ${counts.deferred} 项`, counts.pending && `暂未处理 ${counts.pending} 项`,
        counts.conflicts && `关键冲突 ${counts.conflicts} 项`].filter(Boolean).join(" · ");
      summary.hidden = !summary.textContent;
    }
    const consequence = root.querySelector("[data-review-consequence]");
    if (consequence) consequence.textContent = detail.joint_speaker_confirmation_enabled && !counts.deferred && !counts.conflicts && !counts.pending
      ? '核对上方资料后，可一次确认客户与所选出镜人。' : customerReviewConsequence(counts);
    const important = root.querySelector("[data-important-submissions]");
    if (important) important.innerHTML = controls.map((row, index) => `<li><strong>${escapeHtml(CONSTRAINT_PRESENTATION[choices[index].type]?.[0] || "重要事项")}</strong>：${escapeHtml(CONSTRAINT_ACTION_LABELS[choices[index].decision] || "本次暂不处理")}<small>${escapeHtml(detail.constraint_candidates.find(v => v.constraint_id === row.dataset.constraintId)?.source.evidence_quote || "")}</small>${row.querySelector("[data-amend-enabled]")?.checked ? `<p>本次修订：禁用 ${escapeHtml(row.querySelector("[data-amend-terms]").value || "无")}；条件 ${escapeHtml(row.querySelector("[data-amend-condition]").value || "无")}；影响信息 ${escapeHtml([...row.querySelector("[data-amend-fields]").selectedOptions].map(v => customerFieldLabel(v.value)).join("、") || "原宣传范围")}。</p><small>修订依据：${escapeHtml(row.querySelector("[data-amend-quote]").value)}；说明：${escapeHtml(row.querySelector("[data-amend-reason]").value)}；生产影响：${escapeHtml(row.querySelector("[data-amend-impact]").value)}</small>` : ""}</li>`).join("");
    const button = root.querySelector("#submit-fact-review");
    if (button) button.disabled = !rows.some(row => row.dataset.decision) && !choices.some(v => v.decision) && !root.querySelector("#human-industry")?.value && !detail.review_progress?.completion_retry_required && !(detail.speaker_candidates || []).some(v => !v.confirmed) && detail.fact_candidates.some(v=>v.state==="requires_review");
    onChange();
  };
  rows.forEach(row => {
    row.querySelectorAll("[data-review-choice]").forEach(button => button.addEventListener("click", () => {
      row.dataset.decision = button.dataset.reviewChoice;
      const candidate = detail.fact_candidates.find(v => v.candidate_id === row.dataset.reviewRow);
      try { row.querySelector("[data-fact-value]").innerHTML = formatProfileValue(row.dataset.decision === "edit"
        ? parseEditedFactValue(candidate.value, row.querySelector("textarea").value) : candidate.value); }
      catch { row.querySelector("[data-fact-value]").textContent = "请检查修改内容"; }
      row.classList.toggle("is-rejected", row.dataset.decision === "reject");
      row.querySelector("[data-fact-status]").textContent = {approve: "待统一确认", edit: "已修改，待统一确认", reject: "不采用，待保存"}[row.dataset.decision] || "本次暂不处理";
      row.querySelector(".review-edit-panel").hidden = row.dataset.decision !== "edit";
      row.querySelector('[data-review-choice="approve"]').hidden = row.dataset.decision === "approve";
      row.querySelectorAll("[data-review-choice]").forEach(choice => choice.setAttribute?.("aria-pressed", String(choice.dataset.reviewChoice === row.dataset.decision)));
      const options = row.querySelector(".customer-fact-options");
      if (options) options.open = false;
      if (row.dataset.decision === "edit") row.querySelector("textarea").focus();
      else options?.querySelector("summary")?.focus();
      window.__customerReviewDirty = true;
      update();
    }));
    row.querySelector("textarea").addEventListener("input", () => {
      const candidate = detail.fact_candidates.find(v => v.candidate_id === row.dataset.reviewRow);
      try { row.querySelector("[data-fact-value]").innerHTML = formatProfileValue(parseEditedFactValue(candidate.value, row.querySelector("textarea").value)); }
      catch { row.querySelector("[data-fact-status]").textContent = "请检查修改内容"; }
      window.__customerReviewDirty = true;
      update();
    });
  });
  root.querySelectorAll(".customer-review-page input, .customer-review-page textarea, .customer-review-page select").forEach(input => {
    for (const event of ["input", "change"]) input.addEventListener(event, () => {window.__customerReviewDirty = true; update();});
  });
  update();
  return update;
}

function discoveryPanel(detail) {
  const candidates = (detail.speaker_candidates || []).filter(item => !item.confirmed);
  if (candidates.length) return speakerDiscoverySection(candidates,detail.joint_speaker_confirmation_enabled);
  if ((detail.speakers || []).length) return "";
  if (detail.speaker_discovery_status === "failed") return `<section class="work-surface customer-discovery-status"><h2>人物发现暂未完成</h2><p>客户信息仍然保留，可以单独重试查找人物，也可以手动添加。</p><div class="customer-recovery-actions"><button class="btn btn-secondary" data-retry-person-discovery>重试查找出镜人</button><a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>手动添加出镜人</a></div><div data-person-discovery-progress></div></section>`;
  return `<section class="work-surface customer-discovery-status"><h2>${(detail.speaker_candidates || []).length ? "已保存所选出镜人" : (detail.speaker_count ? "本次资料未发现新增人物" : "暂未找到明确的出镜人")}</h2><p>人物资料与客户资料分别审核。可以继续处理已保存人物，或补充新的本人资料。</p><div class="customer-recovery-actions">${detail.speaker_discovery_status === "completed" && !(detail.speaker_candidates || []).length ? '<button class="btn btn-secondary" data-retry-person-discovery>重新查找出镜人</button>' : ""}<a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a></div><div data-person-discovery-progress></div></section>`;
}

const SPEAKER_TYPE_OPTIONS = [
  ["owner_founder", "老板 / 创始人"],
  ["frontline_expert", "一线专业人员"],
  ["brand", "品牌代表"],
  ["generic", "其他出镜人"],
];

function speakerDiscoverySection(candidates = [], joint = false) {
  if (!candidates.length) return "";
  return `
    <section class="work-surface speaker-discovery-surface" id="customer-review-speakers">
      <div class="review-surface-heading">
        <h2>确认出镜人 <span class="customer-section-count">${candidates.length} 位待确认</span></h2>
        <p>${joint ? '请核对选中的人。下方会展示完整人物资料，最后与客户档案一次确认。' : '请检查选中的人；确认后保存资料，之后仍需单独确认人物档案。'}</p>
      </div>
      <div class="speaker-discovery-list">
        ${candidates.map((candidate) => {
          const candidateId = escapeHtml(candidate.candidate_id);
          const explicit = candidate.candidate_status === "explicit_speaker";
          // UI preselection never grants permission or saves a Human decision.
          // Preserve an explicit previous rejection when resuming confirmation.
          const selected = !candidate.confirmed && (
            typeof candidate.confirmation?.selected === "boolean"
              ? candidate.confirmation.selected
              : true
          );
          const speakerType = candidate.confirmation?.speaker_type ?? candidate.speaker_type_hint ?? null;
          return `
            <article class="speaker-discovery-card" data-speaker-candidate="${candidateId}">
              <label class="speaker-discovery-toggle">
                <input type="checkbox" data-speaker-select ${selected ? "checked" : ""}>
                <span>
                  <strong>本次添加为出镜人</strong>
                  <small>${explicit ? "资料明确提到会出镜" : "可能代表客户出镜"}</small>
                </span>
              </label>
              <div class="speaker-discovery-fields">
                <div class="field">
                  <label for="speaker-${candidateId}-name">姓名</label>
                  <input id="speaker-${candidateId}-name" data-speaker-name maxlength="200" value="${escapeHtml(candidate.confirmation?.speaker_name || candidate.name || "")}" placeholder="请补充姓名">
                </div>
                <div class="field">
                  <label for="speaker-${candidateId}-role">公开身份</label>
                  <input id="speaker-${candidateId}-role" data-speaker-role maxlength="200" value="${escapeHtml(candidate.confirmation?.public_role || candidate.public_role || "")}" placeholder="请补充公开身份">
                </div>
                <div class="field">
                  <label for="speaker-${candidateId}-type">出镜人类型</label>
                  <select id="speaker-${candidateId}-type" data-speaker-type>
                    <option value="" ${speakerType === null ? "selected" : ""}>暂时无法判断，请选择</option>
                    ${SPEAKER_TYPE_OPTIONS.map(([value, label]) => `<option value="${value}" ${value === speakerType ? "selected" : ""}>${label}</option>`).join("")}
                  </select>
                </div>
              </div>
              <details class="speaker-discovery-evidence">
                <summary>查看来源依据</summary>
                <ul>${(candidate.evidence_quotes || []).map((quote) => `<li>${escapeHtml(quote)}</li>`).join("")}</ul>
              </details>
            </article>`;
        }).join("")}
      </div>
    </section>`;
}

function customerProfileSections(facts = []) {
  const values = new Map(
    facts
      .filter((fact) => fact.state === "known")
      .map((fact) => [fact.field, fact.value]),
  );
  const grouped = new Set(CUSTOMER_PROFILE_GROUPS.flatMap((group) => group.fields));
  const sections = CUSTOMER_PROFILE_GROUPS.map((group) =>
    ProfileSection({
      title: group.title,
      rows: group.fields.map((field) =>
        ProfileRow({
          label: customerFieldLabel(field),
          value: values.get(field),
          labelFor: customerFieldLabel,
        }),
      ),
    }),
  );
  const other = facts.filter(
    (fact) => fact.state === "known" && !grouped.has(fact.field),
  );
  if (other.length) {
    sections.push(
      ProfileSection({
        title: "其他信息",
        rows: other.map((fact) =>
          ProfileRow({
            label: customerFieldLabel(fact.field),
            value: fact.value,
            labelFor: customerFieldLabel,
          }),
        ),
      }),
    );
  }
  return sections.filter(Boolean).join("");
}

export function createCustomerViews({
  app,
  api,
  navigate,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  openModal,
  renderLoadError,
}) {
  let stopPolling = null;

  function stopTaskPolling() {
    stopPolling?.();
    stopPolling = null;
  }

  function bindCustomerProgress(task, businessId) {
    const host = document.querySelector("[data-customer-progress]");
    if (!host) return;

    host.innerHTML = customerProgressPanel(task);

    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,

      onUpdate(next) {
        const current = document.querySelector("[data-customer-progress]");
        if (current) current.innerHTML = customerProgressPanel(next);
      },

      onDone(next) {
        const current = document.querySelector("[data-customer-progress]");
        if (!current) return;
        // Re-read canonical state on completion. This opens Human review;
        // it never submits a fact decision or grants Persona approval.
        void renderCustomerDetail(businessId);
      },
    });
  }

  async function renderCustomers() {
    const route = window.location.href;
    stopTaskPolling();
    app.innerHTML=shell("客户",`<main class="page page-standard brand-list-page customer-list-page">${pageHeading("","客户","客户、人物与创作进展，清楚地放在一起。")}${listSkeleton()}</main>`);
    bindCommonActions();

    try {
      const params = new URLSearchParams(window.location.search);
      const search = params.get("search") || "";
      const filter = ["all", "pending", "ready"].includes(params.get("filter_by")) ? params.get("filter_by") : "all";
      const sort = params.get("sort_by") === "updated" ? "updated" : "action";
      const page = Math.max(1, Number(params.get("page")) || 1);
      const query = new URLSearchParams({search, filter_by: filter, sort_by: sort, page: String(page)});
      const data = await api(`/api/customers/operations?${query}`);
      if (window.location.href !== route) return;
      const customers = data.customers || [];
      const link = (patch) => `/customers?${new URLSearchParams({...Object.fromEntries(query), ...patch})}`;
      const controls = `<form class="customer-list-toolbar" id="customer-search-form">
        <div class="customer-search"><label class="sr-only" for="customer-search">搜索客户、已确认行业或地区</label>${searchIcon}<input id="customer-search" type="search" name="search" maxlength="100" placeholder="搜索客户、行业或地区" value="${escapeHtml(search)}"><button class="btn btn-secondary btn-compact" type="submit">搜索</button></div>
        <label class="customer-list-sort">排序<select id="customer-sort" aria-label="排序"><option value="action" ${sort === "action" ? "selected" : ""}>待处理优先</option><option value="updated" ${sort === "updated" ? "selected" : ""}>最近更新</option></select></label>
      </form><nav class="customer-list-filters" aria-label="客户筛选">${[["all","全部"],["pending","待处理"],["ready","可创作"]].map(([value,label]) => `<a class="customer-filter ${filter === value ? "active" : ""}" href="${escapeHtml(link({filter_by:value,page:"1"}))}" data-route ${filter === value ? 'aria-current="page"' : ""}>${label}<span>${data.filter_counts?.[value] ?? "—"}</span></a>`).join("")}</nav>`;

      const content = customers.length
        ? `
          <div class="customer-operations-list">
            ${customers.map(customerCard).join("")}
          </div>`
        : listEmpty(search || filter !== "all" || page > 1 ? "没有符合条件的客户" : "从第一位客户开始",
                    search || filter !== "all" || page > 1 ? "调整搜索或筛选条件，查看其他客户。" : "添加客户资料，让人物、创作与下一步工作有清楚的归属。");

      app.innerHTML = shell(
        "客户",
        `
          <main class="page page-standard brand-list-page customer-list-page">
            ${pageHeading(
              "",
              "客户",
              "集中查看客户状态、出镜人和下一步工作。",
              `
                <a class="btn btn-primary" href="/customers/new" data-route>
                  新建客户
                </a>`,
            )}

            ${controls}
            <p class="customer-list-count">${data.total} 位客户 <span>· 筛选数量基于全部搜索匹配</span></p>
            ${content}
            <nav class="customer-list-pagination" aria-label="客户列表分页">${page > 1 ? `<a class="btn btn-secondary" href="${escapeHtml(link({page:String(page-1)}))}" data-route>上一页</a>` : ""}<span>第 ${page} 页</span>${page * data.page_size < data.total ? `<a class="btn btn-secondary" href="${escapeHtml(link({page:String(page+1)}))}" data-route>下一页</a>` : ""}</nav>
          </main>`,
      );

      bindCommonActions();
      document.querySelector("#customer-search-form").addEventListener("submit", event => {event.preventDefault(); navigate(link({search:document.querySelector("#customer-search").value.trim(),page:"1"}));});
      document.querySelector("#customer-sort").addEventListener("change", event => navigate(link({sort_by:event.target.value,page:"1"})));
    } catch (error) {
      if (window.location.href !== route) return;
      renderLoadError("客户列表暂时无法读取", error);
    }
  }

  function renderCustomerNew() {
    stopTaskPolling();
    app.innerHTML = shell("添加客户", `
      <main class="page page-form profile-mutation-page smart-profile-page customer-intake-page">
        ${pageHeading("", "添加客户", "把客户提供的资料粘贴进来，系统会整理业务信息，并找出可能的出镜人。")}
        ${intakeSteps(1)}
        <section class="work-surface profile-form-surface">
          <form id="customer-new-form" novalidate>
            <div class="field"><label for="customer-name">客户名称 <span class="customer-field-note">必填</span></label>
              <input id="customer-name" maxlength="200" autocomplete="organization" placeholder="填写客户或门店名称" required></div>
            <div class="field"><label for="customer-materials">客户资料</label>
          <textarea id="customer-materials" rows="7" maxlength="50000" placeholder="粘贴客户介绍、采访记录、产品与服务、顾客问题。人物的姓名、身份和本人经历也可以写在同一份资料里。"></textarea>
              <span class="field-hint">无需提前判断行业。系统整理后，由你分别确认客户信息和出镜人信息。</span></div>
            <div id="customer-form-error" class="form-error" role="alert"></div>
            <div class="profile-form-actions">
              <button class="btn btn-primary" type="submit">开始整理资料</button>
              <button class="btn btn-secondary" type="button" data-save-customer>先保存，稍后补充</button>
            </div>
            <p class="governance-copy">只填写名称也可以先保存；没有资料时不会启动分析。系统建议仍需人工审核。</p>
            <div data-duplicate-customer></div>
          </form>
        </section>
      </main>`);
    bindCommonActions();
    let submissionKey = crypto.randomUUID();
    let lastInput = "";
    let pending = false;
    const submit = async (saveOnly, createSeparate = false) => {
      if (pending) return;
      const name = document.querySelector("#customer-name").value.trim();
      const materials = document.querySelector("#customer-materials").value.trim();
      const errorBox = document.querySelector("#customer-form-error");
      errorBox.classList.remove("visible");
      const message = !name ? "请填写客户名称。" : !saveOnly && !materials ? "请粘贴客户资料，或选择先保存客户。" : "";
      if (message) { errorBox.textContent = message; errorBox.classList.add("visible"); return; }
      const signature = JSON.stringify([name, materials, saveOnly]);
      if (lastInput && lastInput !== signature) submissionKey = crypto.randomUUID();
      lastInput = signature;
      pending = true;
      document.querySelectorAll("#customer-new-form button").forEach(button => button.disabled = true);
      try {
        const result = await api("/api/customers/analyze", {method: "POST", body: JSON.stringify({
          customer_name: name, materials, save_only: saveOnly, create_separate: createSeparate, submission_key: submissionKey,
        })});
        if (result.existing_customer_check_required) {
          document.querySelector("[data-duplicate-customer]").innerHTML = `
            <aside class="result-banner"><h2>已有同名客户，请先检查</h2>
              <p>如果属于同一个客户，请打开现有记录补充资料。</p>
              <a class="btn btn-secondary" href="/customers/${encodeURIComponent(result.business_id)}" data-route>查看已有客户</a>
              <button type="button" class="btn btn-secondary" data-separate-customer>确认为不同客户，单独建立</button></aside>`;
          bindCommonActions();
          document.querySelector("[data-separate-customer]").addEventListener("click", () => submit(saveOnly, true));
          return;
        }
        showToast(result.saved_only ? "客户已保存，可以稍后补充资料。" : "资料已提交，可以离开页面后继续查看。");
        navigate(`/customers/${encodeURIComponent(result.business_id)}`);
      } catch (error) { errorBox.textContent = error.detail?.next_action || error.message; errorBox.classList.add("visible"); }
      finally { pending = false; document.querySelectorAll("#customer-new-form button").forEach(button => button.disabled = false); }
    };
    document.querySelector("#customer-new-form").addEventListener("submit", event => {event.preventDefault(); void submit(false);});
    document.querySelector("[data-save-customer]").addEventListener("click", () => submit(true));
  }

  function renderFactReview(detail) {
    const supplement = detail.latest_intake_type === "gap_supplement";
    const amendment = detail.latest_intake_type === "review_amendment";
    const reviewTitle = detail.joint_speaker_confirmation_enabled ? '核对客户与出镜人资料' : detail.status === "persona_review_required" ? "核对并批准客户档案" : amendment ? "核对更正后的客户资料" : "检查 AI 整理的客户资料";
    const candidates = detail.fact_candidates || [];
    const known = candidates.filter(
      (item) => item.state === "known_candidate",
    );
    const needsReview = candidates.filter(
      (item) => item.state === "requires_review",
    );
    const knownHtml = known.length
      ? `
        <details class="known-facts-disclosure">
          <summary>已经明确的信息 <span>${known.length} 项</span></summary>
          <dl class="profile-rows">
            ${known
              .map((item) =>
                ProfileRow({
                  label: customerFieldLabel(item.field),
                  value: item.value,
                  labelFor: customerFieldLabel,
                }),
              )
              .join("")}
          </dl>
        </details>`
      : "";

    app.innerHTML = shell(
      reviewTitle,
      `
        <main class="page page-form customer-review-page profile-review-page customer-intake-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "",
            reviewTitle,
            amendment ? "请核对本轮更正及其依据。原资料、审核记录和关键限制保留；更正仍需独立档案批准。" : supplement
              ? "只检查本轮新增事实；之前已经确认的信息会继续保留。"
              : "AI 已帮你整理好内容。请快速核对，发现不准确的地方可以直接修改。",
          )}
          <p class="customer-review-name">${escapeHtml(detail.display_name)}</p>

          ${intakeSteps(3, amendment)}
          <nav class="customer-review-overview" aria-label="核对内容">
            ${(detail.constraint_candidates || []).length ? `<button type="button" data-review-section-target="customer-review-constraints">重要事项 <strong>${(detail.constraint_candidates || []).filter(v => !v.human_review).length} 项待核对</strong></button>` : ""}
            <button type="button" data-review-section-target="customer-review-business">业务信息 <strong>${needsReview.length} 项待确认</strong></button>
            ${(detail.speaker_candidates || []).some(v => !v.confirmed) ? `<button type="button" data-review-section-target="customer-review-speakers">出镜人 <strong>${detail.speaker_candidates.filter(v => !v.confirmed).length} 位待确认</strong></button>` : ""}
            <button type="button" data-review-section-target="customer-review-summary">查看提交摘要</button>
          </nav>
          ${detail.review_progress?.saved_count ? `<p class="result-banner">已保存 ${detail.review_progress.saved_count} 项审核决定，${detail.review_progress.pending_count} 项仍待处理。已保存记录保留，不需要重复核对。${detail.review_progress.completion_retry_required ? "审核决定已保存，后续整理中断，请继续完成保存。" : ""}</p>` : ""}
          ${customerConstraintReview(detail)}

          <section class="work-surface review-surface" id="customer-review-business">
            <div class="review-surface-heading">
              <h2>客户业务信息 ${needsReview.length ? `<span class="customer-section-count">${needsReview.length} 项待确认</span>` : ""}</h2>
              <p>准确的普通信息可统一确认；需要更正时打开“调整”。标记为重点核对的信息仍需明确选择。</p>
            </div>
            ${knownHtml}
            ${customerReviewGroups(needsReview)}
            ${!candidates.some(item => item.field === "industry") && (!detail.industry || detail.industry === "待确认") ? `<div class="field customer-industry-field"><label for="human-industry">所属行业</label><select id="human-industry"><option value="">保留待判断（未提供人工判断）</option><option value="__uncertain__">暂不确定</option>${CUSTOMER_INDUSTRIES.map(value => `<option>${escapeHtml(value)}</option>`).join("")}</select><span class="field-hint">系统暂时无法准确判断。可以根据真实资料选择行业；留待判断不会阻止保存或其他审核。</span></div>` : ""}
          </section>

          ${discoveryPanel(detail)}

          <section class="work-surface customer-submit-summary" id="customer-review-summary"><h2>${detail.unified_confirmation_enabled ? "本次确认" : "本次提交范围"}</h2><p data-review-progress></p><p class="customer-review-consequence" data-review-consequence role="status"></p>
          ${(detail.constraint_candidates || []).some(v => !v.human_review) ? '<details class="customer-submit-details"><summary>查看重要事项提交明细</summary><ul data-important-submissions></ul></details>' : ""}
          <p class="field-hint">${detail.joint_speaker_confirmation_enabled ? '请核对上方资料及本次确认范围，最后点击下方按钮提交。' : detail.unified_confirmation_enabled ? "请确认已核对上方资料。资料审核与客户档案批准分别保留记录；出镜人独立审核。" : "点击保存才形成逐项人工审核决定；关键限制仍按原规则生效。"}</p>
          ${detail.unified_confirmation_enabled ? '<div data-customer-final-preview aria-live="polite"></div>' : ""}
          <div class="review-submit-bar">
            <button
              id="submit-fact-review"
              class="btn btn-primary"
              type="button"
            >
              确认并保存已核对的信息
            </button>
          </div>
          </section>
        </main>`,
    );

    bindCommonActions();
    bindCustomerConstraintControls(document, detail);
    let refreshFinal = () => {};
    const updateSummary = bindCustomerReviewControls(detail, document, () => refreshFinal());
    document.querySelectorAll('[data-review-row]').forEach(row => {
      const item = needsReview.find(candidate => candidate.candidate_id === row.dataset.reviewRow);
      if (item?.field === "industry") {
        const reject = row.querySelector('[data-review-choice="reject"]');
        reject.textContent = "暂不确定";
        const input = row.querySelector("textarea");
        const select = document.createElement("select");
        select.setAttribute("aria-label", "修改行业");
        select.innerHTML = CUSTOMER_INDUSTRIES.map(value => `<option ${value === item.value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("");
        input.hidden = true;
        input.value = select.value;
        select.addEventListener("change", () => {input.value = select.value; input.dispatchEvent(new Event("input")); updateSummary();});
        input.before(select);
      }
    });
    bindDiscoveryRetry(detail);

    const collectReview = () => {
        const decisions = [];
        const constraintDecisions = [];
        for (const item of detail.constraint_candidates || []) {
          if (item.human_review) continue;
          const action = document.querySelector(`[data-constraint-id="${CSS.escape(item.constraint_id)}"] select`)?.value;
          if (!action) continue;
          const row = document.querySelector(`[data-constraint-id="${CSS.escape(item.constraint_id)}"]`);
          const decision = {constraint_id: item.constraint_id, decision: action};
          if (row.querySelector("[data-amend-enabled]")?.checked) {
            decision.amendment = {schema_version: "restriction-amendment-v1.0", original_constraint_sha256: item.original_constraint_sha256,
              candidate_sha256: detail.review_context.candidate_sha256,
              control: {scope: item.scope, affected_fields: [...row.querySelector("[data-amend-fields]").selectedOptions].map(v => v.value),
                blocked_terms: row.querySelector("[data-amend-terms]").value.split("\n").map(v => v.trim()).filter(Boolean), condition: row.querySelector("[data-amend-condition]").value.trim() || null},
              evidence_quote: row.querySelector("[data-amend-quote]").value.trim(), reason: row.querySelector("[data-amend-reason]").value.trim(), production_impact: row.querySelector("[data-amend-impact]").value.trim()};
            if (!decision.amendment.reason || !decision.amendment.production_impact || !decision.amendment.evidence_quote) {throw new Error("请填写限制修订的准确来源、依据及对内容使用的影响。");}
          }
          if (["dismiss", "resolve"].includes(action)) {
            decision.resolution_quote = row.querySelector("[data-constraint-evidence]").value.trim();
            decision.note = row.querySelector("[data-constraint-note]").value.trim();
            if (!decision.resolution_quote || !decision.note) { throw new Error("请引用本轮已保存资料中的准确原文，并填写核对说明。"); }
            const target = (detail.constraint_resolution_targets || []).find(value => [value.constraint_id, value.source_intake_id || "", value.constraint_sha256].join("|") === row.querySelector("[data-constraint-target]").value);
            if (target && action === "resolve") {
              decision.resolution_target = {constraint_id: target.constraint_id, constraint_sha256: target.constraint_sha256,
                ...(target.source_intake_id ? {source_intake_id: target.source_intake_id, raw_answers_sha256: target.raw_answers_sha256} : {})};
            }
          }
          constraintDecisions.push(decision);
        }

        for (const candidate of needsReview) {
          const row = document.querySelector(
            `[data-review-row="${CSS.escape(candidate.candidate_id)}"]`,
          );
          const decision = row?.dataset.decision;
          if (!decision) continue;

          const value = {
            candidate_id: candidate.candidate_id,
            decision,
            note:
              decision === "approve"
                ? "Internal Console reviewer confirmed this customer information."
                : decision === "reject"
                  ? "Internal Console reviewer did not accept this customer information."
                  : "Internal Console reviewer corrected this customer information.",
          };

          if (decision === "edit") {
            try {
              value.edited_value = parseEditedFactValue(
                candidate.value,
                row.querySelector(".review-edit-panel textarea").value,
              );
            } catch (error) {
              throw error;
            }
          }

          if (candidate.field === "industry" && decision === "reject") value.note = "运营明确选择行业暂不确定，不采用本次系统建议。";
          decisions.push(value);
        }

        const speakerConfirmations = (detail.speaker_candidates || []).filter(candidate => !candidate.confirmed).map(
          (candidate) => {
            const row = document.querySelector(
              `[data-speaker-candidate="${CSS.escape(candidate.candidate_id)}"]`,
            );
            return {
              candidate_id: candidate.candidate_id,
              selected: row?.querySelector("[data-speaker-select]")?.checked === true,
              speaker_name: row?.querySelector("[data-speaker-name]")?.value.trim() || null,
              public_role: row?.querySelector("[data-speaker-role]")?.value.trim() || null,
              speaker_type: row?.querySelector("[data-speaker-type]")?.value || null,
            };
          },
        );
        const industry = document.querySelector("#human-industry")?.value;
        return {decisions, constraint_decisions:constraintDecisions, speaker_confirmations:speakerConfirmations,
          review_context:detail.review_context?.token,
          ...(detail.review_progress?.completion_retry_required ? {resume_review:true} : {}),
          ...(industry ? {industry_review:{decision:industry === "__uncertain__" ? "uncertain" : "confirm",value:industry === "__uncertain__" ? null : industry}} : {}),
          note:"Internal Console customer information review completed."};
    };
    if (detail.unified_confirmation_enabled) {
      const bindFinal = detail.joint_speaker_confirmation_enabled ? bindCustomerSpeakerConfirmation : bindFinalCustomerConfirmation;
      refreshFinal = bindFinal({root:document, detail, api, collect:collectReview,
        render:customerFinalPreview, reload:()=>renderCustomerDetail(detail.business_id), toast:showToast});
      return;
    }
    document
      .querySelector("#submit-fact-review")
      .addEventListener("click", async () => {
        let payload;
        try {payload = collectReview();} catch (error) {showToast(error.message); return;}
        const {decisions, constraint_decisions:constraintDecisions, speaker_confirmations:speakerConfirmations} = payload;
        const button = document.querySelector("#submit-fact-review");
        button.disabled = true;
        button.textContent = "正在保存…";

        try {
          // Preserve the independent, existing Speaker Draft save path when no
          // Customer decision is selected. Never create an empty Fact Review.
          if (!decisions.length && !constraintDecisions.length && !document.querySelector("#human-industry")?.value && !detail.review_progress?.completion_retry_required && speakerConfirmations.length) {
            const result = await api(`/api/customers/${encodeURIComponent(detail.business_id)}/speaker-discovery/confirm`, {
              method: "POST", body: JSON.stringify({decisions: speakerConfirmations}),
            });
            showToast(result.speaker_confirmation?.retry_required ? "出镜人资料暂未保存成功，可以稍后继续。"
              : "出镜人选择已保存。客户事实尚未提交审核，客户档案尚未批准。");
            window.__customerReviewDirty = false;
            renderCustomerDetail(detail.business_id);
            return;
          }
          const result = await api(
            `/api/customers/${encodeURIComponent(
              detail.business_id,
            )}/facts/review`,
            {
              method: "POST",
              body: JSON.stringify({
                ...(detail.review_progress?.completion_retry_required ? {resume_review: true} : {}),
                decisions,
                review_context: detail.review_context?.token,
                constraint_decisions: constraintDecisions,
                speaker_confirmations: speakerConfirmations,
                ...(document.querySelector("#human-industry")?.value ? {industry_review: {
                  decision: document.querySelector("#human-industry").value === "__uncertain__" ? "uncertain" : "confirm",
                  value: document.querySelector("#human-industry").value === "__uncertain__" ? null : document.querySelector("#human-industry").value,
                }} : {}),
                note: "Internal Console customer information review completed.",
              }),
            },
          );

          const blocked = result.review.status === "completed_persona_blocked";
          const partial = result.review.status === "review_progress_saved";
          const peopleSaved = (result.speaker_confirmation?.drafts || []).some(item => item.speaker_id);
          showToast(result.review.recovery_required ? `已保存 ${result.review.saved_count} 项审核决定，后续整理中断。请继续保存，已保存项不会重复写入。` : result.speaker_confirmation?.retry_required
            ? "客户事实已保存，出镜人资料暂未保存成功，可以稍后继续。"
            : `${peopleSaved ? "客户已核对的信息和出镜人资料均已保存。" : "客户事实已保存。"}${partial ? `已保存审核进度，仍有 ${result.review.pending_count} 项待处理。` : blocked ? "本次事实审核已完成，仍有信息需要处理；客户档案尚未批准。" : "本次事实审核已完成，可以继续确认客户档案。"}`);
          window.__customerReviewDirty = false;

          renderCustomerDetail(detail.business_id);
        } catch (error) {
          showToast([error.detail?.message || error.message, error.detail?.next_action].filter(Boolean).join(" "));
          button.disabled = false;
          button.textContent = "确认并保存已核对的信息";
        }
      });
  }

  function renderPersonaReview(detail) {
    const persona = detail.business_persona;
    const facts = (persona?.facts || []).filter(
      (fact) => fact.state === "known",
    );

    app.innerHTML = shell(
      "确认客户档案",
      `
        <main class="page page-form customer-review-page profile-review-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "",
            "确认客户档案",
            "请整体检查这些信息，确认后会用于后续内容创作。",
          )}

          ${intakeSteps(3, detail.latest_intake_type === "review_amendment")}
          ${detail.current_business_persona?.approved ? '<p class="result-banner">新资料正在确认。原有已批准版本继续有效；确认本页后才启用新版本，出镜人将需要独立复核。</p>' : ""}
          ${auditNote(detail)}
          <div class="work-surface profile-document">
            ${customerProfileSections(facts)}
          </div>
          ${customerConstraintReview(detail)}

          <div class="sticky-action profile-approval-bar">
            <p>确认后的客户信息将用于后续视频内容。</p>
            <button
              id="approve-business-persona"
              class="btn btn-primary"
              type="button"
            >
              确认客户档案
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();

    document
      .querySelector("#approve-business-persona")
      .addEventListener("click", async () => {
        const decision = await openModal({
          title: "确认客户档案？",
          description: "请确认你已经整体检查客户信息。确认后，这些信息会用于后续内容创作。",
          confirmLabel: "确认客户档案",
        });
        if (!decision.confirmed) return;

        const button = document.querySelector(
          "#approve-business-persona",
        );

        button.disabled = true;
        button.textContent = "正在批准…";

        try {
          const result = await api(
            `/api/customers/${encodeURIComponent(
              detail.business_id,
            )}/persona/approve`,
            {
              method: "POST",
              body: JSON.stringify({
                review_context: detail.approval_context.token,
                note: "Internal Console reviewer confirmed the complete customer profile.",
              }),
            },
          );

          if (result.speaker_handoff?.task_count > 0) {
            showToast(`客户档案已确认，已识别 ${result.speaker_handoff.task_count} 位出镜人，正在整理出镜人信息。`);
          } else if ((result.speaker_handoff?.failed || []).length) {
            showToast("客户档案已确认，出镜人信息需要继续处理。");
          } else {
            showToast("客户档案已确认");
          }
          renderCustomerDetail(detail.business_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "确认客户档案";
        }
      });
  }

  async function renderCustomerEdit(businessId) {
    stopTaskPolling();
    skeletonPage("修改客户资料");

    try {
        const detail = await api(`/api/customers/${encodeURIComponent(businessId)}`);
        if (detail.current_business_persona?.approved || detail.business_persona?.approved) {
          return navigate(`/customers/${encodeURIComponent(businessId)}/supplement`, true);
        }
        const payload = await api(
        `/api/customers/${encodeURIComponent(
            businessId,
        )}/input`,
        );

        const source = payload.input;

        app.innerHTML = shell(
        "更新客户资料",
        `
            <main class="page page-form profile-mutation-page">
            ${pageHeading(
                "",
                "更新客户资料",
                "修改后会重新分析，已确认的历史记录不会被静默覆盖。",
            )}

            <section class="work-surface profile-form-surface">
                <form id="customer-edit-form">
                <div class="field">
                    <label for="customer-name">客户名称</label>
                    <input
                    id="customer-name"
                    maxlength="200"
                    value="${escapeHtml(source.customer_name || "")}"
                    required
                    >
                </div>

                <div class="field">
                    <label for="customer-industry">行业</label>
                    <input
                    id="customer-industry"
                    maxlength="120"
                    value="${escapeHtml(source.industry || "")}"
                    placeholder="可留空，稍后根据资料确认"
                    >
                </div>

                <div class="field">
                    <label for="customer-materials">已有资料</label>
                    <textarea
                    id="customer-materials"
                    rows="8"
                    maxlength="50000"
                    required
                    >${escapeHtml(source.materials || "")}</textarea>
                </div>

                <div id="customer-edit-error" class="form-error"></div>

                <div class="profile-form-actions">
                    <button class="btn btn-primary btn-wide" type="submit">
                    重新分析
                    </button>
                </div>
                </form>
            </section>
            </main>`,
        );

        bindCommonActions();

        document
        .querySelector("#customer-edit-form")
        .addEventListener("submit", async (event) => {
            event.preventDefault();

            const button =
            event.currentTarget.querySelector(
                "button[type=submit]",
            );

            button.disabled = true;
            button.textContent = "正在提交…";

            try {
            const result = await api(
                `/api/customers/${encodeURIComponent(
                businessId,
                )}/reanalyze`,
                {
                method: "POST",
                body: JSON.stringify({
                    customer_name:
                    document.querySelector(
                        "#customer-name",
                    ).value,
                    industry:
                    document.querySelector(
                        "#customer-industry",
                    ).value,
                    materials:
                    document.querySelector(
                        "#customer-materials",
                    ).value,
                }),
                },
            );

            showToast(
                result.new_intake
                ? "已提交更新后的客户资料"
                : "已重新提交客户资料",
            );

            navigate(
                `/customers/${encodeURIComponent(
                businessId,
                )}`,
            );
            } catch (error) {
            const errorBox =
                document.querySelector(
                "#customer-edit-error",
                );

            errorBox.textContent =
                error.detail?.next_action ||
                error.message;

            errorBox.classList.add(
                "visible",
            );

            button.disabled = false;
            button.textContent =
                "重新分析";
            }
        });
    } catch (error) {
        renderLoadError(
        "客户原始资料暂时无法读取",
        error,
        );
    }
    }

  async function renderCustomerSupplement(businessId) {
    stopTaskPolling();
    skeletonPage("补充缺失信息");
    try {
      const detail = await api(
        `/api/customers/${encodeURIComponent(businessId)}`,
      );
      const requestedGap = new URLSearchParams(location.search).get("gap");
      const productionSupplement = requestedGap === "process_material";
      const constraintSupplement = requestedGap === "critical_constraints" && detail.creation_constraints?.blocked;
      const approvedSupplement = detail.status === "approved";
      if (detail.status !== "needs_more_info" && !approvedSupplement) {
        return navigate(`/customers/${encodeURIComponent(businessId)}`, true);
      }
      const gaps = productionSupplement
        ? [{
            gap_id: "process_material",
            label: "真实服务流程",
            question: "这项服务从开始到结束通常如何完成？请只填写已经确认的真实步骤，以及出镜人本人实际参与的部分。",
          }]
        : approvedSupplement ? [{gap_id: "additional_materials", label: constraintSupplement ? "主体关系与适用数据口径" : "新增客户资料", question: constraintSupplement
          ? (detail.creation_constraints.items || []).map(item => `${item.title}：${item.reason}`).join("\n")
          : "粘贴本次新增的真实业务资料。原有已批准事实保留，新事实需要单独审核；实质更正不会静默覆盖。"}] : detail.readiness_gaps || [];
      app.innerHTML = shell(
        productionSupplement ? "补充真实服务流程" : approvedSupplement ? "补充客户资料" : "补充缺失信息",
        `
          <main class="page page-form profile-mutation-page customer-gap-page">
            <div class="case-review-heading">
              <a class="back-link" href="/customers/${encodeURIComponent(businessId)}" data-route>← 返回客户详情</a>
              ${customerStatusPill(detail.status)}
            </div>
            ${pageHeading(
              productionSupplement ? "可选的创作解锁路径" : "客户已创建",
              productionSupplement ? "补充真实服务流程" : constraintSupplement ? "补充核实资料" : approvedSupplement ? "补充客户资料" : "补充缺失信息",
              constraintSupplement ? "请提供可核实的主体关系及数据适用范围。补充将进入现有资料分析和人工审核，不会自动解除限制或覆盖已批准档案。" : productionSupplement || approvedSupplement
                ? `这不会改变当前客户档案的完整性判断；补充内容仍需人工审核，并形成“${detail.display_name}”的新档案版本。`
                : `还差 ${gaps.length} 类信息，就可以确认“${detail.display_name}”的客户档案。`,
            )}
            <section class="work-surface profile-form-surface">
              <form id="customer-gap-form" novalidate>
                <div class="gap-question-list">
                  ${gaps.map((gap, index) => `
                    <div class="field gap-question" data-gap-id="${escapeHtml(gap.gap_id)}">
                      <label for="customer-gap-${index}">${escapeHtml(gap.label)}</label>
                      <p class="field-prompt">${escapeHtml(gap.question)}</p>
                      <textarea id="customer-gap-${index}" rows="5" maxlength="12000" placeholder="填写你已经确认的真实信息"></textarea>
                    </div>`).join("")}
                </div>
                <div id="customer-gap-error" class="form-error" role="alert"></div>
                <div class="profile-form-actions">
                  <button class="btn btn-primary btn-wide" type="submit">补充并继续</button>
                  ${approvedSupplement && !productionSupplement ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}" data-route>返回客户</a>` : productionSupplement
                    ? `<a class="btn btn-secondary" href="/create?business_id=${encodeURIComponent(businessId)}" data-route>返回创作</a>`
                    : `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}/speakers/new" data-route>先添加出镜人资料</a>`}
                </div>
                <div class="secondary-link-row">
                  ${!approvedSupplement ? `<a href="/customers/${encodeURIComponent(businessId)}/edit" data-route>编辑完整资料</a>` : ""}
                  <a href="/customers" data-route>稍后处理</a>
                </div>
              </form>
            </section>
          </main>`,
      );
      bindCommonActions();
      document.querySelector("#customer-gap-form").addEventListener(
        "submit",
        async (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const answers = [...form.querySelectorAll("[data-gap-id]")]
            .map((field) => ({
              target_gap: field.dataset.gapId,
              raw_answer: field.querySelector("textarea").value.trim(),
            }))
            .filter((item) => item.raw_answer);
          const errorBox = document.querySelector("#customer-gap-error");
          if (!answers.length) {
            errorBox.textContent = "请至少补充一项真实信息。";
            errorBox.classList.add("visible");
            return;
          }
          errorBox.classList.remove("visible");
          const button = form.querySelector('button[type="submit"]');
          button.disabled = true;
          button.textContent = "正在提交…";
          try {
            const result = await api(
              `/api/customers/${encodeURIComponent(businessId)}/gaps/supplement`,
              {
                method: "POST",
                body: JSON.stringify({ answers }),
              },
            );
            navigate(`/customers/${encodeURIComponent(businessId)}`);
          } catch (error) {
            errorBox.textContent = error.detail?.next_action || error.message;
            errorBox.classList.add("visible");
            button.disabled = false;
            button.textContent = "补充并继续";
          }
        },
      );
    } catch (error) {
      renderLoadError("缺失信息暂时无法读取", error);
    }
  }

  function renderFailedCustomer(detail) {
    app.innerHTML = shell(
        "客户信息分析失败",
        `
        <main class="page page-form customer-intake-page customer-failed-page">
            <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
                ← 返回客户列表
            </a>
            ${customerStatusPill("failed")}
            </div>

            ${pageHeading(
            "",
            detail.display_name,
            "上一次客户信息分析没有完成，已经录入的资料仍然保留。",
            )}
            ${intakeSteps(2)}

            <section class="panel needs-info-state">
            <h2>分析没有完成</h2>
            <p>
                ${escapeHtml(
                detail.task?.error_message ||
                    "模型调用或分析过程没有完成。",
                )}
            </p>

            <div class="customer-recovery-actions">
                <button
                id="retry-customer-analysis"
                class="btn btn-primary"
                type="button"
                >
                继续分析
                </button>

                <a
                class="btn btn-secondary"
                href="/customers/${encodeURIComponent(
                    detail.business_id,
                )}/edit"
                data-route
                >
                修改资料后重新分析
                </a>
            </div>
            </section>

        </main>`,
    );

    bindCommonActions();

    document
        .querySelector("#retry-customer-analysis")
        .addEventListener("click", async () => {
        const button = document.querySelector(
            "#retry-customer-analysis",
        );

        button.disabled = true;
        button.textContent = "正在继续…";

        try {
            const result = await api(
            `/api/customers/${encodeURIComponent(
                detail.business_id,
            )}/retry`,
            {
                method: "POST",
            },
            );

            const task =
            result.task ||
            result.existing_task;

            showToast("已重新开始客户信息分析");

            app.innerHTML = shell(
            "客户信息分析",
            `
            <main class="page page-form customer-intake-page customer-progress-page">
                ${pageHeading(
                    "客户",
                    detail.display_name,
                    "正在继续分析已有客户资料。",
                )}
                ${intakeSteps(2)}
                <div data-customer-progress></div>
                </main>`,
            );

            bindCommonActions();
            bindCustomerProgress(
            task,
            detail.business_id,
            );
        } catch (error) {
            showToast(
            error.detail?.next_action ||
                error.message,
            );

            button.disabled = false;
            button.textContent = "继续分析";
        }
        });
    }

  async function renderCustomerContentOperations(businessId) {
    const host = document.querySelector("[data-customer-content-operations]");
    if (!host) return;
    try {
      const [data, batches] = await Promise.all([
        api(`/api/customers/${encodeURIComponent(businessId)}/content-operations`).catch(() => null),
        api(`/api/create/batches?business_id=${encodeURIComponent(businessId)}`).catch(() => null),
      ]);
      if (!host.isConnected) return;
      host.innerHTML = batchHistoryMarkup(batches) + (data ? ContentOperationsPanel(data) : '<p class="field-hint">内容概览暂时无法可靠读取；已有批次仍可查看。</p>');
      bindCommonActions(host);
    } catch {
      if (!host.isConnected) return;
      host.innerHTML = `
        <section class="state-panel state-error content-management-inline-state">
          <h2>内容管理暂时无法读取</h2>
          <p>请稍后重试，客户资料和已有内容不会受到影响。</p>
          <a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}#content" data-route>重新加载</a>
        </section>`;
      bindCommonActions(host);
    }
  }

  function approvedCustomerPresentation(detail) {
    const correction = amendmentPanel(detail, "business", customerFieldLabel);
    const facts = (detail.business_persona?.facts || []).filter(
      (fact) => fact.state === "known",
    );
    const speakers = detail.speakers || [];
    const constraintBlocked = detail.creation_constraints?.blocked === true || detail.production_constraint_blocked === true;
    const revalidationRequired = speakers.some(speaker => speaker.status === "revalidation_required");
    const approvedSpeakers = speakers.filter(
      (speaker) => speaker.approved_for_current_business ?? speaker.status === "approved",
    );
    const pendingSpeaker = speakers.find(
      (speaker) => speaker.status !== "approved",
    );
    const analyzingSpeakers = speakers.filter(
      (speaker) => speaker.status === "analyzing",
    );
    const retrySpeaker = speakers.find(
      (speaker) => speaker.auto_handoff_status === "retry_required",
    );
    const tabs = [
      { id: "overview", label: "概览" },
      { id: "profile", label: "客户资料" },
      { id: "speakers", label: "出镜人" },
      { id: "content", label: "内容" },
      ...(constraintBlocked || detail.creation_constraints?.legacy_scope_available ? [{ id: "constraints", label: "待核实事项" }] : []),
    ];
    const primaryAction = constraintBlocked
      ? `<a class="btn btn-primary" href="#constraints" data-profile-tab="constraints">查看待核实事项</a>`
      : detail.creation_entry_ready
      ? `<a class="btn btn-primary" href="/create/config?business_id=${encodeURIComponent(detail.business_id)}" data-route>${detail.creation_constraints?.legacy_scope_available ? "检查创作条件" : "开始创作"}</a>`
      : !speakers.length
        ? `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>`
        : analyzingSpeakers.length === 1
          ? `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/${encodeURIComponent(analyzingSpeakers[0].speaker_id)}" data-route>查看出镜人进度</a>`
        : analyzingSpeakers.length > 1
          ? `<a class="btn btn-primary" href="#speakers" data-customer-tab="speakers">查看出镜人</a>`
        : pendingSpeaker
          ? `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/${encodeURIComponent(pendingSpeaker.speaker_id)}" data-route>${pendingSpeaker.status === "revalidation_required" ? "确认出镜人关联" : "确认出镜人信息"}</a>`
          : `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>`;
    const speakerContent = speakers.length
      ? `<div class="speaker-list">${speakers
          .map((speaker) => speakerCard(speaker, detail.business_id))
          .join("")}</div>`
      : `
        <section class="state-panel compact-empty-state">
          <span class="empty-icon" aria-hidden="true">＋</span>
          <h2>还没有出镜人</h2>
          <p>添加出镜人后，可以确认这个人的身份、经历和表达范围。</p>
          <a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>
        </section>`;
    const tabContent = {
      overview: `
        ${ProfileSummary([
          {
            label: "客户资料",
            value: "已确认",
            note: `${facts.length} 项有效信息`,
          },
          {
            label: "出镜人",
            value: `${speakers.length} 位`,
            note: pendingSpeaker
              ? `${speakers.length - approvedSpeakers.length} 位资料待确认`
              : `${approvedSpeakers.length} 位已确认`,
          },
          {
            label: "创作状态",
            value: constraintBlocked ? "创作受限" : detail.creation_entry_ready ? "可以检查创作内容" : "尚未就绪",
            note: constraintBlocked ? "档案已批准，仍有重要限制需要核实" : detail.creation_entry_ready
              ? "仍需检查内容机会与可行性"
              : "需要至少一位已确认出镜人",
          },
        ])}
        <section class="profile-next-action">
          <div>
            <span>下一步</span>
            <h2>${
              constraintBlocked ? "核实主体关系与适用范围" : detail.creation_entry_ready
                ? "开始准备视频内容"
                : analyzingSpeakers.length
                  ? `正在整理 ${analyzingSpeakers.length} 位出镜人信息`
                  : retrySpeaker
                    ? "继续处理出镜人信息"
                : !speakers.length
                  ? "添加第一位出镜人"
                  : "完成出镜人信息确认"
            }</h2>
            <p>${constraintBlocked ? escapeHtml(detail.creation_constraints?.items?.[0]?.title || "重要限制尚未解除，请查看待核实事项。") : revalidationRequired ? "出镜人需要确认更新后的客户信息。完成独立复核与档案确认后，再检查创作条件。" : retrySpeaker ? "客户档案已确认，出镜人信息需要继续处理。" : "系统只会在客户和出镜人信息满足条件后开放创作。"}</p>
          </div>
        </section>
        ${correction ? `<div class="profile-correction-shortcut"><span>客户信息有变化？</span><a href="#profile" data-open-customer-correction>更正客户资料 <span aria-hidden="true">→</span></a></div>` : ""}`,
      profile: `<div class="work-surface profile-document">${customerProfileSections(facts)}</div>`,
      constraints: customerConstraintPanel(detail),
      speakers: `
        <section class="profile-tab-section">
          <div class="section-head">
            <div><h2>出镜人</h2><p>管理谁可以以什么身份进行第一人称表达。</p></div>
            ${speakers.length ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>` : ""}
          </div>
          ${speakerContent}
        </section>`,
      content: `
        <section class="profile-tab-section">
          <div data-customer-content-operations aria-live="polite">
            <section class="state-panel state-loading content-management-inline-state" aria-label="正在加载内容管理">
              <span class="loading-indicator" aria-hidden="true"></span>
              <h2>正在读取内容管理</h2>
              <p>请稍候，已有内容与交付记录马上就好。</p>
            </section>
          </div>
        </section>`,
    };

    return {tabs,primaryAction,tabContent,correction};
  }

  function renderApprovedCustomer(detail) {
    const initial=approvedCustomerPresentation(detail);
    let {tabs,primaryAction,tabContent}=initial;
    const correction=initial.correction;
    const requestedTab=decodeURIComponent(location.hash.slice(1));
    let activeTab=tabs.some(tab=>tab.id===requestedTab)?requestedTab:'overview';
    const supplementAction=`<a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/supplement" data-route>补充客户资料</a>`;
    app.innerHTML = shell(
      "客户详情",
      `
        <main class="page page-standard customer-detail-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>← 返回客户</a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "",
            detail.display_name,
            detail.industry,
            `<div class="page-heading-actions" data-customer-profile-actions>${primaryAction}${supplementAction}</div>`,
          )}

          ${auditNote(detail)}
          <p class="field-hint" role="status" data-speaker-status-feedback hidden></p>
          ${ProfileTabs(tabs, activeTab)}
          <div class="profile-tab-panel" data-active-profile-tab="${escapeHtml(activeTab)}">
            ${tabContent[activeTab]}
          </div>
          ${correction}
        </main>`,
    );

    bindCommonActions();
    const panel = app.querySelector(".profile-tab-panel");
    const correctionCard = app.querySelector("[data-review-amendment]");
    const loadTab = () => {
      // Hide the retained form outside its owning tab without discarding drafts.
      if (correctionCard) correctionCard.hidden = activeTab !== "profile";
      panel?.querySelector("[data-open-customer-correction]")?.addEventListener("click", event => {
        event.preventDefault();
        if (!correctionCard) return;
        selectTab("profile");
        correctionCard.open = true;
        correctionCard.querySelector("summary")?.focus({preventScroll:true});
        correctionCard.scrollIntoView({block:"start"});
      });
      if (activeTab === "content") void renderCustomerContentOperations(detail.business_id);
      if (activeTab === "constraints") void bindLegacyScope({host: document.querySelector("[data-legacy-scope]"),
        businessId: detail.business_id, api, onSaved: () => renderCustomerDetail(detail.business_id)});
    };
    const selectTab = next => {
      if (!panel || next === activeTab || !tabs.some(item => item.id === next)) return;
      activeTab = next;
      history.replaceState({}, "", `${location.pathname}#${next}`);
      // Keep correction drafts and pending recovery controls in the same DOM.
      panel.dataset.activeProfileTab = next;
      panel.innerHTML = tabContent[next];
      document.querySelectorAll(".profile-tabs [data-profile-tab]").forEach(link => {
        const selected = link.dataset.profileTab === next;
        link.classList.toggle("active", selected);
        if (selected) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      bindCommonActions(panel);
      loadTab();
    };
    loadTab();
    document.querySelectorAll("[data-profile-tab]").forEach((tab) => {
      tab.addEventListener("click", (event) => {
        event.preventDefault();
        selectTab(tab.dataset.profileTab);
      });
    });
    const page=app.querySelector('.customer-detail-page');
    const route=location.pathname;
    const feedback=app.querySelector('[data-speaker-status-feedback]');
    stopPolling=watchCustomerSpeakerTasks({detail,api,
      isCurrent:()=>location.pathname===route && app.querySelector('.customer-detail-page')===page,
      onDetail(next){
        // A concurrent Business revision needs an explicit re-read, not a silent
        // replacement of the source behind a correction draft or review command.
        if(['business_persona','current_business_persona','latest_intake_id','creation_constraints'].some(key=>JSON.stringify(next[key])!==JSON.stringify(detail[key]))) {
          stopTaskPolling();
          if(feedback) {feedback.textContent='客户资料已变化，请刷新后重新核对。';feedback.hidden=false;}
          return;
        }
        ({tabs,primaryAction,tabContent}=approvedCustomerPresentation(next));
        const actions=app.querySelector('[data-customer-profile-actions]');
        if(actions) {actions.innerHTML=primaryAction+supplementAction;bindCommonActions(actions);}
        if(['overview','speakers'].includes(activeTab)) {
          panel.innerHTML=tabContent[activeTab];bindCommonActions(panel);loadTab();
        }
        if(feedback) {feedback.textContent='';feedback.hidden=true;}
      },
      onError(error){
        if(feedback) {feedback.textContent=error.detail?.next_action || error.message || '出镜人状态暂时无法读取，请稍后刷新。';feedback.hidden=false;}
      },
    });
  }

  function renderNeedsMoreInfo(detail) {
    const gaps = detail.readiness_gaps || [];
    const speakers = detail.speakers || [];
    const confirmed = (detail.reviewed_fact_candidates || []).filter(
      (item) => item.state === "known_candidate" && item.value != null,
    );

    app.innerHTML = shell(
      "客户信息待处理",
      `
        <main class="page customer-needs-info-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户列表
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "客户已创建",
            detail.display_name,
            `${detail.industry} · 信息待处理`,
          )}
          ${ProfileSummary([
            {
              label: "当前状态",
              value: "客户事实已保存",
              note: "客户档案尚未批准",
            },
            {
              label: "待处理信息",
              value: `${gaps.length} 类`,
              note: "补充后继续确认档案",
            },
            {
              label: "已收集信息",
              value: `${confirmed.length} 项`,
              note: "已有确认不会重新审核",
            },
            {
              label: "出镜人资料",
              value: `${speakers.length} 位`,
              note: speakers.length ? "查看下方人物资料" : "可以先并行添加",
            },
          ])}
          <section class="panel needs-info-state">
            <span class="state-icon state-icon-warning" aria-hidden="true">!</span>
            <div>
              <h2>客户事实已保存，仍有信息需要处理</h2>
              <p>请按下方原因处理；之前已经核对的信息会继续保留。</p>
              <p class="muted-copy">完成客户档案确认，并确认至少一位出镜人后，可以进入创作检查。仍需检查内容机会与可行性。</p>
              <div class="needs-info-list">
                <span>需要处理：</span>
                <ul>${gaps.map((gap) => `<li><strong>${escapeHtml(gap.label)}</strong><p>${escapeHtml(gap.explanation || "请核实资料来源及审核状态。")}</p></li>`).join("")}</ul>
              </div>
              <div class="needs-info-actions">
                ${detail.saved_source_recovery?.available ? '<button class="btn btn-secondary" type="button" data-recover-saved-source>使用已保存资料补齐识别</button>' : ""}
                <a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/supplement" data-route>补充真实资料</a>
                <a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人资料</a>
                ${detail.legacy_readiness_recheck_available ? '<button class="btn btn-secondary" type="button" data-needs-info-action="recheck-readiness">重新检查现有资料</button>' : ""}
              </div>
              <div class="secondary-link-row">
                <a href="/customers/${encodeURIComponent(detail.business_id)}/edit" data-route>查看已保存原文</a>
                <a href="/customers" data-route>稍后处理</a>
              </div>
            </div>
          </section>
          ${speakers.length ? `
            <section class="profile-tab-section">
              <div class="section-head"><div><h2>已保存的出镜人资料</h2><p>客户档案确认后，可以直接继续确认出镜人。</p></div></div>
              <div class="speaker-list">${speakers.map((speaker) => speakerCard(speaker, detail.business_id)).join("")}</div>
            </section>` : ""}
        </main>`,
    );

    bindCommonActions();
    document
      .querySelector('[data-needs-info-action="recheck-readiness"]')
      ?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = "正在检查…";
        try {
          const result = await api(
            `/api/customers/${encodeURIComponent(detail.business_id)}/readiness/recheck`,
            { method: "POST" },
          );
          if (result.review.status === "completed_persona_review_required") {
            showToast("现有资料已满足要求，请确认客户档案。");
          } else {
            showToast("现有资料仍不足，请按提示补充。");
          }
          renderCustomerDetail(detail.business_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "重新检查现有资料";
        }
      });
    document.querySelector("[data-recover-saved-source]")?.addEventListener("click", async event => {
      const button = event.currentTarget;
      button.disabled = true;
      const source = detail.saved_source_recovery;
      try {
        const result = await api(`/api/customers/${encodeURIComponent(detail.business_id)}/intake/recover`, {
          method: "POST", body: JSON.stringify({source_intake_id: source.source_intake_id,
            targets: source.targets, execution_identity: `saved-source-${source.raw_sha256.slice(0,32)}`}),
        });
        const task = result.task || result.existing_task;
        showToast(result.replayed ? "此份资料已发起补齐识别，请查看原任务。" : "正在补齐识别已有资料；新增信息仍需人工核对。");
        if (task && ["queued", "running"].includes(task.status)) {
          stopPolling = startTaskPolling({api, taskId: task.task_id, onUpdate() {}, onDone() {renderCustomerDetail(detail.business_id);}});
        }
        renderCustomerDetail(detail.business_id);
      } catch (error) {showToast(error.detail?.next_action || error.message); button.disabled = false;}
    });
  }

  function bindDiscoveryRetry(detail) {
    document.querySelector("[data-retry-person-discovery]")?.addEventListener("click", async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const result = await api(`/api/customers/${encodeURIComponent(detail.business_id)}/speaker-discovery/retry`, {method: "POST"});
        const task = result.task || result.existing_task;
        if (!task) return renderCustomerDetail(detail.business_id);
        const host = document.querySelector("[data-person-discovery-progress]");
        if (host) host.innerHTML = '<p>正在查找可能的出镜人；客户事实不会重新整理。可以离开后继续查看。</p>';
        stopPolling = startTaskPolling({api, taskId: task.task_id, onUpdate() {}, onDone() {renderCustomerDetail(detail.business_id);}});
      } catch(error) {showToast(error.message); button.disabled = false;}
    });
  }

  function renderDiscoveryRecovery(detail) {
    if (!detail.speaker_discovery_status && !detail.speaker_confirmation?.retry_required) return;
    const page = document.querySelector("main");
    page?.insertAdjacentHTML("beforeend", `
      <section class="work-surface" data-discovery-recovery>
        ${detail.speaker_confirmation?.retry_required ? '<h2>客户信息已保存</h2><p>出镜人资料暂未建立成功，可以继续处理。</p>' : ""}
        ${discoveryPanel(detail)}
        ${(detail.speaker_candidates || []).some(item => !item.confirmed) ? '<button class="btn btn-secondary" data-retry-discovery>继续添加出镜人</button>' : ""}
      </section>`);
    bindDiscoveryRetry(detail);
    document.querySelector("[data-retry-discovery]")?.addEventListener("click", async event => {
      const button = event.currentTarget;
      button.disabled = true;
      const decisions = (detail.speaker_candidates || []).filter(item => !item.confirmed).map(candidate => {
        const row = document.querySelector(`[data-speaker-candidate="${CSS.escape(candidate.candidate_id)}"]`);
        return { candidate_id: candidate.candidate_id,
          selected: row?.querySelector("[data-speaker-select]")?.checked === true,
          speaker_name: row?.querySelector("[data-speaker-name]")?.value.trim() || null,
          public_role: row?.querySelector("[data-speaker-role]")?.value.trim() || null,
          speaker_type: row?.querySelector("[data-speaker-type]")?.value || null };
      });
      try {
        const result = await api(`/api/customers/${encodeURIComponent(detail.business_id)}/speaker-discovery/confirm`,
          {method: "POST", body: JSON.stringify({decisions})});
        showToast(result.speaker_confirmation.retry_required ? "仍需补充出镜人身份或稍后重试。" : "出镜人资料已保存。仍需独立审核本人经历。");
        renderCustomerDetail(detail.business_id);
      } catch(error) { showToast(error.message); button.disabled = false; }
    });
  }

  async function renderCustomerDetail(businessId) {
    stopTaskPolling();
    skeletonPage("客户详情");

    let detail = null;
    const pending = await api(`/api/review-commands/business/${encodeURIComponent(businessId)}`).catch(()=>({operations:[]}));
    try {
      detail = await api(
        `/api/customers/${encodeURIComponent(businessId)}`,
      );

      if (detail.creation_constraints?.blocked && detail.status !== "approved" && location.hash === "#constraints") {
        app.innerHTML = shell("客户待核实事项", `<main class="page page-standard customer-detail-page">
          <a class="back-link" href="/customers/${encodeURIComponent(businessId)}" data-route>← 返回客户详情</a>
          ${pageHeading("", detail.display_name, "核实具体限制后，再按原流程继续。")}${customerConstraintPanel(detail)}</main>`);
        bindCommonActions();
        void bindLegacyScope({host: document.querySelector("[data-legacy-scope]"), businessId, api,
          onSaved: () => renderCustomerDetail(businessId)});
        return;
      }
      if (
        detail.status === "analyzing" &&
        detail.task
      ) {
        app.innerHTML = shell(
          "客户信息分析",
          `
            <main class="page page-form customer-intake-page customer-progress-page">
              ${pageHeading(
                "客户",
                detail.display_name,
                "正在把已有资料整理成待确认事实。",
              )}
              ${intakeSteps(2)}
              ${detail.current_business_persona?.approved ? '<p class="result-banner">新资料正在整理；原有已批准客户资料继续有效。</p>' : ""}
              <div data-customer-progress></div>
            </main>`,
        );

        bindCommonActions();
        bindCustomerProgress(detail.task, businessId);
        return;
      }

      if (detail.status === "failed") {
        return renderFailedCustomer(detail);
        }
      if (detail.status === "fact_review_required") {
        return renderFactReview(detail);
      }

      if (detail.status === "persona_review_required") {
        if (detail.unified_confirmation_enabled) return renderFactReview(detail);
        renderPersonaReview(detail);
        renderDiscoveryRecovery(detail);
        return;
      }

      if (detail.status === "approved") {
        renderApprovedCustomer(detail);
        renderDiscoveryRecovery(detail);
        return;
      }

      if (detail.status === "needs_more_info") {
        renderNeedsMoreInfo(detail);
        renderDiscoveryRecovery(detail);
        return;
      }

      if (detail.status === "draft") {
        app.innerHTML = shell("客户已保存", `<main class="page page-form smart-profile-page">${intakeSteps(1)}
          ${pageHeading("客户已保存", detail.display_name, "尚未提交可分析资料，可以稍后继续。")}
          <section class="work-surface"><p>行业暂不确定，没有资料时不会启动分析。</p>
          <a class="btn btn-primary" href="/customers/${encodeURIComponent(businessId)}/edit" data-route>继续填写资料</a>
          <a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}/speakers/new" data-route>先保存出镜人资料</a></section></main>`);
        bindCommonActions(); return;
      }

      app.innerHTML = shell(
        "客户详情",
        `
          <main class="page">
            ${pageHeading(
              "客户",
              detail.display_name,
              "当前客户流程尚未到达可审核状态。",
            )}
            <section class="card notice-card">
              <h2>正在准备客户信息</h2>
              <p>当前还没有可审核内容，请稍后再回来查看。</p>
            </section>
          </main>`,
      );

      bindCommonActions();
    } catch (error) {
      renderLoadError("客户暂时无法读取", error);
    } finally {
      if (detail && ["approved", "persona_review_required", "binding_review_required", "needs_more_info"].includes(detail.status)) {
        if (detail.status !== "approved") app.querySelector("main")?.insertAdjacentHTML("beforeend", amendmentPanel(detail,"business",customerFieldLabel));
        bindAmendment(app, detail, "business", {api, reload:()=>renderCustomerDetail(businessId)});
      }
      mountRecovery(app, api, pending.operations, ()=>renderCustomerDetail(businessId));
      const reviewPage = app.querySelector?.('.customer-review-page');
      if (reviewPage) enhanceReviewDisclosures(reviewPage);
    }
  }

  function renderCustomerTaskDetail(task) {
    stopTaskPolling();

    const businessId = task.subject_ref;

    app.innerHTML = shell(
      "任务进度",
      `
        <main class="page page-form task-detail-page customer-intake-page customer-progress-page">
          ${pageHeading(
            "任务进度",
            task.payload?.customer_name || "客户信息分析",
            "正在从已有客户资料中提取待确认事实。你可以离开这个页面。",
          )}
          ${intakeSteps(2)}
          <div data-customer-progress>
            ${customerProgressPanel(task)}
          </div>
        </main>`,
    );

    bindCommonActions();
    bindCustomerProgress(task, businessId);
  }

  return {
    renderCustomers,
    renderCustomerNew,
    renderCustomerEdit,
    renderCustomerSupplement,
    renderCustomerDetail,
    renderCustomerTaskDetail,
    stopTaskPolling,
    };
}
