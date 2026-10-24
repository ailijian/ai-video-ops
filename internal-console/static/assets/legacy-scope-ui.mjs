import {escapeHtml} from "./case-components.js?v=flow-closure-2";
import {formatConsoleTime} from "./ui-format.mjs?v=ui-1";

const labels = {
  external_claims_only: "仅外部关联主张待核实",
  core_identity_unresolved: "当前客户核心身份也有未解决问题",
  insufficient_evidence: "证据不足，保持当前阻断",
};

function claimSummary(value) {
  if (Array.isArray(value?.claims)) return `${value.entity || "来源主体"}：${value.claims.join("、")}（尚未核实适用范围）`;
  if (value?.speaker_or_source_entity) return `来源：${value.speaker_or_source_entity}。与${value.target_business || "当前客户"}的关系及数据适用范围尚待核实。`;
  return typeof value === "string" ? value : "请结合原始来源核对这项未批准主张。";
}

function receiptMarkup(receipt, current = false) {
  return `<div class="${current ? "result-banner" : "legacy-scope-history"}"><strong>${current ? "当前有效范围：" : "历史决定："}${escapeHtml(labels[receipt.decision])}</strong>
    <p>${escapeHtml(receipt.reason)}</p><p>主体关系仍未核实。${escapeHtml(formatConsoleTime(receipt.at))}</p>
    <details><summary>查看裁决收据</summary><p class="legacy-scope-hash">${escapeHtml(receipt.sha256)}</p>
    <p>审核身份：${escapeHtml(receipt.actor.namespace)} / ${receipt.actor.user_id}</p></details></div>`;
}

export function scopeReviewMarkup(data) {
  return data.items.map((item, index) => `<section class="legacy-scope-item">
    <details><summary>查看原始来源与受影响主张</summary>
      ${item.groups.length ? item.groups.map(group => `<h3>${escapeHtml(group.raw_answer_ref)}</h3>
        <p class="legacy-scope-source">${escapeHtml(group.source_text)}</p>
        <ul>${group.claims.map(claim => `<li><strong>${escapeHtml(claim.id)}</strong>：${escapeHtml(claimSummary(claim.value))}</li>`).join("")}</ul>`).join("")
        : '<p>当前资料尚不满足历史范围裁决条件，请补充针对性证据，原限制继续保留。</p>'}
      <p class="field-hint">来源记录：${escapeHtml(item.target.source_intake_id)} · 限制：${escapeHtml(item.target.constraint_id)}</p>
      <p class="field-hint legacy-scope-hash">原限制 SHA：${escapeHtml(item.target.constraint_sha256)}</p>
    </details>
    ${item.receipts.length ? receiptMarkup(item.receipts.at(-1), true) : ""}
    ${item.receipts.length > 1 ? `<details><summary>历史范围裁决（${item.receipts.length - 1}）</summary>${item.receipts.slice(0,-1).map(receipt => receiptMarkup(receipt)).join("")}</details>` : ""}
    ${data.can_adjudicate && item.eligible ? `<form data-legacy-scope-form="${index}" class="form-stack">
      <h3>人工判断限制范围</h3>
      <label class="field">受影响来源<select name="source" required><option value="">请选择已核对的来源</option>${item.groups.map((g, i) => `<option value="${i}">${escapeHtml(g.raw_answer_ref)} · ${escapeHtml(g.claims.map(v => v.id).join("、"))}</option>`).join("")}</select></label>
      <label class="field">范围裁决<select name="decision">${Object.entries(labels).reverse().map(([key, label]) => `<option value="${key}">${escapeHtml(label)}</option>`).join("")}</select></label>
      <label class="field">明确禁用的名称和主张词句（每行一项，须来自所选原文）<textarea name="blocked_terms" rows="4"></textarea></label>
      <label class="field">裁决理由<textarea name="reason" rows="3" maxlength="2000" required></textarea></label>
      <p class="field-hint">选择“仅外部关联主张待核实”不会确认双方关系，也不会自动生成内容。其余生产条件仍须检查。</p>
      <button class="btn btn-primary" type="submit">确认范围并保存裁决</button>
      <p data-scope-feedback role="status" aria-live="polite"></p>
    </form>` : '<p class="field-hint">限制范围由明确授权的客户审核人裁决；提交资料或选择不使用，均不会自行解除阻断。</p>'}
  </section>`).join("");
}

export async function bindLegacyScope({host, businessId, api, onSaved}) {
  if (!host) return;
  host.innerHTML = '<p role="status">正在读取来源与审核资格…</p>';
  try {
    const data = await api(`/api/customers/${encodeURIComponent(businessId)}/legacy-scope`);
    if (!host.isConnected) return;
    host.innerHTML = scopeReviewMarkup(data);
    host.querySelectorAll("[data-legacy-scope-form]").forEach(form => {
      let pending = null;
      form.elements.source.addEventListener("change", () => {
        const item = data.items[Number(form.dataset.legacyScopeForm)];
        const group = item.groups[Number(form.elements.source.value)];
        if (group && form.elements.source.value !== "") form.elements.blocked_terms.value = group.required_terms.join("\n");
      });
      form.addEventListener("input", () => {pending = null;});
      form.addEventListener("submit", async event => {
        event.preventDefault();
        const feedback = form.querySelector("[data-scope-feedback]");
        const button = form.querySelector("button");
        const item = data.items[Number(form.dataset.legacyScopeForm)];
        const group = item.groups[Number(form.elements.source.value)];
        if (!group || form.elements.source.value === "") return;
        pending ||= {target: item.target, raw_answer_refs: [group.raw_answer_ref], context_sha256: group.context_sha256,
          decision: form.elements.decision.value, reason: form.elements.reason.value.trim(),
          blocked_terms: form.elements.blocked_terms.value.split(/\r?\n/).map(v => v.trim()).filter(Boolean),
          operation_id: crypto.randomUUID().replaceAll("-", "")};
        button.disabled = true; feedback.textContent = "正在保存人工裁决…";
        try {
          await api(`/api/customers/${encodeURIComponent(businessId)}/legacy-scope`, {method: "POST", body: JSON.stringify(pending)});
          feedback.textContent = "裁决收据已保存，正在重新检查当前限制。";
          await onSaved();
        } catch (error) {
          feedback.textContent = error.detail?.next_action || error.message || "未能确认保存结果，请重试同一次提交。";
          button.disabled = false;
        }
      });
    });
  } catch (error) {
    if (host.isConnected) host.innerHTML = `<p role="alert">来源与审核资格暂时无法读取。请刷新重试；现有限制保持有效。</p>`;
  }
}
