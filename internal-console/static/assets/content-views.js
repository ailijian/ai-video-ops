import { escapeHtml } from "./case-components.js";
import { createContentDeliveryViews } from "./content-delivery-views.js?v=productized-stage3-3";
import { createNewsDeliveryViews } from "./news-delivery-views.js?v=productized-stage3-3";
import { createNovelNewsViews } from "./novel-news-views.js?v=gate-c2-1";
import {
  CreationHeader,
  CreationMetricRow,
  CreationState,
  CreationSummary,
  safeCreationMessage,
} from "./creation-components.js?v=productized-stage3-3";

export function createContentViews({
  app,
  api,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  renderLoadError,
}) {
  let options = null;
  let confirmationKey = null;

  const deliveryViews = createContentDeliveryViews({ api, showToast, escapeHtml });
  const newsDeliveryViews = createNewsDeliveryViews({ api, showToast, escapeHtml });
  const novelNewsViews = createNovelNewsViews({ api, showToast, escapeHtml });

  function newConfirmationKey() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return ["console", Date.now(), Math.random().toString(36).slice(2, 14)].join("_");
  }

  function selectedProfileValue() {
    return document.querySelector('input[name="create-profile"]:checked')?.value || "mix";
  }

  function selectedNewsModeValue() {
    return document.querySelector('input[name="create-news-mode"]:checked')?.value || "cross_profile_repurpose";
  }

  function selectedCustomer(businessId) {
    return (options?.customers || []).find((customer) => customer.business_id === businessId);
  }

  function approvedSpeakers(customer) {
    return (customer?.speakers || []).filter((speaker) => speaker.status === "approved");
  }

  function selectionSummary() {
    const form = document.querySelector("#content-entry-form");
    const business = document.querySelector("#create-business");
    const speaker = document.querySelector("#create-speaker");
    const quantity = document.querySelector("#create-quantity");
    const profile = selectedProfileValue();
    return [
      { label: "客户", value: business?.selectedOptions?.[0]?.textContent?.trim() || "" },
      { label: "出镜人", value: speaker?.selectedOptions?.[0]?.textContent?.trim() || "" },
      { label: "内容类型", value: profile === "news" ? "新闻体" : "素材混剪" },
      ...(profile === "news" ? [{ label: "创作模式", value: selectedNewsModeValue() === "novel_content" ? "创作新内容" : "重新表达已有内容" }] : []),
      ...(profile === "mix" && form?.dataset.confirmedQuantity
        ? [
            { label: "计划数量", value: `${Number(form.dataset.requestedQuantity || 0)} 条` },
            { label: "本次确认", value: `${Number(form.dataset.confirmedQuantity || 0)} 条` },
          ]
        : profile === "mix"
          ? [{ label: "计划数量", value: `${Number(quantity?.value || 0)} 条` }]
          : []),
    ];
  }

  function lockEntryForm(label = "继续上次创作") {
    const form = document.querySelector("#content-entry-form");
    if (!form) return;
    form.classList.add("completed");
    form.querySelectorAll("input, select, button").forEach((control) => {
      control.disabled = !control.matches("[data-edit-creation-selection]");
    });
    const compact = form.querySelector("[data-creation-entry-locked]");
    if (compact) {
      compact.hidden = false;
      compact.innerHTML = `
        <div>
          <span>本次创作</span>
          <strong>${escapeHtml(label)}</strong>
        </div>
        ${CreationSummary(selectionSummary())}
        <button type="button" class="btn btn-ghost" data-edit-creation-selection>更换选择</button>`;
      compact.querySelector("[data-edit-creation-selection]")?.addEventListener("click", () => {
        document.querySelector("#capacity-preview-result").innerHTML = "";
        unlockEntryForm();
      });
    }
  }

  function unlockEntryForm() {
    const form = document.querySelector("#content-entry-form");
    if (!form) return;
    form.classList.remove("completed", "has-capacity-result");
    delete form.dataset.requestedQuantity;
    delete form.dataset.confirmedQuantity;
    form.querySelectorAll("input, select, button").forEach((control) => { control.disabled = false; });
    const compact = form.querySelector("[data-creation-entry-locked]");
    if (compact) {
      compact.hidden = true;
      compact.innerHTML = "";
    }
    const speaker = form.querySelector("#create-speaker");
    const submit = form.querySelector("#check-content-capacity");
    const hasSpeaker = Boolean(speaker?.options?.length);
    if (speaker) speaker.disabled = !hasSpeaker;
    if (submit) submit.disabled = !hasSpeaker;
    syncProfileSpecificUi();
  }

  function syncProfileSpecificUi() {
    const news = selectedProfileValue() === "news";
    const quantityField = document.querySelector("#create-quantity-field");
    const quantityInput = document.querySelector("#create-quantity");
    const submit = document.querySelector("#check-content-capacity");
    if (quantityField) quantityField.hidden = news;
    const newsModes = document.querySelector("#create-news-modes");
    if (newsModes) newsModes.hidden = !news;
    if (quantityInput) quantityInput.disabled = news || document.querySelector("#content-entry-form")?.classList.contains("completed");
    if (submit && !submit.closest("form")?.classList.contains("completed")) submit.textContent = "查看可创作内容";
  }

  function syncSpeakerOptions(customer, requestedSpeaker = "") {
    const select = document.querySelector("#create-speaker");
    const empty = document.querySelector("[data-speaker-empty]");
    const submit = document.querySelector("#check-content-capacity");
    if (!select) return;
    const speakers = approvedSpeakers(customer);
    select.innerHTML = speakers.map((speaker) => `
      <option value="${escapeHtml(speaker.speaker_id)}" ${speaker.speaker_id === requestedSpeaker ? "selected" : ""}>
        ${escapeHtml(speaker.display_name)}${speaker.public_role ? ` · ${escapeHtml(speaker.public_role)}` : ""}
      </option>`).join("");
    select.disabled = !speakers.length;
    if (empty) empty.hidden = Boolean(speakers.length);
    if (submit) submit.disabled = !speakers.length;
  }

  function renderPreparation(handoffReady, sourcePlan, businessId) {
    if (handoffReady === false) {
      return CreationState({
        tone: "running",
        eyebrow: "创作准备",
        title: "正在恢复创作准备",
        body: "本次选择已经保留，可以安全继续。",
        actions: `<button id="recover-source-handoff" class="btn btn-primary" type="button">继续准备</button>`,
      });
    }
    if (sourcePlan?.artifactExists === true && sourcePlan.coverageStatus !== "supported") {
      const feasibility = sourcePlan.productionFeasibility || {};
      const route = feasibility.optional_customer_truth_route;
      const processRoute = route?.capability === "process_material";
      return CreationState({
        tone: "warning",
        eyebrow: "创作准备",
        title: "本次创作暂时无法继续",
        body: processRoute
          ? "这些内容方向本身有效，但当前已批准的创作结构还不能支持这批内容。"
          : safeCreationMessage(
            feasibility.humanized_reason || sourcePlan.coverageReason,
            "当前创作结构暂时不能支持这批内容。",
          ),
        content: `<p class="creation-governance-line">客户档案仍然有效；这是创作结构覆盖不足，不代表客户资料不完整。</p>
          ${processRoute ? `<p class="creation-governance-line">只有客户确实存在稳定、真实的服务流程时才需要补充；不需要为了生成内容而编写不存在的信息。</p>` : ""}`,
        actions: `
          <button type="button" class="btn btn-danger" data-abandon-generation-request>结束本次创作</button>
          ${processRoute ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}/supplement?gap=process_material" data-route>客户有真实流程，去补充</a>` : ""}`,
      });
    }
    if (!sourcePlan || sourcePlan.artifactExists !== true) {
      return CreationState({
        eyebrow: "创作准备",
        title: "还需要准备创作内容",
        body: "系统会整理客户信息、历史内容和可用参考。",
        actions: `<button id="resolve-sources" class="btn btn-primary" type="button">准备创作内容</button>`,
      });
    }
    return CreationState({
      tone: "success",
      eyebrow: "创作准备",
      title: "准备完成",
      body: "已经找到足够的创作依据。",
    });
  }

  function renderRequestEstablished(host, {
    requestId,
    profile,
    confirmedQuantity,
    requestedQuantity = confirmedQuantity,
    businessId = "",
    handoffReady,
    sourcePlan = null,
    recovered = false,
  }) {
    const preparationComplete = handoffReady !== false
      && sourcePlan?.artifactExists === true
      && sourcePlan?.coverageSupported === true
      && sourcePlan?.coverageStatus === "supported";
    host.innerHTML = `
      ${preparationComplete ? "" : `
        <section class="work-surface creation-request-surface" data-request-id="${escapeHtml(requestId)}">
          ${CreationHeader({
            eyebrow: recovered ? "继续上次创作" : "本次创作已创建",
            title: profile === "news" ? "新闻体创作" : "素材混剪创作",
            description: "选择已经锁定，可以从当前步骤继续。",
          })}
          ${renderPreparation(handoffReady, sourcePlan, businessId)}
        </section>`}
      <div id="content-delivery-host"></div>`;
    const form = document.querySelector("#content-entry-form");
    if (form) {
      form.dataset.requestedQuantity = String(requestedQuantity || 0);
      form.dataset.confirmedQuantity = String(confirmedQuantity || 0);
    }
  }

  function bindAbandonRequest(host, requestId) {
    const button = host.querySelector("[data-abandon-generation-request]");
    if (!button) return;
    button.addEventListener("click", async () => {
      if (!window.confirm("结束后，这个请求不会重新绑定新的客户档案版本。确定结束本次创作吗？")) return;
      button.disabled = true;
      button.textContent = "正在结束…";
      try {
        await api(`/api/create/${encodeURIComponent(requestId)}/abandon`, { method: "POST" });
        showToast("本次创作已结束，可以重新检查创作条件。");
        unlockEntryForm();
        await restoreSelectedProfileRequest();
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "本次创作暂时无法结束。"));
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = "结束本次创作";
        }
      }
    });
  }

  function bindResolveSourcesButton(host, requestId) {
    const button = host.querySelector("#resolve-sources");
    if (!button) return;
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "正在准备…";
      try {
        await api(`/api/create/${encodeURIComponent(requestId)}/resolve-sources`, { method: "POST" });
        showToast("创作内容准备完成。");
        await restoreSelectedProfileRequest();
      } catch (error) {
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "创作内容暂时无法准备，请稍后重试。"));
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = "准备创作内容";
        }
      }
    });
  }

  function activeSpeakerUnavailable(host) {
    host.innerHTML = CreationState({
      tone: "error",
      title: "这次创作暂时无法继续",
      body: "出镜人状态已经发生变化，请返回客户页面确认后再继续。",
      actions: `<a class="btn btn-secondary" href="/customers">查看客户</a>`,
    });
    lockEntryForm("暂时无法继续");
  }

  async function restoreActiveNewsRequest() {
    const business = document.querySelector("#create-business");
    const host = document.querySelector("#capacity-preview-result");
    if (!business || !host) return false;
    try {
      const response = await api(`/api/create/news/active?business_id=${encodeURIComponent(business.value)}`);
      const active = response.active_request;
      if (!active) {
        unlockEntryForm();
        return false;
      }
      const speaker = document.querySelector("#create-speaker");
      if (speaker && active.speaker_id) {
        const found = Array.from(speaker.options).some((option) => option.value === active.speaker_id);
        if (!found) {
          activeSpeakerUnavailable(host);
          return true;
        }
        speaker.value = active.speaker_id;
      }
      const radio = document.querySelector('input[name="create-profile"][value="news"]');
      if (radio) radio.checked = true;
      document.querySelectorAll(".profile-choice").forEach((label) => label.classList.toggle("selected", label.querySelector("input").checked));
      syncProfileSpecificUi();
      lockEntryForm("继续上次新闻体创作");
      await newsDeliveryViews.restore(active.request_id, host);
      return true;
    } catch (error) {
      host.innerHTML = CreationState({
        tone: "error",
        title: "这次创作暂时无法继续",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前状态无法安全恢复，请稍后重试或查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      lockEntryForm("暂时无法继续");
      return true;
    }
  }

  async function restoreActiveNovelNewsRequest() {
    const business = document.querySelector("#create-business");
    const host = document.querySelector("#capacity-preview-result");
    if (!business || !host) return false;
    try {
      const response = await api(`/api/create/active-request?business_id=${encodeURIComponent(business.value)}&profile=news`);
      const active = response.active_request;
      if (!active) { unlockEntryForm(); return false; }
      const speaker = document.querySelector("#create-speaker");
      if (speaker && active.speaker_id) {
        if (![...speaker.options].some((option) => option.value === active.speaker_id)) {
          activeSpeakerUnavailable(host);
          return true;
        }
        speaker.value = active.speaker_id;
      }
      lockEntryForm("继续上次新闻体 · 创作新内容");
      if (active.handoff_ready === false) {
        host.innerHTML = CreationState({
          title: "继续上次新闻体创作",
          body: "内容方向已经确认，继续准备创作来源；不会重新建立内容方向。",
          actions: `<button type="button" class="btn btn-primary" data-recover-novel-handoff>继续准备</button>`,
        });
        host.querySelector("[data-recover-novel-handoff]")?.addEventListener("click", async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            await api("/api/create/confirm", {
              method: "POST",
              body: JSON.stringify({
                business_id: active.business_id, speaker_id: active.speaker_id,
                profile: "news", requested_quantity: 1, confirmed_quantity: 1,
                selected_opportunity_id: active.selected_opportunity_id,
                idempotency_key: newConfirmationKey(),
              }),
            });
            await restoreActiveNovelNewsRequest();
          } catch (error) {
            showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "暂时无法恢复，请稍后重试。"));
            if (button.isConnected) button.disabled = false;
          }
        });
        return true;
      }
      await novelNewsViews.restore(active.request_id, host);
      return true;
    } catch (error) {
      host.innerHTML = CreationState({
        tone: "error", title: "新闻体创作暂时无法恢复",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "请查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      lockEntryForm("暂时无法继续");
      return true;
    }
  }

  async function restoreActiveRequest() {
    const business = document.querySelector("#create-business");
    const host = document.querySelector("#capacity-preview-result");
    if (!business || !host) return false;
    let active;
    try {
      const response = await api(`/api/create/active-request?business_id=${encodeURIComponent(business.value)}`);
      active = response.active_request;
    } catch (error) {
      host.innerHTML = CreationState({
        tone: "error",
        title: "这次创作暂时无法继续",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前状态无法安全恢复，请稍后重试或查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      lockEntryForm("暂时无法继续");
      return true;
    }
    if (!active) {
      unlockEntryForm();
      return false;
    }
    const speaker = document.querySelector("#create-speaker");
    if (speaker && active.speaker_id) {
      const found = Array.from(speaker.options).some((option) => option.value === active.speaker_id);
      if (!found) {
        activeSpeakerUnavailable(host);
        return true;
      }
      speaker.value = active.speaker_id;
    }
    const radio = document.querySelector(`input[name="create-profile"][value="${active.profile}"]`);
    if (radio) radio.checked = true;
    document.querySelectorAll(".profile-choice").forEach((label) => label.classList.toggle("selected", label.querySelector("input").checked));
    const quantity = document.querySelector("#create-quantity");
    if (quantity && active.requested_quantity) quantity.value = String(active.requested_quantity);
    syncProfileSpecificUi();
    renderRequestEstablished(host, {
      requestId: active.request_id,
      businessId: active.business_id,
      profile: active.profile,
      requestedQuantity: active.requested_quantity,
      confirmedQuantity: active.confirmed_quantity,
      handoffReady: active.handoff_ready,
      recovered: true,
      sourcePlan: {
        artifactExists: active.source_plan_artifact_exists === true,
        coverageSupported: active.source_coverage_supported === true,
        coverageStatus: active.coverage_status,
        coverageReason: active.coverage_reason,
        productionFeasibility: active.production_feasibility,
      },
    });
    lockEntryForm("继续上次素材混剪创作");
    if (active.handoff_ready === false) {
      const recover = host.querySelector("#recover-source-handoff");
      recover?.addEventListener("click", async () => {
        recover.disabled = true;
        recover.textContent = "正在恢复…";
        try {
          await api("/api/create/confirm", {
            method: "POST",
            body: JSON.stringify({
              business_id: active.business_id,
              speaker_id: active.speaker_id,
              profile: active.profile,
              requested_quantity: Number(active.requested_quantity),
              confirmed_quantity: Number(active.confirmed_quantity),
              idempotency_key: newConfirmationKey(),
            }),
          });
          showToast("本次创作已经恢复。");
          await restoreActiveRequest();
        } catch (error) {
          showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "本次创作暂时无法恢复，请稍后重试。"));
          if (recover.isConnected) {
            recover.disabled = false;
            recover.textContent = "继续准备";
          }
        }
      });
    } else {
      bindResolveSourcesButton(host, active.request_id);
    }
    bindAbandonRequest(host, active.request_id);
    if (active.source_coverage_supported === true) await deliveryViews.restore(active.request_id);
    return true;
  }

  async function restoreSelectedProfileRequest() {
    if (selectedProfileValue() !== "news") return restoreActiveRequest();
    return options?.novel_news?.available === true && selectedNewsModeValue() === "novel_content"
      ? restoreActiveNovelNewsRequest() : restoreActiveNewsRequest();
  }

  function bindAdjustQuantity(host) {
    host.querySelector("[data-adjust-quantity]")?.addEventListener("click", () => {
      host.innerHTML = "";
      document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
      const input = document.querySelector("#create-quantity");
      input?.focus();
      input?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function renderResult(preview) {
    const host = document.querySelector("#capacity-preview-result");
    if (!host) return;
    const entryForm = document.querySelector("#content-entry-form");
    entryForm?.classList.remove("has-capacity-result");
    const capacity = preview.capacity || {};
    const feasibility = preview.production_feasibility || {};
    const recommendation = preview.recommendation || {};
    const profile = preview.selection?.profile || "mix";
    confirmationKey = null;

    if (recommendation.status === "profile_unavailable") {
      host.innerHTML = CreationState({
        tone: "warning",
        title: "这种内容目前暂时不能开始",
        body: "请返回客户页面确认客户与出镜人状态，或选择其他内容类型。",
      });
      return;
    }

    const requested = Number(recommendation.requested_quantity || 0);
    const available = Number(capacity.high_quality_novel_capacity || 0);
    const historical = Number(capacity.ledger_entry_count || 0);
    const recommended = Number(recommendation.recommended_quantity || 0);

    if (recommendation.status === "capacity_exhausted") {
      host.innerHTML = CreationState({
        tone: "neutral",
        eyebrow: "内容空间",
        title: "暂时没有值得继续做的新内容",
        body: "当前已有内容已经覆盖了这组可用方向。补充新的客户信息或素材后，可以再次检查。",
        content: CreationMetricRow([
          { label: "计划数量", value: requested },
          { label: "当前可用", value: 0 },
          ...(historical ? [{ label: "已有内容", value: historical }] : []),
        ]),
      });
      return;
    }

    if (feasibility.status !== "supported") {
      const route = feasibility.optional_customer_truth_route;
      const processRoute = route?.capability === "process_material";
      host.innerHTML = CreationState({
        tone: "warning",
        eyebrow: "创作条件",
        title: `当前有 ${available} 个值得做的内容方向`,
        body: processRoute
          ? "这些内容方向本身有效，但当前已批准的创作结构还不能支持这批内容。"
          : safeCreationMessage(
            feasibility.humanized_reason,
            "但现有创作结构暂时不能支持这批内容。",
          ),
        content: `
          ${CreationMetricRow([
            { label: "计划数量", value: requested },
            { label: "内容方向", value: available },
            { label: "可生产", value: 0 },
          ])}
          <p class="creation-governance-line">内容方向与创作结构分别判断；客户档案仍然有效。</p>
          ${processRoute ? `<p class="creation-governance-line">只有客户确实存在稳定、真实的服务流程时才需要补充；不需要为了生成内容而编写不存在的信息。</p>` : ""}`,
        actions: `
          <button class="btn btn-secondary" type="button" data-adjust-quantity>返回调整</button>
          ${processRoute ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(preview.business.business_id)}/supplement?gap=process_material" data-route>客户有真实流程，去补充</a>` : ""}`,
      });
      bindAdjustQuantity(host);
      return;
    }

    const limited = recommendation.status === "capacity_limited";
    entryForm?.classList.toggle("has-capacity-result", Boolean(recommendation.can_continue));
    confirmationKey = newConfirmationKey();
    const gaps = capacity.content_gap_summary || [];
    host.innerHTML = CreationState({
      tone: limited ? "warning" : "success",
      eyebrow: "内容方向",
      title: `当前有 ${available} 个值得做的内容方向`,
      body: limited
        ? `你计划做 ${requested} 条，本次确认 ${recommended} 条；现有创作结构可以支持。系统不会为了凑够数量重复已经做过的内容。`
        : `你计划做 ${requested} 条，本次确认 ${recommended} 条；现有创作结构可以支持。`,
      content: `
        ${CreationMetricRow([
          { label: "计划数量", value: requested },
          { label: "内容方向", value: available },
          { label: "本次确认", value: recommended },
        ])}
        ${gaps.length ? `
          <details class="creation-evidence">
            <summary>查看后续补充方向</summary>
            <ul>${gaps.map((gap) => `<li>${escapeHtml(gap)}</li>`).join("")}</ul>
          </details>` : ""}
        <p class="creation-governance-line">本次结果只判断内容是否值得继续做，不代表已获得相关素材使用权。</p>`,
      actions: recommendation.can_continue ? `
        <button id="content-generation-next" class="btn btn-primary" type="button">按 ${recommended} 条继续</button>
        <button class="btn btn-secondary" type="button" data-adjust-quantity>调整数量</button>` : "",
    });
    bindAdjustQuantity(host);
    const next = host.querySelector("#content-generation-next");
    next?.addEventListener("click", async () => {
      const key = confirmationKey || newConfirmationKey();
      confirmationKey = key;
      next.disabled = true;
      next.textContent = "正在创建本次创作…";
      try {
        const response = await api("/api/create/confirm", {
          method: "POST",
          body: JSON.stringify({
            business_id: preview.business.business_id,
            speaker_id: preview.speaker.speaker_id,
            profile,
            requested_quantity: requested,
            confirmed_quantity: recommended,
            idempotency_key: key,
          }),
        });
        const result = response.result;
        renderRequestEstablished(host, {
          requestId: result.request_id,
          businessId: preview.business.business_id,
          profile,
          requestedQuantity: requested,
          confirmedQuantity: result.confirmed_quantity,
          handoffReady: true,
          recovered: Boolean(result.recovered),
        });
        lockEntryForm(result.recovered ? "继续上次素材混剪创作" : "本次创作已创建");
        bindResolveSourcesButton(host, result.request_id);
        showToast(result.recovered ? "已恢复上次创作。" : "本次创作已创建。");
      } catch (error) {
        if (error.detail?.preflight) {
          renderResult(error.detail.preflight);
          showToast("创作条件已经变化，已显示最新检查结果。");
          return;
        }
        showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "本次创作暂时无法创建，请稍后重试。"));
        if (next.isConnected) {
          next.disabled = false;
          next.textContent = `按 ${recommended} 条继续`;
        }
      }
    });
  }

  function renderForm(data) {
    options = data;
    const customers = (data.customers || []).filter((customer) => customer.creation_ready);
    if (!customers.length) {
      app.innerHTML = shell("创作", `
        <main class="page page-form">
          ${pageHeading("", "创作", "选择客户、出镜人和内容类型，开始一次新的内容创作。")}
          <section class="state-panel state-empty">
            <h2>还没有可用于创作的客户</h2>
            <p>请先确认客户档案，并确认至少一位出镜人。</p>
            <a class="btn btn-primary" href="/customers" data-route>查看客户</a>
          </section>
        </main>`);
      bindCommonActions();
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const initialCustomer = customers.find((customer) => customer.business_id === params.get("business_id")) || customers[0];
    const speakers = approvedSpeakers(initialCustomer);
    const initialSpeaker = speakers.find((speaker) => speaker.speaker_id === params.get("speaker_id")) || speakers[0];

    app.innerHTML = shell("创作", `
      <main class="page create-entry-page">
        ${pageHeading("", "创作", "选择客户、出镜人和内容类型，开始一次新的内容创作。")}
        <div class="create-workflow">
          <section class="work-surface create-entry-card">
            <form id="content-entry-form" novalidate>
              <div class="creation-entry-fields">
                <div class="field">
                  <label for="create-business">客户</label>
                  <select id="create-business" required>
                    ${customers.map((customer) => `<option value="${escapeHtml(customer.business_id)}" ${customer.business_id === initialCustomer.business_id ? "selected" : ""}>${escapeHtml(customer.display_name)}</option>`).join("")}
                  </select>
                </div>
                <div class="field">
                  <label for="create-speaker">出镜人</label>
                  <select id="create-speaker" required>
                    ${speakers.map((speaker) => `<option value="${escapeHtml(speaker.speaker_id)}" ${speaker.speaker_id === initialSpeaker?.speaker_id ? "selected" : ""}>${escapeHtml(speaker.display_name)}${speaker.public_role ? ` · ${escapeHtml(speaker.public_role)}` : ""}</option>`).join("")}
                  </select>
                  <p class="field-hint" data-speaker-empty ${speakers.length ? "hidden" : ""}>还没有可用的出镜人。请先在客户页面确认至少一位出镜人。</p>
                </div>
                <fieldset class="field creation-type-field">
                  <legend>内容类型</legend>
                  <div class="profile-choice-grid">
                    <label class="profile-choice selected">
                      <input type="radio" name="create-profile" value="mix" checked>
                      <strong>素材混剪</strong>
                      <span>结合客户真实信息和可用参考，生成新的选题与视频文案。</span>
                    </label>
                    <label class="profile-choice">
                      <input type="radio" name="create-profile" value="news">
                      <strong>新闻体</strong>
                      <span>用短促、连续的信息节奏表达客户真实内容。</span>
                    </label>
                  </div>
                </fieldset>
                <fieldset class="field creation-type-field" id="create-news-modes" hidden>
                  <legend>新闻体创作模式</legend>
                  <div class="profile-choice-grid">
                    ${data.novel_news?.available === true ? `<label class="profile-choice selected">
                      <input type="radio" name="create-news-mode" value="novel_content" checked>
                      <strong>创作新内容${data.novel_news.verification_badge ? " <span class=\"creation-verification-badge\">验证中</span>" : ""}</strong>
                      <span>从客户真实信息中寻找新的内容方向，用新闻体形式表达。</span>
                    </label>` : ""}
                    <label class="profile-choice ${data.novel_news?.available === true ? "" : "selected"}">
                      <input type="radio" name="create-news-mode" value="cross_profile_repurpose" ${data.novel_news?.available === true ? "" : "checked"}>
                      <strong>重新表达已有内容</strong>
                      <span>把以前已经讲过的重要信息重新组织成新闻体，不新增事实。</span>
                    </label>
                  </div>
                </fieldset>
                <div class="field quantity-field" id="create-quantity-field">
                  <label for="create-quantity">计划生成</label>
                  <div class="quantity-control">
                    <input id="create-quantity" type="number" min="1" max="20" step="1" value="4" inputmode="numeric" required>
                    <span>条</span>
                  </div>
                  <span class="field-hint">系统会先检查当前还有多少值得做的新内容。</span>
                </div>
                <div id="content-entry-error" class="form-error" role="alert"></div>
                <button id="check-content-capacity" class="btn btn-primary" type="submit" ${speakers.length ? "" : "disabled"}>查看可创作内容</button>
              </div>
              <div class="creation-entry-locked" data-creation-entry-locked hidden></div>
            </form>
          </section>
          <div id="capacity-preview-result"></div>
        </div>
      </main>`);

    bindCommonActions();
    syncProfileSpecificUi();
    const business = document.querySelector("#create-business");
    const speaker = document.querySelector("#create-speaker");
    const host = document.querySelector("#capacity-preview-result");

    business.addEventListener("change", async () => {
      unlockEntryForm();
      syncSpeakerOptions(selectedCustomer(business.value));
      host.innerHTML = "";
      confirmationKey = null;
      lockEntryForm("正在检查现有创作…");
      await restoreSelectedProfileRequest();
    });
    speaker.addEventListener("change", () => {
      host.innerHTML = "";
      document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
      confirmationKey = null;
    });
    document.querySelectorAll(".profile-choice input").forEach((input) => {
      input.addEventListener("change", async () => {
        document.querySelectorAll(".profile-choice").forEach((label) => label.classList.toggle("selected", label.querySelector("input").checked));
        host.innerHTML = "";
        document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
        confirmationKey = null;
        syncProfileSpecificUi();
        lockEntryForm("正在检查现有创作…");
        await restoreSelectedProfileRequest();
      });
    });
    document.querySelector("#create-quantity").addEventListener("input", () => {
      host.innerHTML = "";
      document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
      confirmationKey = null;
    });

    document.querySelector("#content-entry-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorBox = document.querySelector("#content-entry-error");
      errorBox.classList.remove("visible");
      const profile = selectedProfileValue();
      const speakerId = speaker.value;
      if (!speakerId) {
        errorBox.textContent = "还没有可用的出镜人，请先在客户页面确认至少一位出镜人。";
        errorBox.classList.add("visible");
        return;
      }
      const button = document.querySelector("#check-content-capacity");
      host.innerHTML = "";
      confirmationKey = null;
      button.disabled = true;
      button.textContent = "正在查看…";
      try {
        if (profile === "news" && selectedNewsModeValue() === "novel_content") {
          const result = await api("/api/create/novel-news/preview", {
            method: "POST",
            body: JSON.stringify({ business_id: business.value, speaker_id: speakerId }),
          });
          novelNewsViews.renderPreview(host, result.projection, {
            businessId: business.value, speakerId,
            onRequestCreated: async (requestId) => {
              lockEntryForm("继续新闻体 · 创作新内容");
              await novelNewsViews.restore(requestId, host);
            },
          });
          document.querySelector("#content-entry-form")?.classList.toggle(
            "has-capacity-result", Number(result.projection?.production_ready_count || 0) > 0,
          );
        } else if (profile === "news") {
          const result = await api("/api/create/news/preview", {
            method: "POST",
            body: JSON.stringify({ business_id: business.value, speaker_id: speakerId }),
          });
          newsDeliveryViews.renderPreview(host, result.preview, {
            onRequestCreated: async (requestId) => {
              lockEntryForm("继续新闻体创作");
              await newsDeliveryViews.restore(requestId, host);
            },
          });
          document.querySelector("#content-entry-form")?.classList.toggle(
            "has-capacity-result",
            Boolean(result.preview?.available && Number(result.preview?.eligible_source_count || 0) > 0),
          );
        } else {
          const quantity = Number(document.querySelector("#create-quantity").value);
          if (!Number.isInteger(quantity) || quantity < 1 || quantity > 20) {
            throw new Error("请输入 1–20 之间的整数。");
          }
          const result = await api("/api/create/capacity-preview", {
            method: "POST",
            body: JSON.stringify({ business_id: business.value, speaker_id: speakerId, profile, quantity }),
          });
          renderResult(result.preview);
        }
        host.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        errorBox.textContent = safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前可创作内容暂时无法读取，请稍后重试。");
        errorBox.classList.add("visible");
      } finally {
        button.disabled = false;
        button.textContent = "查看可创作内容";
      }
    });
  }

  async function renderCreate() {
    skeletonPage("创作");
    try {
      const data = await api("/api/create/options");
      renderForm(data);
      if (!document.querySelector("#content-entry-form")) return;
      lockEntryForm("正在检查现有创作…");
      await restoreSelectedProfileRequest();
    } catch (error) {
      renderLoadError("创作入口暂时无法读取", error);
    }
  }

  return { renderCreate };
}
