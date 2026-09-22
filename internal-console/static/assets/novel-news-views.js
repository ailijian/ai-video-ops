import { startTaskPolling } from "./task-progress.js";
import { CreationHeader, CreationState, CreationStepper, safeCreationMessage } from "./creation-components.js?v=productized-stage3-3";

export function createNovelNewsViews({ api, showToast, escapeHtml }) {
  function roleLabel(role) {
    return ({
      price_offer_first_semantic_anchor: "首屏价格或优惠",
      included_value_context: "包含内容",
      service_context: "服务信息",
      trust_context: "信任信息",
      price_scope_information: "价格范围",
      state_a: "已确认的状态 A",
      state_b: "已确认的状态 B",
    })[role] || "已确认的信息";
  }

  function freshKey() {
    return globalThis.crypto?.randomUUID?.() || `novel_news_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  }

  function watch(task, requestId, host, message) {
    showToast("已进入后台，离开页面后也可以恢复。 ");
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

  function renderPreview(host, projection, { businessId, speakerId, onRequestCreated }) {
    const opportunities = (projection.opportunities || []).filter((item) => item.novelty_status === "novel");
    const cards = opportunities.map((item) => {
      const supported = item.production_feasibility?.status === "supported";
      return `<article class="work-surface creation-section" data-novel-opportunity="${escapeHtml(item.concept_id)}">
        <span class="eyebrow">${supported ? "现有结构可支持" : "当前结构暂不支持"}</span>
        <h3>${escapeHtml(item.central_claim)}</h3>
        <p>${escapeHtml(item.why_publish || "来自已确认的客户信息。")}</p>
        <p class="creation-governance-line">${supported ? "适用：价格或优惠驱动的新闻体" : "这条内容方向有效，但当前已批准的结构或案例不足。"}</p>
        ${supported ? `<button type="button" class="btn btn-primary" data-confirm-novel>按这一个方向继续</button>` : ""}
      </article>`;
    }).join("");
    host.innerHTML = `<section class="work-surface creation-workflow-header">
      ${CreationHeader({ eyebrow: "新闻体 · 创作新内容", title: "选择一个新内容方向", description: "从客户已确认的真实信息中选择本次要讲的内容；一次制作一条新闻体视频。" })}
      <p class="creation-governance-line">内容是否值得讲，与现有结构能否支持分别判断。</p>
    </section>${cards || CreationState({ title: "当前没有可用的新内容方向", body: "已讲过的价格内容不会换一种形式后再算作新内容。可以选择“重新表达已有内容”，或补充真实客户信息。" })}`;
    host.querySelectorAll("[data-confirm-novel]").forEach((button) => button.addEventListener("click", async () => {
      const card = button.closest("[data-novel-opportunity]");
      button.disabled = true;
      button.textContent = "正在确认…";
      try {
        const response = await api("/api/create/confirm", {
          method: "POST",
          body: JSON.stringify({
            business_id: businessId, speaker_id: speakerId,
            profile: "news", requested_quantity: 1, confirmed_quantity: 1,
            selected_opportunity_id: card.dataset.novelOpportunity,
            idempotency_key: freshKey(),
          }),
        });
        await onRequestCreated(response.result.request_id);
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "无法确认这个内容方向。"));
        if (button.isConnected) { button.disabled = false; button.textContent = "按这一个方向继续"; }
      }
    }));
  }

  function reviewHtml(state) {
    const beats = state.beats || [];
    return `<section class="work-surface creation-section content-review-surface">
      ${CreationHeader({ eyebrow: "新闻体 · 人工审核", title: "审核新闻体", description: "请逐 Beat 核对角色、文本和来源事实；修改只能调整表达，不能添加事实。" })}
      <div class="creation-news-beats">${beats.map((beat) => {
        const fact = state.source_facts?.[beat.source_fact_refs?.[0]] || "";
        return `<fieldset class="creation-news-beat" data-novel-beat="${escapeHtml(beat.beat_id)}">
          <legend>Beat ${beat.order} · ${escapeHtml(roleLabel(beat.semantic_role))}</legend>
          <p>${escapeHtml(beat.text)}</p><details><summary>查看来源事实</summary><p>${escapeHtml(fact)}</p></details>
          <div class="creation-news-beat-actions">
            <label><input type="radio" name="decision-${escapeHtml(beat.beat_id)}" value="approved" checked> 通过</label>
            <label><input type="radio" name="decision-${escapeHtml(beat.beat_id)}" value="revised"> 修改</label>
            <label><input type="radio" name="decision-${escapeHtml(beat.beat_id)}" value="rejected"> 不采用</label>
          </div><textarea aria-label="Beat ${beat.order} 修改后的文本" data-novel-revised hidden>${escapeHtml(beat.text)}</textarea>
        </fieldset>`;
      }).join("")}</div>
      <p class="creation-governance-line">首个价格或优惠 Beat 及至少 4 个 Beat 必须保留；所有文本必须能追溯到已确认事实。</p>
      <button type="button" class="btn btn-primary" data-submit-novel-review>提交审核</button>
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
    if (state.stage === "blocked") {
      body = CreationState({ tone: "warning", title: "有内容值得讲，但现有结构暂不支持", body: safeCreationMessage(state.source_coverage?.humanized_reason || state.source_coverage?.reason, "请稍后重试或返回调整。") });
    } else if (state.stage === "source_plan") {
      body = CreationState({ title: "锁定结构与案例", body: "系统将验证已批准的结构和案例参考。", actions: `<button class="btn btn-primary" data-novel-action="sources">准备创作来源</button>` });
    } else if (state.stage === "generation") {
      body = CreationState({ title: "已有可靠创作依据", body: "只有现在才会调用生成模型；生成后必须人工审核。", actions: `<button class="btn btn-primary" data-novel-action="generate">生成 4–8 个新闻 Beat</button>` });
    } else if (state.stage === "review") {
      body = reviewHtml(state);
    } else if (state.stage === "export") {
      body = CreationState({ title: "审核完成", body: "将按顺序导出标题1…标题N，并分别记录新内容语义历史与新闻体呈现历史。", actions: `<button class="btn btn-primary" data-novel-action="export">导出新闻体 Excel</button>` });
    } else {
      body = CreationState({ tone: "success", title: "新闻体已完成", body: "新内容与本次呈现已分别登记。", actions: `<a class="btn btn-primary" href="/api/create/novel-news/${encodeURIComponent(requestId)}/excel">下载 Excel</a>` });
    }
    host.innerHTML = `<section class="work-surface creation-workflow-header">
      ${CreationHeader({ eyebrow: "新闻体 · 创作新内容", title, description: "一条视频，4–8 个连续的信息 Beat。" })}
      ${CreationStepper({ steps: ["选内容", "生成", "审核", "导出", "完成"], currentIndex: index })}
    </section>${body}`;
    host.querySelectorAll("[data-novel-beat] input[type=radio]").forEach((radio) => radio.addEventListener("change", () => {
      const row = radio.closest("[data-novel-beat]");
      row.querySelector("[data-novel-revised]").hidden = row.querySelector("input:checked")?.value !== "revised";
    }));
    host.querySelector("[data-submit-novel-review]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      const decisions = [...host.querySelectorAll("[data-novel-beat]")].map((row) => ({
        beat_id: row.dataset.novelBeat,
        decision: row.querySelector("input:checked")?.value,
        revised_text: row.querySelector("[data-novel-revised]")?.value || null,
      }));
      try {
        await api(`/api/create/novel-news/${encodeURIComponent(requestId)}/review`, {
          method: "POST", body: JSON.stringify({ decisions }),
        });
        await restore(requestId, host);
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "审核未通过，请核对修改文本与来源事实。"));
        button.disabled = false;
      }
    });
    host.querySelectorAll("[data-novel-action]").forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const operation = button.dataset.novelAction;
        if (operation === "sources") {
          await api(`/api/create/${encodeURIComponent(requestId)}/resolve-sources`, { method: "POST" });
          await restore(requestId, host);
        } else {
          const response = await api(`/api/create/novel-news/${encodeURIComponent(requestId)}/${operation}`, { method: "POST" });
          watch(response.task, requestId, host, operation === "generate" ? "新闻体 Beat 已生成，请审核。" : "新闻体已导出。 ");
        }
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前操作未完成。"));
        if (button.isConnected) button.disabled = false;
      }
    }));
  }

  return { renderPreview, restore };
}
