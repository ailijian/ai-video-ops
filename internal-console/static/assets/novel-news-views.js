import { startTaskPolling } from "./task-progress.js";
import { bindContentReviewControls, ContentReviewItem, ContentReviewList, CreationCapacityState, CreationHeader, CreationState, CreationStepper, safeCreationMessage } from "./creation-components.js?v=news-review-ui-2";

export function createNovelNewsViews({ api, showToast, escapeHtml }) {
  function roleLabel(role) {
    return ({
      price_offer_first_semantic_anchor: "价格与适用条件",
      included_value_context: "包含内容",
      service_context: "服务信息",
      trust_context: "信任信息",
      price_scope_information: "价格范围",
      state_a: "已确认的状态 A",
      state_b: "已确认的状态 B",
    })[role] || "";
  }

  function freshKey() {
    return globalThis.crypto?.randomUUID?.() || `novel_news_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  }

  async function watch(task, requestId, host, message) {
    showToast("已进入后台，离开页面后也可以恢复。 ");
    await restore(requestId, host);
    startTaskPolling({
      api, taskId: task.task_id,
      onUpdate: () => {},
      onDone: async (current) => {
        await restore(requestId, host);
        showToast(current.status === "completed" ? message : safeCreationMessage(current.error_message, "后台任务未完成，请重试。"));
      },
      onError: () => {},
    });
  }

  function renderPreview(host, projection, { businessId, speakerId, requestedQuantity = 1, createPreparation }) {
    const opportunities = (projection.opportunities || []).filter((item) => item.novelty_status === "novel");
    if (!opportunities.length) {
      host.innerHTML = CreationState({ title: "当前没有可用的新内容方向", body: projection.opportunities?.length
        ? "已讲过的价格内容不会换一种形式后再算作新内容。可以选择“重新表达已有内容”，或补充真实客户信息。"
        : "本次没有可用的已核实价格或优惠信息。请先补充并核对价格及适用条件，再检查新闻体内容方向。" });
      return;
    }
    const supported = opportunities.filter((item) => item.production_feasibility?.status === "supported");
    const canContinue = requestedQuantity === 1 && Number(projection.production_ready_count || 0) > 0 && supported.length > 0;
    const selected = supported[0];
    const details = `<details class="creation-evidence"><summary>查看内容方向</summary>
      <div class="news-source-list">${opportunities.map((item) => `<label class="news-source-row">
        <input type="radio" name="novel-opportunity" value="${escapeHtml(item.concept_id)}" ${item === selected ? "checked" : ""} ${item.production_feasibility?.status !== "supported" ? "disabled" : ""}>
        <span><strong>${escapeHtml(item.central_claim)}</strong>${item.why_publish ? `<small>${escapeHtml(item.why_publish)}</small>` : ""}</span>
        ${item.production_feasibility?.status !== "supported" ? "<em>当前结构暂不支持</em>" : ""}
      </label>`).join("")}</div></details>`;
    host.innerHTML = canContinue ? CreationCapacityState({
      requested: requestedQuantity, available: opportunities.length, confirmed: 1, details,
      actions: `<button type="button" class="btn btn-primary" data-confirm-novel>开始本次创作（1 条）</button>`,
    }) : CreationState({ tone: "warning", title: `当前有 ${opportunities.length} 个值得做的内容方向`,
      body: "当前结构暂不支持本次创作，请核对数量和适用的创作结构。", content: details });
    const button = host.querySelector("[data-confirm-novel]");
    let resume;
    button?.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "正在确认…";
      try {
        if (!resume) {
          const selectedId = host.querySelector('input[name="novel-opportunity"]:checked')?.value;
          if (!supported.some((item) => item.concept_id === selectedId) || typeof createPreparation !== "function") {
            throw new Error("请重新检查当前创作条件后再确认。");
          }
          resume = createPreparation({
            business_id: businessId, speaker_id: speakerId,
            profile: "news", requested_quantity: 1, confirmed_quantity: 1,
            selected_opportunity_id: selectedId,
            idempotency_key: freshKey(),
          });
        }
        await resume();
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "无法确认这个内容方向。"));
        if (button.isConnected) { button.disabled = false; button.textContent = "开始本次创作（1 条）"; }
      }
    });
  }

  function reviewHtml(state) {
    const beats = state.beats || [];
    const rows = beats.map((beat, index) => ContentReviewItem({
      namespace: "novel-review", itemId: beat.beat_id, index: index + 1,
      eyebrow: roleLabel(beat.semantic_role), title: beat.text, editorMode: "news",
      editorTitleLabel: "修改后的短信息", showReviewNote: false,
      evidenceLabel: "查看来源事实",
      evidenceRows: (beat.source_fact_refs || []).map((ref) => ({label: "来源事实", value: state.source_facts?.[ref] || ""})),
      rejectDisabled: beat.semantic_role === "price_offer_first_semantic_anchor",
      rejectReason: "价格及其适用条件必须保留。",
    }));
    return `<section class="work-surface creation-section content-review-surface">
      ${CreationHeader({ title: "核对本条视频的短信息", description: "默认选择通过，需调整时选择修改或不采用；核对后统一提交审核。" })}
      <div class="content-review-progress" data-novel-review-progress></div>
      ${ContentReviewList(rows)}
      <div class="creation-action-bar">
        <button type="button" class="btn btn-primary" data-submit-novel-review disabled>提交审核</button>
      </div>
      <p class="creation-governance-line">本条视频需保留 4–8 段短信息，价格及其适用条件必须保留；所有内容均须有已确认事实作为依据。</p>
    </section>`;
  }

  async function restore(requestId, host) {
    let state;
    try {
      state = (await api(`/api/create/novel-news/${encodeURIComponent(requestId)}/state`)).state;
    } catch (error) {
      host.innerHTML = CreationState({ tone: "error", title: "无法恢复新闻体进度", body: safeCreationMessage(error.detail?.next_action || error.message, "请稍后重试。") });
      return;
    }
    const index = ({ source_plan: 0, generation: 1, review: 2, export: 3, completed: 4, blocked: 0 })[state.stage] ?? 0;
    const title = ({ source_plan: "准备创作来源", generation: "生成新闻体", review: "审核新闻体", export: "准备导出", completed: "新闻体已完成", blocked: "当前结构暂不支持" })[state.stage];
    let body = "";
    if (state.export_recovery_state === "legacy_unbound_orphan") {
      body = CreationState({ tone: "warning", title: "导出结果需要重新核对。", body: "原文件和记录已保留，请交由有权人员核对。" });
    } else if (state.stage === "blocked") {
      body = state.generation?.recovery_state === 'source_or_authorization_conflict'
        ? CreationState({ tone: "warning", title: "来源或授权已变化", body: "当前生成操作已阻断。请重新核对客户、价格条件和创作参考；原记录会保留。" })
        : CreationState({ tone: "warning", title: "有内容值得讲，但现有结构暂不支持", body: safeCreationMessage(state.source_coverage?.humanized_reason || state.source_coverage?.reason, "请稍后重试或返回调整。") });
    } else if (state.stage === "source_plan") {
      body = CreationState({ title: "创作准备尚未完成", body: "原请求已保留，请继续完成来源准备。", actions: `<button class="btn btn-primary" data-novel-action="sources">继续准备</button>` });
    } else if (state.stage === "generation") {
      const generation = state.generation || {};
      if (generation.task_running) {
        body = CreationState({ title: "正在生成新闻体", body: "可以稍后刷新查看进度，系统不会重复发起原模型调用。", actions: `<button class="btn" data-novel-action="refresh">刷新进度</button>` });
      } else if (generation.recovery_state === "dispatched_outcome_unknown") {
        body = CreationState({ tone: "warning", title: "模型执行结果无法确认", body: generation.legacy_unbound
          ? "旧版生成缺少可信尝试记录。原结果已保留，请交由有权人员核对；系统不会自动重复生成。"
          : "本次模型调用可能已经执行，系统不会自动重复生成。你可以稍后刷新查看结果，或在确认后重新尝试；重新尝试可能产生额外模型费用。", actions: `${generation.legacy_unbound ? "" : `<label><input type="checkbox" data-novel-retry-consent> 我已了解原调用可能已执行，再次尝试可能产生额外费用</label><button class="btn btn-primary" data-novel-action="retry-generation" disabled>重新尝试生成</button>`}<button class="btn" data-novel-action="refresh">刷新进度</button>` });
      } else if (generation.recovery_state === "confirmed_failure") {
        body = CreationState({ tone: "warning", title: "已确认生成结果未通过校验", body: "原响应和失败记录已保留。重新尝试会发起新的模型调用，可能产生额外费用。", actions: `<label><input type="checkbox" data-novel-retry-consent> 我确认重新尝试生成，可能产生额外费用</label><button class="btn btn-primary" data-novel-action="retry-generation" disabled>重新尝试生成</button>` });
      } else {
        const prepared = generation.recovery_state === "validated_result_unpublished";
        body = CreationState({ title: prepared ? "模型响应已保存，正在恢复结果" : "准备完成", body: prepared ? "继续原操作将复用已保存的响应，不会重新调用模型。" : "已核对创作依据，可以生成本次文案；生成后仍需人工审核。", actions: `<button class="btn btn-primary" data-novel-action="generate">${prepared ? "继续完成原操作" : "生成文案"}</button>` });
      }
    } else if (state.stage === "review") {
      body = reviewHtml(state);
    } else if (state.stage === "export") {
      body = CreationState({ title: "审核完成", body: state.export_recovery_state && state.export_recovery_state !== "xlsx_not_generated" ? "导出尚未完成，可继续原操作。" : "将按顺序导出标题1…标题N，并分别记录新内容语义历史与新闻体呈现历史。", actions: `<button class="btn btn-primary" data-novel-action="export">${state.export_recovery_state && state.export_recovery_state !== "xlsx_not_generated" ? "继续完成原操作" : "导出新闻体 Excel"}</button>` });
    } else {
      body = CreationState({ tone: "success", title: "新闻体已完成", body: "新内容与本次呈现已分别登记。", actions: `<a class="btn btn-primary" href="/api/create/novel-news/${encodeURIComponent(requestId)}/excel">下载 Excel</a>` });
    }
    host.innerHTML = `<section class="work-surface creation-workflow-header">
      ${CreationHeader({ eyebrow: "新闻体 · 创作新内容", title, description: "按选题、文案、审核和导出完成本次创作；一条视频包含 4–8 段短信息。" })}
      ${CreationStepper({ steps: ["选题", "文案", "审核", "导出"], currentIndex: index })}
    </section>${body}`;
    if (state.stage === "review") bindContentReviewControls(host, {
      progressSelector: "[data-novel-review-progress]", submitSelector: "[data-submit-novel-review]",
    });
    host.querySelector('[data-novel-retry-consent]')?.addEventListener('change', (event) => {
      host.querySelector('[data-novel-action="retry-generation"]').disabled = !event.currentTarget.checked;
    });
    host.querySelector("[data-submit-novel-review]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      if (button.disabled) return;
      const decisions = [];
      for (const row of host.querySelectorAll("[data-content-review-item]")) {
        const decision = row.querySelector("input[data-content-decision]:checked")?.value;
        if (!decision) return;
        const text = row.querySelector("[data-revised-title]")?.value || "";
        if (decision === "revised" && (!text.trim() || text.length > 200)) {
          showToast("修改后的短信息需为 1–200 个字符。");
          return;
        }
        decisions.push({ beat_id: row.dataset.itemId, decision, revised_text: text || null });
      }
      const kept = decisions.filter((item) => item.decision !== "rejected").length;
      if (kept < 4 || kept > 8) { showToast("本条视频需保留 4–8 段短信息，请调整审核选择。"); return; }
      button.disabled = true;
      button.dataset.reviewSubmitting = "true";
      button.textContent = "正在保存审核结果…";
      try {
        await api(`/api/create/novel-news/${encodeURIComponent(requestId)}/review`, {
          method: "POST", body: JSON.stringify({ decisions }),
        });
        await restore(requestId, host);
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "审核未通过，请核对修改文本与来源事实。"));
        button.disabled = false;
        button.dataset.reviewSubmitting = "false";
        button.textContent = "提交审核";
      }
    });
    host.querySelectorAll("[data-novel-action]").forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const operation = button.dataset.novelAction;
        if (operation === 'refresh') {
          await restore(requestId, host);
        } else if (operation === "sources") {
          await api(`/api/create/${encodeURIComponent(requestId)}/resolve-sources`, { method: "POST" });
          await restore(requestId, host);
        } else {
          const response = await api(`/api/create/novel-news/${encodeURIComponent(requestId)}/${operation}`, { method: "POST",
            ...(operation === 'retry-generation' ? { body: JSON.stringify({ parent_intent_sha256: state.generation.intent_sha256,
              confirmation: 'retry_unknown_generation_with_possible_additional_cost' }) } : {}) });
          if (response.accepted === false) await restore(requestId, host);
          else await watch(response.task, requestId, host, ["generate", "retry-generation"].includes(operation) ? "新闻体文案已生成，请审核。" : "新闻体已导出。 ");
        }
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前操作未完成。"));
        if (button.isConnected) button.disabled = false;
      }
    }));
  }

  return { renderPreview, restore };
}
