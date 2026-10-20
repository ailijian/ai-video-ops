import { escapeHtml } from "./case-components.js?v=flow-closure-2";
import { createPreparationOperation, pinNewsRequestLocation } from "./creation-entry-flow.js?v=entry-auto-2";
import { createContentDeliveryViews } from "./content-delivery-views.js?v=news-review-ui-2";
import { createNewsDeliveryViews } from "./news-delivery-views.js?v=news-review-ui-2";
import { createNovelNewsViews } from "./novel-news-views.js?v=news-review-ui-2";
import {
  CreationHeader,
  CreationMetricRow,
  CreationCapacityState,
  CreationState,
  CreationSummary,
  safeCreationMessage,
} from "./creation-components.js?v=news-review-ui-2";

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
  let entryVersion = 0;
  let previewTimer = null;
  let previewVersion = 0;
  let preparing = false;
  let checkCurrentEntry = null;

  function currentEntryGuard() {
    const version = previewVersion;
    const route = window.location.href;
    const form = document.querySelector("#content-entry-form");
    return () => version === previewVersion && route === window.location.href && form === document.querySelector("#content-entry-form");
  }

  function schedulePreview(delay = 300) {
    const form = document.querySelector("#content-entry-form");
    if (!form || form.classList.contains("completed") || preparing) return;
    clearTimeout(previewTimer);
    const version = ++previewVersion;
    confirmationKey = null;
    document.querySelector("#capacity-preview-result").innerHTML = CreationState({
      tone: "running", title: "正在检查创作条件", body: "正在核对所选类型、数量和可用创作结构。" });
    previewTimer = setTimeout(() => { void checkCurrentEntry?.(version); }, delay);
  }

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
      { label: "客户", value: selectedCustomer(business?.value)?.display_name || business?.selectedOptions?.[0]?.textContent?.trim() || "" },
      { label: "出镜人", value: speaker?.selectedOptions?.[0]?.textContent?.trim() || "" },
      { label: "内容类型", value: profile === "news" ? "新闻体" : "素材混剪" },
      ...(profile === "news" ? [{ label: "创作模式", value: selectedNewsModeValue() === "novel_content" ? "创作新内容" : "重新表达已有内容" }] : []),
      ...(form?.dataset.confirmedQuantity
        ? [
            { label: "计划数量", value: `${Number(form.dataset.requestedQuantity || 0)} 条` },
            { label: "本次确认", value: `${Number(form.dataset.confirmedQuantity || 0)} 条` },
          ]
        : [{ label: "计划数量", value: `${Number(quantity?.value || 0)} 条` }]),
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
        if (preparing) return;
        document.querySelector("#capacity-preview-result").innerHTML = "";
        unlockEntryForm();
        schedulePreview();
      });
      compact.querySelector("[data-edit-creation-selection]").disabled = preparing;
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
    if (quantityField) quantityField.hidden = false;
    const newsModes = document.querySelector("#create-news-modes");
    if (newsModes) newsModes.hidden = !news;
    if (quantityInput) {
      if (news) {
        if (quantityInput.max !== "1") quantityInput.dataset.mixQuantity = quantityInput.value;
        quantityInput.max = "1";
        quantityInput.value = "1";
      } else if (quantityInput.max === "1") {
        quantityInput.max = "20";
        quantityInput.value = quantityInput.dataset.mixQuantity || "4";
      }
      quantityInput.readOnly = news;
      quantityInput.disabled = Boolean(document.querySelector("#content-entry-form")?.classList.contains("completed"));
    }
    const quantityHint = document.querySelector("#create-quantity-hint");
    if (quantityHint) quantityHint.textContent = news
      ? "当前新闻体每次制作 1 条视频，视频内的短信息不另计条数。"
      : "系统会先检查当前还有多少值得做的新内容。";
    if (submit && !submit.closest("form")?.classList.contains("completed")) submit.textContent = "查看可创作内容";
    if (submit) submit.hidden = true;
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
        title: "正在恢复原创作请求",
        body: "本次选择已经保留，可以安全继续。",
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
        title: "正在核对创作依据",
        body: "系统正在整理客户信息、历史内容和可用参考。",
      });
    }
    return CreationState({
      tone: "success",
      eyebrow: "创作准备",
      title: "准备完成",
      body: "已经找到足够的创作依据。",
    });
  }

  function preparationOperation(confirmation, active = null) {
    const form = document.querySelector("#content-entry-form");
    const route = window.location.href;
    const version = entryVersion;
    const host = document.querySelector("#capacity-preview-result");
    if (form) {
      form.dataset.requestedQuantity = String(confirmation.requested_quantity);
      form.dataset.confirmedQuantity = String(confirmation.confirmed_quantity);
    }
    const current = () => entryVersion === version && window.location.href === route && document.querySelector("#content-entry-form") === form;
    const operation = createPreparationOperation({ api, confirmation, active, isCurrent: current,
      onStage(title) {
        if (!current()) return;
        host.innerHTML = CreationState({ tone: "running", eyebrow: "创作准备", title,
          body: "本次选择已保留，准备完成后再由你生成内容。" });
        lockEntryForm(title);
      },
    });
    return async function resume() {
      if (preparing || !current()) return;
      preparing = true;
      try {
        if (await operation.continue()) {
          preparing = false;
          if (confirmation.profile === "news") await restoreActiveNovelNewsRequest();
          else await restoreActiveRequest(false);
        }
      } catch (error) {
        if (!current()) return;
        preparing = false;
        if (error.detail?.preflight && !operation.requestId) {
          unlockEntryForm();
          if (confirmation.profile === "news") schedulePreview(0);
          else renderResult(error.detail.preflight);
          showToast("创作条件已经变化，请核对最新结果后再确认。");
          return;
        }
        host.innerHTML = CreationState({ tone: "warning", title: "创作准备尚未完成",
          body: safeCreationMessage(error.detail?.next_action || error.message, "请继续原操作，系统会核对当前授权和来源。"),
          content: `<p>已保存的步骤会继续保留，不会重新开始另一条创作。</p>`,
          actions: `<button id="continue-creation-preparation" class="btn btn-primary" type="button">继续准备</button>` });
        lockEntryForm("创作准备尚未完成");
        host.querySelector("#continue-creation-preparation")?.addEventListener("click", resume);
      } finally {
        if (current()) preparing = false;
      }
    };
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
    const current = currentEntryGuard();
    const business = document.querySelector("#create-business");
    const host = document.querySelector("#capacity-preview-result");
    if (!business || !host) return false;
    try {
      const response = await api(`/api/create/news/active?business_id=${encodeURIComponent(business.value)}`);
      if (!current()) return true;
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
      const form = document.querySelector("#content-entry-form");
      if (form) { form.dataset.requestedQuantity = "1"; form.dataset.confirmedQuantity = "1"; }
      lockEntryForm("继续上次新闻体创作");
      pinNewsRequestLocation({requestId:active.request_id,businessId:business.value,speakerId:active.speaker_id,
        newsMode:'cross_profile_repurpose'});
      await newsDeliveryViews.restore(active.request_id, host);
      return true;
    } catch (error) {
      if (!current()) return true;
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
    const current = currentEntryGuard();
    const business = document.querySelector("#create-business");
    const host = document.querySelector("#capacity-preview-result");
    if (!business || !host) return false;
    try {
      const response = await api(`/api/create/active-request?business_id=${encodeURIComponent(business.value)}&profile=news`);
      if (!current()) return true;
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
      const form = document.querySelector("#content-entry-form");
      if (form) { form.dataset.requestedQuantity = "1"; form.dataset.confirmedQuantity = "1"; }
      lockEntryForm("继续上次新闻体 · 创作新内容");
      pinNewsRequestLocation({requestId:active.request_id,businessId:business.value,speakerId:active.speaker_id,
        newsMode:'novel_content'});
      if (active.handoff_ready === false) {
        host.innerHTML = CreationState({
          title: "继续上次新闻体创作",
          body: "内容方向已经确认，继续准备创作来源；不会重新建立内容方向。",
          actions: `<button type="button" class="btn btn-primary" data-recover-novel-handoff>继续准备</button>`,
        });
        const resume = preparationOperation({
          business_id: active.business_id, speaker_id: active.speaker_id,
          profile: "news", requested_quantity: 1, confirmed_quantity: 1,
          selected_opportunity_id: active.selected_opportunity_id,
          idempotency_key: `resume_${active.request_id}`,
        }, active);
        host.querySelector("[data-recover-novel-handoff]")?.addEventListener("click", resume);
        return true;
      }
      await novelNewsViews.restore(active.request_id, host);
      return true;
    } catch (error) {
      if (!current()) return true;
      host.innerHTML = CreationState({
        tone: "error", title: "新闻体创作暂时无法恢复",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "请查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      lockEntryForm("暂时无法继续");
      return true;
    }
  }

  async function restoreActiveRequest(autoPrepare = true) {
    const version = previewVersion;
    const route = window.location.href;
    const form = document.querySelector("#content-entry-form");
    const business = document.querySelector("#create-business");
    const host = document.querySelector("#capacity-preview-result");
    if (!business || !host) return false;
    let active;
    try {
      const response = await api(`/api/create/active-request?business_id=${encodeURIComponent(business.value)}`);
      active = response.active_request;
    } catch (error) {
      if (version !== previewVersion || route !== window.location.href || form !== document.querySelector("#content-entry-form")) return true;
      host.innerHTML = CreationState({
        tone: "error",
        title: "这次创作暂时无法继续",
        body: safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前状态无法安全恢复，请稍后重试或查看任务记录。"),
        actions: `<a class="btn btn-secondary" href="/tasks">查看任务</a>`,
      });
      lockEntryForm("暂时无法继续");
      return true;
    }
    if (version !== previewVersion || route !== window.location.href || form !== document.querySelector("#content-entry-form")) return true;
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
    if (active.handoff_ready === false || !active.source_plan_artifact_exists) {
      const resume = preparationOperation({ business_id: active.business_id, speaker_id: active.speaker_id,
        profile: active.profile, requested_quantity: Number(active.requested_quantity),
        confirmed_quantity: Number(active.confirmed_quantity), idempotency_key: `resume_${active.request_id}` }, active);
      if (autoPrepare) await resume();
      else {
        host.innerHTML = CreationState({ tone: "warning", title: "创作准备尚未完成", body: "原请求已保留，请继续完成来源准备。",
          actions: `<button id="continue-creation-preparation" class="btn btn-primary" type="button">继续准备</button>` });
        host.querySelector("#continue-creation-preparation")?.addEventListener("click", resume);
      }
      return true;
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
      schedulePreview();
    });
  }

  function renderResult(preview) {
    const version = previewVersion;
    const form = document.querySelector("#content-entry-form");
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
    host.innerHTML = CreationCapacityState({
      requested, available, confirmed: recommended, limited,
      details: `
        ${gaps.length ? `
          <details class="creation-evidence">
            <summary>查看后续补充方向</summary>
            <ul>${gaps.map((gap) => `<li>${escapeHtml(gap)}</li>`).join("")}</ul>
          </details>` : ""}`,
      actions: recommendation.can_continue ? `
        <button id="content-generation-next" class="btn btn-primary" type="button">开始本次创作（${recommended} 条）</button>
        <button class="btn btn-secondary" type="button" data-adjust-quantity>调整数量</button>` : "",
    });
    bindAdjustQuantity(host);
    const next = host.querySelector("#content-generation-next");
    next?.addEventListener("click", async () => {
      if (preparing || version !== previewVersion || form !== document.querySelector("#content-entry-form")) return;
      const key = confirmationKey || newConfirmationKey();
      confirmationKey = key;
      next.disabled = true;
      next.textContent = "正在创建本次创作…";
      const resume = preparationOperation({
            business_id: preview.business.business_id,
            speaker_id: preview.speaker.speaker_id,
            profile,
            requested_quantity: requested,
            confirmed_quantity: recommended,
            idempotency_key: key,
      });
      await resume();
    });
  }

  function renderForm(data) {
    options = data;
    const customers = (data.customers || []).filter((customer) => customer.creation_ready);
    const context = data.customer_context;
    const back = context ? `<a class="back-link" href="/customers/${encodeURIComponent(context.business_id)}" data-route>← 返回 ${escapeHtml(context.display_name)}</a>` : `<a class="back-link" href="/customers" data-route>← 返回客户列表</a>`;
    if (!customers.length) {
      app.innerHTML = shell("创作", `
        <main class="page page-form">
          ${back}
          ${pageHeading("", context ? `${context.display_name} · 创作` : "创作", "进入创作前仍需核对正式档案和当前创作条件。")}
          <section class="state-panel state-empty">
            <h2>${context ? "当前客户暂不能创作" : "还没有可用于创作的客户"}</h2>
            <p>${escapeHtml((data.customers || [])[0]?.authority_blocker?.message || "请先完成客户档案与适用出镜人的独立审核。")}</p>
            <a class="btn btn-primary" href="${escapeHtml((data.customers || [])[0]?.authority_blocker?.url || (context ? `/customers/${encodeURIComponent(context.business_id)}` : "/customers"))}" data-route>${(data.customers || [])[0]?.authority_blocker?.url ? "查看待核实事项" : "查看客户资料"}</a>
          </section>
        </main>`);
      bindCommonActions();
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const initialCustomer = customers.find((customer) => customer.business_id === params.get("business_id"));
    if (!initialCustomer) throw new Error("指定客户当前无法安全进入创作，请返回客户核对。");
    const speakers = approvedSpeakers(initialCustomer);
    const initialSpeaker = speakers.find((speaker) => speaker.speaker_id === params.get("speaker_id")) || speakers[0];

    app.innerHTML = shell("创作", `
      <main class="page create-entry-page">
        ${back}
        ${pageHeading("", `${initialCustomer.display_name} · 创作`, "选择出镜人与内容类型，系统会重新核对当前创作条件。")}
        <div class="create-workflow">
          <section class="work-surface create-entry-card">
            <form id="content-entry-form" novalidate>
              <div class="creation-entry-fields">
                <div class="field" hidden>
                  <label for="create-business">客户</label>
                  <select id="create-business" required>
                    <option value="${escapeHtml(initialCustomer.business_id)}" selected>${escapeHtml(initialCustomer.display_name)}</option>
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
                      <strong>创作新内容${data.novel_news.verification_badge ? " <span class=\"creation-verification-badge\" title=\"当前为隔离验收环境\">隔离验收</span>" : ""}</strong>
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
                  <span class="field-hint" id="create-quantity-hint">系统会先检查当前还有多少值得做的新内容。</span>
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
    const profileHint = params.get("profile");
    if (profileHint === "news") {
      document.querySelector('input[name="create-profile"][value="news"]').checked = true;
      document.querySelectorAll(".profile-choice").forEach(label => label.classList.toggle("selected", label.querySelector("input").checked));
      const newsMode = document.querySelector(`input[name="create-news-mode"][value="${params.get("news_mode") === "novel_content" ? "novel_content" : "cross_profile_repurpose"}"]`);
      if (newsMode) newsMode.checked = true;
    }
    syncProfileSpecificUi();
    const business = document.querySelector("#create-business");
    const speaker = document.querySelector("#create-speaker");
    const host = document.querySelector("#capacity-preview-result");

    business.addEventListener("change", async () => {
      ++previewVersion;
      unlockEntryForm();
      syncSpeakerOptions(selectedCustomer(business.value));
      host.innerHTML = "";
      confirmationKey = null;
      lockEntryForm("正在检查现有创作…");
      if (!await restoreSelectedProfileRequest()) schedulePreview();
    });
    speaker.addEventListener("change", () => {
      host.innerHTML = "";
      document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
      confirmationKey = null;
      schedulePreview();
    });
    document.querySelectorAll(".profile-choice input").forEach((input) => {
      input.addEventListener("change", async () => {
        ++previewVersion;
        document.querySelectorAll(".profile-choice").forEach((label) => label.classList.toggle("selected", label.querySelector("input").checked));
        host.innerHTML = "";
        document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
        confirmationKey = null;
        syncProfileSpecificUi();
        lockEntryForm("正在检查现有创作…");
        if (!await restoreSelectedProfileRequest()) schedulePreview();
      });
    });
    document.querySelector("#create-quantity").addEventListener("input", () => {
      host.innerHTML = "";
      document.querySelector("#content-entry-form")?.classList.remove("has-capacity-result");
      confirmationKey = null;
      schedulePreview();
    });

    const entryForm = document.querySelector("#content-entry-form");
    const route = window.location.href;
    checkCurrentEntry = async (version) => {
      const current = () => version === previewVersion && route === window.location.href && entryForm === document.querySelector("#content-entry-form");
      if (!current() || entryForm.classList.contains("completed")) return;
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
          if (Number(document.querySelector("#create-quantity").value) !== 1) {
            throw new Error("当前新闻体每次制作 1 条视频，请按当前数量继续。");
          }
          const result = await api("/api/create/novel-news/preview", {
            method: "POST",
            body: JSON.stringify({ business_id: business.value, speaker_id: speakerId }),
          });
          if (!current()) return;
          novelNewsViews.renderPreview(host, result.projection, {
            businessId: business.value, speakerId,
            requestedQuantity: Number(document.querySelector("#create-quantity").value),
            createPreparation: (confirmation) => preparationOperation(confirmation),
          });
          document.querySelector("#content-entry-form")?.classList.toggle(
            "has-capacity-result", Number(result.projection?.production_ready_count || 0) > 0,
          );
        } else if (profile === "news") {
          const result = await api("/api/create/news/preview", {
            method: "POST",
            body: JSON.stringify({ business_id: business.value, speaker_id: speakerId }),
          });
          if (!current()) return;
          newsDeliveryViews.renderPreview(host, result.preview, {
            onRequestCreated: async (requestId) => {
              const form = document.querySelector("#content-entry-form");
              if (form) { form.dataset.requestedQuantity = "1"; form.dataset.confirmedQuantity = "1"; }
              lockEntryForm("继续新闻体创作");
              pinNewsRequestLocation({requestId,businessId:business.value,speakerId,newsMode:'cross_profile_repurpose'});
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
          if (!current()) return;
          renderResult(result.preview);
        }
      } catch (error) {
        if (!current()) return;
        const missingHistory = ["NEWS_DELIVERY_CONTENT_LEDGER_MISSING", "NEWS_DELIVERY_SOURCE_NOT_FOUND",
          "NEWS_DELIVERY_SOURCE_NOT_STRONG_MEMORY", "NEWS_DELIVERY_SOURCE_NOT_ELIGIBLE"].includes(error.detail?.code);
        host.innerHTML = CreationState({ tone: "warning", title: missingHistory ? "暂无可用的历史内容" : "创作条件暂未确认",
          body: safeCreationMessage(error.detail?.next_action || error.message, "请重新检查当前创作条件。"),
          actions: `<button type="button" class="btn btn-secondary" data-recheck-entry>重新检查</button>` });
        host.querySelector("[data-recheck-entry]")?.addEventListener("click", () => schedulePreview(0));
        errorBox.textContent = safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message, "当前可创作内容暂时无法读取，请稍后重试。");
        errorBox.classList.add("visible");
      } finally {
        if (!current()) return;
        button.disabled = false;
        button.textContent = "查看可创作内容";
      }
    };
    entryForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (preparing || entryForm.classList.contains("completed")) return;
      clearTimeout(previewTimer);
      await checkCurrentEntry(++previewVersion);
    });
  }

  async function renderCreate() {
    ++entryVersion;
    ++previewVersion;
    clearTimeout(previewTimer);
    preparing = false;
    checkCurrentEntry = null;
    const route = window.location.href;
    skeletonPage("创作");
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("request_id")) {
        const requestedMode = params.get("profile") === "news" ? params.get("news_mode") === "novel_content" ? "novel" : "repurpose" : params.has("profile") ? "mix" : null;
        const query = new URLSearchParams({request_id:params.get("request_id")});
        if (requestedMode) query.set("mode", requestedMode);
        if (params.has("business_id")) query.set("business_id", params.get("business_id"));
        const context = await api(`/api/create/request-context?${query}`);
        if (window.location.href !== route) return;
        const mode = context.mode;
        app.innerHTML = shell("创作记录", `<main class="page create-entry-page"><a class="back-link" href="/customers/${encodeURIComponent(context.business_id)}/content" data-route>← 返回 ${escapeHtml(context.display_name)} 的作品记录</a>${pageHeading("", `${context.display_name} · 创作记录`, "恢复原请求和审核结果；不会自动创建新任务。")}<div id="capacity-preview-result"><div id="content-delivery-host"></div></div></main>`);
        bindCommonActions();
        if (["abandoned", "cancelled"].includes(context.status) || (context.status === 'completed' && mode === 'mix')) {
          document.querySelector("#capacity-preview-result").innerHTML = CreationState({title:"本次创作已结束", body:"原请求和历史结果仍然保留；不会重新启动已结束的任务。"});
          return;
        }
        if (mode === "repurpose") await newsDeliveryViews.restore(context.request_id, document.querySelector("#capacity-preview-result"));
        else if (mode === "novel") await novelNewsViews.restore(context.request_id, document.querySelector("#capacity-preview-result"));
        else await deliveryViews.restore(context.request_id);
        return;
      }
      if (!params.get("business_id")) {
        app.innerHTML = shell("选择创作客户", `<main class="page page-form">${pageHeading("", "先选择一个客户", "从客户进入新的创作，历史请求可以从任务或客户作品记录继续。")}<a class="btn btn-primary" href="/customers" data-route>去客户列表</a><a class="btn btn-secondary" href="/tasks" data-route>查看已有任务</a></main>`);
        bindCommonActions();
        return;
      }
      const data = await api(`/api/create/options?business_id=${encodeURIComponent(params.get("business_id"))}`);
      if (window.location.href !== route) return;
      renderForm(data);
      if (!document.querySelector("#content-entry-form")) return;
      lockEntryForm("正在检查现有创作…");
      if (!await restoreSelectedProfileRequest()) schedulePreview(0);
    } catch (error) {
      if (window.location.href !== route) return;
      renderLoadError("创作入口暂时无法读取", error);
    }
  }

  return { renderCreate };
}
