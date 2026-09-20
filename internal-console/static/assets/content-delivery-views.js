import { startTaskPolling } from "./task-progress.js";
import {
  ContentReviewItem,
  ContentReviewList,
  CreationCompletedState,
  CreationHeader,
  CreationState,
  CreationStepper,
  ExportSummary,
  TopicList,
  safeCreationMessage,
} from "./creation-components.js?v=productized-stage3-3";

export function createContentDeliveryViews({ api, showToast, escapeHtml }) {
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

  function flagText(flag) {
    const value = String(flag || "");
    if (value === "cross_concept_material_overlap_requires_human_review") {
      return "与同批其他稿存在信息重叠，请判断是否值得分别发布";
    }
    if (value === "claim_candidates_require_human_review") return "关键表达需要人工确认";
    if (value.startsWith("claim_language_requires_human_review")) return "对比式表达需要人工确认";
    if (value.startsWith("grounding_requires_human_review")) return "关键表达需要核对事实依据";
    return "这条内容需要重点核对";
  }

  function stepIndex(next) {
    return ({
      CREATE_CONTENT_PLAN: 0,
      GENERATE_SCRIPTS: 1,
      HUMAN_REVIEW: 2,
      EXPORT_EXCEL: 3,
      REVIEW_COMPLETE_NO_EXPORT: 3,
      EXCEL_EXPORTED: 4,
    })[next] ?? 0;
  }

  function workflowHeader(state) {
    const labels = {
      CREATE_CONTENT_PLAN: "生成选题",
      GENERATE_SCRIPTS: "选题已经准备好",
      HUMAN_REVIEW: "审核文案",
      REVIEW_COMPLETE_NO_EXPORT: "审核已完成",
      EXPORT_EXCEL: state.export?.completed ? "正在完成导出" : "审核完成",
      EXCEL_EXPORTED: "已完成",
    };
    return `
      <section class="work-surface creation-workflow-header">
        ${CreationHeader({
          eyebrow: "素材混剪",
          title: labels[state.next_action] || "继续创作",
          description: "按选题、文案、审核和导出完成本次创作。",
        })}
        ${CreationStepper({ steps: ["选题", "文案", "审核", "导出"], currentIndex: stepIndex(state.next_action) })}
      </section>`;
  }

  function concepts(state) {
    return state.content_plan?.selected_concepts || [];
  }

  function topicsSurface(state) {
    const items = concepts(state).map((concept) => ({
      title: concept.primary_topic || concept.content_job || "待命名选题",
      audienceNeed: concept.audience_need || "",
      coreExpression: concept.central_claim || "",
    }));
    if (!items.length) return "";
    return `
      <section class="work-surface creation-section">
        ${CreationHeader({ title: `${items.length} 个选题`, description: "这些选题来自客户信息、历史内容和当前可用参考。" })}
        ${TopicList(items)}
      </section>`;
  }

  function reviewSurface(state) {
    const contents = state.generation?.contents || [];
    const rows = contents.map((item, index) => ContentReviewItem({
      namespace: "mix-review",
      itemId: String(item.content_id || ""),
      index: index + 1,
      eyebrow: "待审核文案",
      title: String(item.title || ""),
      body: String(item.narration || ""),
      bodyLabel: "文案",
      coreExpression: String(item.central_claim || ""),
      flags: (item.potential_review_flags || []).map(flagText),
      editorMode: "mix",
    }));
    return `
      <section class="work-surface creation-section content-review-surface">
        ${CreationHeader({ title: "审核文案", description: "逐条确认，只有通过的内容才能进入最终导出。" })}
        <div class="content-review-progress" data-review-progress>已处理 0 / ${contents.length}</div>
        ${ContentReviewList(rows)}
        <div class="creation-action-bar">
          <button type="button" class="btn btn-secondary" data-approve-all>全部通过</button>
          <button type="button" class="btn btn-primary" data-submit-review disabled>提交审核</button>
        </div>
        <p class="creation-governance-line">修改文案只能调整表达，不能新增未经确认的事实。</p>
      </section>`;
  }

  function renderBody(state) {
    const next = state.next_action || "CREATE_CONTENT_PLAN";
    if (next === "RESOLVE_GENERATION_SOURCES") {
      return CreationState({ tone: "warning", eyebrow: "创作准备", title: "创作依据还没有准备完成", body: "请返回上一步完成创作准备后再继续。" });
    }
    if (next === "CREATE_CONTENT_PLAN") {
      return CreationState({
        eyebrow: "第 1 步",
        title: "生成选题",
        body: "系统会根据客户信息、历史内容和可用参考，整理本次值得做的选题。",
        actions: `<button type="button" class="btn btn-primary" data-resolve-content-plan>生成选题</button>`,
      });
    }
    if (next === "GENERATE_SCRIPTS") {
      const count = Number(state.content_plan?.selected_quantity || concepts(state).length || 0);
      return `${topicsSurface(state)}${CreationState({
        tone: "success",
        title: "选题已经准备好",
        body: `本次共有 ${count} 个选题，可以继续生成文案。`,
        actions: `<button type="button" class="btn btn-primary" data-generate-scripts>生成文案</button>`,
      })}`;
    }
    if (next === "HUMAN_REVIEW") return reviewSurface(state);
    if (next === "REVIEW_COMPLETE_NO_EXPORT") {
      return CreationState({
        tone: "neutral",
        eyebrow: "审核完成",
        title: "本次没有通过审核的内容",
        body: "这些内容不会进入最终导出。",
        actions: `<a class="btn btn-secondary" href="/create">返回创作</a>`,
      });
    }
    if (next === "EXPORT_EXCEL") {
      const excelReady = state.export?.completed === true;
      const approved = Number(state.review?.approved_item_count || 0);
      return CreationState({
        tone: excelReady ? "running" : "success",
        eyebrow: excelReady ? "导出处理中" : "审核完成",
        title: excelReady ? "正在完成导出" : `${approved} 条内容可以导出`,
        body: excelReady
          ? "文件已经生成，正在完成最后记录；不会重复生成内容或文件。"
          : "导出文件只包含已经人工通过的内容。",
        content: ExportSummary([
          { label: "客户", value: state.business_display_name || state.business_id || "" },
          { label: "出镜人", value: state.speaker_display_name || state.speaker_id || "" },
          { label: "内容类型", value: "素材混剪" },
          { label: "通过数量", value: `${approved} 条` },
          ...(state.export?.output_name ? [{ label: "文件名", value: state.export.output_name, wide: true }] : []),
        ]),
        actions: `<button type="button" class="btn btn-primary" data-export-excel>${excelReady ? "完成导出" : "导出 Excel"}</button>`,
      });
    }
    if (next === "EXCEL_EXPORTED") {
      const name = state.export?.output_name || "素材混剪内容.xlsx";
      const count = Number(state.export?.exported_row_count || 0);
      return CreationCompletedState({
        title: "已完成",
        description: `${count} 条内容已经导出。`,
        summary: [
          { label: "客户", value: state.business_display_name || state.business_id || "" },
          { label: "出镜人", value: state.speaker_display_name || state.speaker_id || "" },
          { label: "导出条数", value: `${count} 条` },
          { label: "文件名", value: name, wide: true },
        ],
        downloadHref: `/api/create/${encodeURIComponent(state.request_id)}/exported-excel`,
        downloadLabel: "下载 Excel",
      });
    }
    return "";
  }

  function updateReviewProgress(host) {
    const items = Array.from(host.querySelectorAll("[data-content-review-item]"));
    const completed = items.filter((item) => item.querySelector("input[data-content-decision]:checked")).length;
    const progress = host.querySelector("[data-review-progress]");
    const submit = host.querySelector("[data-submit-review]");
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
    host.querySelector("[data-approve-all]")?.addEventListener("click", () => {
      host.querySelectorAll("[data-content-review-item]").forEach((item) => {
        const approved = item.querySelector('input[data-content-decision][value="approved"]');
        const editor = item.querySelector("[data-content-revision-editor]");
        if (approved) approved.checked = true;
        if (editor) editor.hidden = true;
      });
      updateReviewProgress(host);
    });
    const submit = host.querySelector("[data-submit-review]");
    submit?.addEventListener("click", async () => {
      const items = [];
      for (const item of host.querySelectorAll("[data-content-review-item]")) {
        const decision = item.querySelector("input[data-content-decision]:checked")?.value;
        if (!decision) return;
        const record = {
          content_id: item.dataset.itemId,
          decision,
          note: item.querySelector("[data-content-review-note]")?.value?.trim() || "",
        };
        if (decision === "revised") {
          const title = item.querySelector("[data-revised-title]")?.value?.trim() || "";
          const narration = item.querySelector("[data-revised-body]")?.value?.trim() || "";
          if (!title || !narration) {
            showToast("修改后的标题和文案都不能为空。");
            return;
          }
          record.revised_title = title;
          record.revised_narration = narration;
        }
        items.push(record);
      }
      submit.disabled = true;
      submit.textContent = "正在保存审核结果…";
      try {
        const response = await api(`/api/create/${encodeURIComponent(state.request_id)}/review`, {
          method: "POST",
          body: JSON.stringify({ note: "Internal Console content review.", items }),
        });
        const result = response.result?.result;
        showToast(result?.approved_item_count > 0
          ? `审核已完成：${Number(result.approved_item_count)} 条可以导出。`
          : "审核已完成：本次没有可导出内容。");
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

  function bind(host, state, refresh) {
    const plan = host.querySelector("[data-resolve-content-plan]");
    plan?.addEventListener("click", async () => {
      plan.disabled = true;
      plan.textContent = "正在生成选题…";
      try {
        const response = await api(`/api/create/${encodeURIComponent(state.request_id)}/resolve-content-plan`, { method: "POST" });
        watchTask(response.task, refresh, "选题已生成，已读取最新状态。");
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "选题暂时无法生成，请稍后重试。"));
        if (plan.isConnected) {
          plan.disabled = false;
          plan.textContent = "生成选题";
        }
      }
    });
    const generate = host.querySelector("[data-generate-scripts]");
    generate?.addEventListener("click", async () => {
      generate.disabled = true;
      generate.textContent = "正在生成文案…";
      try {
        const response = await api(`/api/create/${encodeURIComponent(state.request_id)}/generate-scripts`, { method: "POST" });
        watchTask(response.task, refresh, "文案已生成，已进入审核。");
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "文案暂时无法生成，请稍后重试。"));
        if (generate.isConnected) {
          generate.disabled = false;
          generate.textContent = "生成文案";
        }
      }
    });
    if (state.next_action === "HUMAN_REVIEW") bindReview(host, state, refresh);
    const exportButton = host.querySelector("[data-export-excel]");
    exportButton?.addEventListener("click", async () => {
      exportButton.disabled = true;
      exportButton.textContent = "正在完成导出…";
      try {
        const response = await api(`/api/create/${encodeURIComponent(state.request_id)}/export-mix`, { method: "POST" });
        watchTask(response.task, refresh, "导出已完成，已读取最新状态。");
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "导出暂时无法完成，请稍后重试。"));
        if (exportButton.isConnected) {
          exportButton.disabled = false;
          exportButton.textContent = state.export?.completed ? "完成导出" : "导出 Excel";
        }
      }
    });
  }

  async function restore(requestId) {
    const host = document.querySelector("#content-delivery-host");
    if (!host || !requestId) return;
    host.innerHTML = CreationState({ tone: "running", title: "正在恢复本次创作", body: "正在读取最新进度…" });
    try {
      const response = await api(`/api/create/${encodeURIComponent(requestId)}/delivery`);
      const state = response.state;
      host.innerHTML = `<div class="content-delivery-stack">${workflowHeader(state)}${renderBody(state)}</div>`;
      bind(host, state, () => restore(requestId));
    } catch (error) {
      host.innerHTML = CreationState({
        tone: "error",
        title: "这次创作暂时无法继续",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前状态无法安全恢复，请稍后重试或查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      showToast("本次创作暂时无法恢复。");
    }
  }

  return { restore };
}
