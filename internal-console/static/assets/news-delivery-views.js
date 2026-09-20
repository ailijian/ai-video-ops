import { startTaskPolling } from "./task-progress.js";
import {
  ContentReviewItem,
  ContentReviewList,
  CreationCompletedState,
  CreationEvidenceDisclosure,
  CreationHeader,
  CreationState,
  CreationStepper,
  ExportSummary,
  safeCreationMessage,
} from "./creation-components.js?v=productized-stage3-3";

export function createNewsDeliveryViews({ api, showToast, escapeHtml }) {
  function watchTask(task, refresh, completedMessage) {
    showToast("任务已进入后台，可以离开页面后再返回。");
    startTaskPolling({
      api,
      taskId: task.task_id,
      onUpdate: () => {},
      onDone: async (current) => {
        await refresh();
        showToast(
          current.status === "completed"
            ? completedMessage
            : safeCreationMessage(current.error_message, "后台任务没有完成，请稍后重试。"),
        );
      },
      onError: () => {},
    });
  }

  function newKey() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return ["news", Date.now(), Math.random().toString(36).slice(2, 14)].join("_");
  }

  function roleLabel(role) {
    return ({
      price_offer_first_semantic_anchor: "首屏价格或优惠",
      price_scope_information: "价格范围",
      included_value_context: "包含内容",
      trust_context: "信任信息",
      service_context: "服务信息",
    })[role] || "已有内容";
  }

  function stepIndex(next) {
    return ({ RESOLVE_NEWS_PLAN: 0, HUMAN_REVIEW: 1, EXPORT_NEWS_EXCEL: 2, NEWS_EXCEL_EXPORTED: 3 })[next] ?? 0;
  }

  function workflowHeader(state) {
    const labels = {
      RESOLVE_NEWS_PLAN: "生成标题",
      HUMAN_REVIEW: "审核标题",
      EXPORT_NEWS_EXCEL: "审核完成",
      NEWS_EXCEL_EXPORTED: "已完成",
    };
    return `
      <section class="work-surface creation-workflow-header">
        ${CreationHeader({
          eyebrow: "新闻体",
          title: labels[state.next_action] || "继续新闻体创作",
          description: "从已确认的已有内容中重新组织新闻式标题，不新增事实。",
        })}
        ${CreationStepper({ steps: ["选择内容", "审核标题", "导出"], currentIndex: stepIndex(state.next_action) })}
      </section>`;
  }

  function sourceSummary(state) {
    const source = state.source_content || {};
    return `
      <section class="creation-source-summary">
        <span>来源内容</span>
        <strong>${escapeHtml(String(source.title || "已选择的已有内容"))}</strong>
        ${source.central_claim ? `<p>${escapeHtml(String(source.central_claim))}</p>` : ""}
      </section>`;
  }

  function reviewSurface(state) {
    const slots = state.plan?.slots || [];
    const rows = slots.map((slot, index) => ContentReviewItem({
      namespace: "news-review",
      itemId: String(slot.slot_id || ""),
      index: index + 1,
      eyebrow: roleLabel(slot.semantic_role),
      title: String(slot.proposed_text || ""),
      editorMode: "news",
      rejectDisabled: Boolean(slot.price_or_offer_anchor),
      rejectReason: slot.price_or_offer_anchor
        ? "为了保留本次必要的价格或优惠信息，这条内容暂时不能移除。"
        : "",
      evidenceRows: [
        { label: "来源事实", value: String(slot.source_known_fact || "") },
      ],
    }));
    return `
      ${sourceSummary(state)}
      <section class="work-surface creation-section content-review-surface">
        ${CreationHeader({ title: "审核标题", description: "逐条确认标题，只调整表达，不改变原有事实。" })}
        <div class="content-review-progress" data-news-review-progress>已处理 0 / ${slots.length}</div>
        ${ContentReviewList(rows)}
        <div class="creation-action-bar">
          <button type="button" class="btn btn-secondary" data-news-approve-all>全部通过</button>
          <button type="button" class="btn btn-primary" data-news-submit-review disabled>提交审核</button>
        </div>
        <p class="creation-governance-line">新闻体只重新组织已经确认的内容，不新增来源事实。</p>
      </section>`;
  }

  function renderBody(state) {
    if (state.next_action === "RESOLVE_NEWS_PLAN") {
      return `${sourceSummary(state)}${CreationState({
        eyebrow: "新闻体创作已开始",
        title: "生成标题",
        body: "系统会基于所选已有内容整理新闻式标题。",
        actions: `<button type="button" class="btn btn-primary" data-news-resolve-plan>生成标题</button>`,
      })}`;
    }
    if (state.next_action === "HUMAN_REVIEW") return reviewSurface(state);
    if (state.next_action === "EXPORT_NEWS_EXCEL") {
      const count = Number(state.review?.approved_slot_count || 0);
      return `${sourceSummary(state)}${CreationState({
        tone: "success",
        eyebrow: "审核完成",
        title: `${count} 条标题可以导出`,
        body: "导出文件只包含已经人工通过的标题。",
        content: ExportSummary([
          { label: "内容类型", value: "新闻体" },
          { label: "通过数量", value: `${count} 条` },
        ]),
        actions: `<button type="button" class="btn btn-primary" data-news-export>导出 Excel</button>`,
      })}`;
    }
    if (state.next_action === "NEWS_EXCEL_EXPORTED") {
      const name = state.export?.output_name || "新闻体标题.xlsx";
      const count = Number(state.export?.slot_count || 0);
      return CreationCompletedState({
        title: "已完成",
        description: `${count} 条标题已经导出。`,
        summary: [
          { label: "内容类型", value: "新闻体" },
          { label: "标题数量", value: `${count} 条` },
          { label: "文件名", value: name, wide: true },
        ],
        downloadHref: `/api/create/news/${encodeURIComponent(state.request_id)}/excel`,
        downloadLabel: "下载 Excel",
      });
    }
    return "";
  }

  function updateReviewProgress(host) {
    const items = Array.from(host.querySelectorAll("[data-content-review-item]"));
    const completed = items.filter((item) => item.querySelector("input[data-content-decision]:checked")).length;
    const progress = host.querySelector("[data-news-review-progress]");
    const submit = host.querySelector("[data-news-submit-review]");
    if (progress) progress.textContent = `已处理 ${completed} / ${items.length}`;
    if (submit) submit.disabled = !items.length || completed !== items.length;
  }

  function bindReview(host, state, refresh) {
    host.querySelectorAll("[data-content-review-item]").forEach((item) => {
      const editor = item.querySelector("[data-content-revision-editor]");
      item.querySelectorAll("[data-content-decision]").forEach((input) => {
        input.addEventListener("change", () => {
          if (editor) editor.hidden = input.value !== "revised";
          updateReviewProgress(host);
        });
      });
    });

    host.querySelector("[data-news-approve-all]")?.addEventListener("click", () => {
      host.querySelectorAll("[data-content-review-item]").forEach((item) => {
        const approved = item.querySelector('input[data-content-decision][value="approved"]');
        const editor = item.querySelector("[data-content-revision-editor]");
        if (approved) approved.checked = true;
        if (editor) editor.hidden = true;
      });
      updateReviewProgress(host);
    });

    const submit = host.querySelector("[data-news-submit-review]");
    submit?.addEventListener("click", async () => {
      const items = [];
      let approvedCount = 0;
      for (const item of host.querySelectorAll("[data-content-review-item]")) {
        const decision = item.querySelector("input[data-content-decision]:checked")?.value;
        if (!decision) return;
        const record = {
          slot_id: item.dataset.itemId,
          decision,
          note: item.querySelector("[data-content-review-note]")?.value?.trim() || "",
        };
        if (decision === "approved") approvedCount += 1;
        if (decision === "revised") {
          const title = item.querySelector("[data-revised-title]")?.value?.trim() || "";
          if (!title) {
            showToast("修改后的标题不能为空。");
            return;
          }
          approvedCount += 1;
          record.revised_text = title;
        }
        items.push(record);
      }
      if (approvedCount < 4 || approvedCount > 8) {
        showToast("本次需要保留 4–8 个标题，请调整审核选择。");
        return;
      }
      submit.disabled = true;
      submit.textContent = "正在保存审核结果…";
      try {
        await api(`/api/create/news/${encodeURIComponent(state.request_id)}/review`, {
          method: "POST",
          body: JSON.stringify({ items }),
        });
        showToast("标题审核已完成。");
        await refresh();
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "审核结果暂时无法保存，请稍后重试。"));
        if (submit.isConnected) {
          submit.disabled = false;
          submit.textContent = "提交审核";
        }
      }
    });
    updateReviewProgress(host);
  }

  function bindState(host, state, refresh) {
    const resolve = host.querySelector("[data-news-resolve-plan]");
    resolve?.addEventListener("click", async () => {
      resolve.disabled = true;
      resolve.textContent = "正在生成标题…";
      try {
        const response = await api(`/api/create/news/${encodeURIComponent(state.request_id)}/resolve-plan`, { method: "POST" });
        watchTask(response.task, refresh, "标题已生成，已进入审核。");
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "标题暂时无法生成，请稍后重试。"));
        if (resolve.isConnected) {
          resolve.disabled = false;
          resolve.textContent = "生成标题";
        }
      }
    });
    if (state.next_action === "HUMAN_REVIEW") bindReview(host, state, refresh);
    const exportButton = host.querySelector("[data-news-export]");
    exportButton?.addEventListener("click", async () => {
      exportButton.disabled = true;
      exportButton.textContent = "正在完成导出…";
      try {
        const response = await api(`/api/create/news/${encodeURIComponent(state.request_id)}/export`, { method: "POST" });
        watchTask(response.task, refresh, "导出已完成，已读取最新状态。");
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "导出暂时无法完成，请稍后重试。"));
        if (exportButton.isConnected) {
          exportButton.disabled = false;
          exportButton.textContent = "导出 Excel";
        }
      }
    });
  }

  async function restore(requestId, hostOverride = null) {
    const host = hostOverride || document.querySelector("#capacity-preview-result");
    if (!host || !requestId) return null;
    host.innerHTML = CreationState({ tone: "running", title: "正在恢复新闻体创作", body: "正在读取最新进度…" });
    try {
      const response = await api(`/api/create/news/${encodeURIComponent(requestId)}/delivery`);
      const state = response.state;
      host.innerHTML = `<div class="content-delivery-stack">${workflowHeader(state)}${renderBody(state)}</div>`;
      bindState(host, state, () => restore(requestId, host));
      return state;
    } catch (error) {
      host.innerHTML = CreationState({
        tone: "error",
        title: "这次创作暂时无法继续",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前状态无法安全恢复，请稍后重试或查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      showToast("新闻体创作暂时无法恢复。");
      return null;
    }
  }

  function completedList(items = []) {
    if (!items.length) return "";
    return `
      <details class="creation-evidence completed-exports">
        <summary>查看最近导出</summary>
        <div class="completed-export-list">
          ${items.slice(0, 3).map((item) => `
            <div>
              <span>${Number(item.slot_count || 0)} 条标题 · ${escapeHtml(String(item.output_name || "已导出文件"))}</span>
              <a class="btn btn-ghost" href="/api/create/news/${encodeURIComponent(item.request_id)}/excel">下载</a>
            </div>`).join("")}
        </div>
      </details>`;
  }

  function renderPreview(host, preview, { onRequestCreated } = {}) {
    const sources = preview.eligible_sources || [];
    const completed = preview.completed_deliveries || [];
    if (preview.available !== true || !sources.length) {
      host.innerHTML = CreationState({
        tone: "neutral",
        eyebrow: "新闻体",
        title: "暂无适合生成新闻体的已有内容",
        body: "当前没有满足条件的已确认内容。新闻体不会新增事实。",
        content: completedList(completed),
      });
      return;
    }

    host.innerHTML = `
      <section class="work-surface news-selection-surface">
        ${CreationHeader({ title: "选择已有内容", description: `当前可使用 ${sources.length} 条已有内容。选择这次要重新呈现的内容。` })}
        <div class="news-source-list">
          ${sources.map((source, index) => `
            <label class="news-source-row">
              <input type="radio" name="news-source-content" value="${escapeHtml(String(source.source_content_id || ""))}" ${index === 0 ? "checked" : ""}>
              <span>
                <strong>${escapeHtml(String(source.source_title || "已有内容"))}</strong>
                ${source.source_central_claim ? `<small>${escapeHtml(String(source.source_central_claim))}</small>` : ""}
              </span>
              <em>建议 ${Number(source.recommended_slot_count || 0)} 条</em>
            </label>`).join("")}
        </div>
        ${CreationEvidenceDisclosure({
          label: "新闻体说明",
          rows: [{ label: "内容边界", value: "只重新组织已有内容的标题和表达，不新增来源事实。" }],
        })}
        ${completedList(completed)}
        <div class="creation-actions">
          <button type="button" class="btn btn-primary" data-news-create-request>用所选内容生成标题</button>
        </div>
      </section>`;

    const button = host.querySelector("[data-news-create-request]");
    button?.addEventListener("click", async () => {
      const selected = host.querySelector('input[name="news-source-content"]:checked')?.value;
      if (!selected) {
        showToast("请选择一条已有内容。");
        return;
      }
      button.disabled = true;
      button.textContent = "正在开始新闻体创作…";
      try {
        const response = await api("/api/create/news/request", {
          method: "POST",
          body: JSON.stringify({
            business_id: preview.business_id,
            speaker_id: preview.speaker_id,
            source_content_id: selected,
            idempotency_key: newKey(),
          }),
        });
        const requestId = response.result.request.request_id;
        showToast(response.result.recovered ? "已恢复上次新闻体创作。" : "新闻体创作已开始。");
        if (typeof onRequestCreated === "function") await onRequestCreated(requestId);
        else await restore(requestId, host);
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "新闻体创作暂时无法开始，请稍后重试。"));
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = "用所选内容生成标题";
        }
      }
    });
  }

  return { renderPreview, restore };
}
