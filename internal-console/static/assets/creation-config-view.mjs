import { escapeHtml } from "./case-components.js?v=flow-closure-2";
import { safeCreationMessage } from "./creation-components.js?v=flow-closure-2";
import { CONFIG_TYPES, OPERATING_STAGES, createConfiguration, changeConfiguration, configurationSummary } from "./creation-config-model.mjs?v=stage-presets-1";
import { createConfigurationSession } from "./creation-config-session.mjs?v=cbux1-b234-3";

export function scopedConfigurationContext(data, businessId, requestedSpeaker = "") {
  const customers = data.customers || [];
  if (data.customer_context?.business_id !== businessId || customers.length > 1 || (customers.length === 1 && customers[0].business_id !== businessId)) {
    throw Error("客户资料无法准确对应，请返回客户列表重新进入。");
  }
  if (!customers.length) return { customer: { business_id: businessId, display_name: data.customer_context.display_name },
    speakers: [], speakerId: "", blocked: true, blockReason: "当前客户业务或人物资料尚未达到创作条件，请先核对客户资料。" };
  const customer = customers[0];
  const speakers = (customer.speakers || []).filter(person => person.status === "approved");
  if (requestedSpeaker && !speakers.some(person => person.speaker_id === requestedSpeaker)) throw Error("指定出镜人当前不适用，请重新核对。");
  return { customer, speakers, speakerId: requestedSpeaker || (speakers.length === 1 ? speakers[0].speaker_id : ""),
    blocked: customer.business_persona_status !== "approved" || !customer.creation_ready || !speakers.length,
    blockReason: safeCreationMessage(customer.authority_blocker?.message, "当前客户或出镜资料还需核对。") };
}
export function repurposeSelectionMarkup(state, context) {
  if (!(state.quantities.repurpose > 0)) return '';
  const esc=escapeHtml, selected=state.repurposeSourceIds || [], lookup=context.repurpose || {};
  const sources=lookup.sources || [], missing=lookup.loaded ? selected.filter(id=>!sources.some(s=>s.source_content_id===id)) : [];
  const status = source => ({approved:'已审核',exported:'已交付',published:'已发布'}[source.source_status] || '已审核来源');
  const matched = selected.length === state.quantities.repurpose && !missing.length;
  return `<section class="batch-repurpose-sources" aria-labelledby="config-source-heading"><h4 id="config-source-heading">选择已有内容</h4>
    <p>请选择已审核、当前允许重新表达的内容。一条内容对应一个视频，不重复计入新增语义。</p>
    <p id="config-repurpose-count" role="status">已选择 ${selected.length} 条内容，本次需要 ${state.quantities.repurpose} 条。${selected.length > state.quantities.repurpose ? `请明确取消多出的 ${selected.length-state.quantities.repurpose} 条；系统不会代选。` : ''}</p>
    ${selected.length ? `<ul class="batch-selected-sources">${selected.map((id,index)=>{
      const source=sources.find(s=>s.source_content_id===id);
      return `<li>${source ? `<strong>${esc(source.source_title || '已审核的历史内容')}</strong><small>${status(source)} · 当前可改编</small>` : `此前选择的第 ${index+1} 条内容 · ${lookup.loaded ? '当前不可用，请重新选择' : '等待重新核对来源'}`}</li>`;
    }).join('')}</ul>` : ''}
    <button class="btn btn-secondary" type="button" id="config-load-repurpose" aria-expanded="${lookup.open === true}" aria-controls="config-repurpose-list">${lookup.loading ? '正在读取可用内容' : '选择已有内容'}</button>
    ${lookup.error ? `<p role="status">${esc(lookup.error)}</p>` : ''}
    <div id="config-repurpose-list" ${lookup.open ? '' : 'hidden'}>
      ${lookup.loaded && sources.length < state.quantities.repurpose ? `<p class="batch-source-warning" role="status">当前有 ${sources.length} 条可改编内容，本次填写 ${state.quantities.repurpose} 条。请调整数量或明确选择其他合法来源，不会自动换成新创作。</p>` : ''}
      ${lookup.loaded && !sources.length ? '<p>当前没有满足资格要求的已交付历史内容。请先完成原内容的审核与交付，或将本次改编数量调为 0。</p>' : ''}
      ${sources.map(s=>`<label class="batch-repurpose-choice"><input id="config-source-${esc(s.source_content_id)}" type="checkbox" data-repurpose-source value="${esc(s.source_content_id)}" ${selected.includes(s.source_content_id) ? 'checked' : selected.length >= state.quantities.repurpose ? 'disabled' : ''}><span><strong>${esc(s.source_title || '已审核的历史内容')}</strong><small>${status(s)} · 当前可改编</small></span></label>`).join('')}
      ${missing.map((id,index)=>`<label class="batch-repurpose-choice"><input id="config-source-${esc(id)}" type="checkbox" data-repurpose-source value="${esc(id)}" checked><span>此前选项 ${index+1} 当前不可用，请取消后重新选择。</span></label>`).join('')}
      ${lookup.loaded ? `<button type="button" class="btn btn-secondary" id="config-finish-repurpose" ${matched ? '' : 'disabled'}>确认使用这 ${selected.length} 条内容</button>` : ''}
    </div></section>`;
}

const NEWS_SOURCES = [
  ['novel','创作新内容','从已审核客户资料中发掘新的内容主题。'],
  ['repurpose','改编已有内容','选择已经审核的历史内容，重新制作新闻体。'],
];
export function configurationFailureMarkup(failure) {
  return `<span class="batch-config-feedback-icon" aria-hidden="true">!</span><div class="batch-config-feedback-body">
    <h3 id="config-feedback-title">${failure.checking ? '创作资格未通过，暂不能开始' : '本次操作未完成'}</h3>
    <p class="batch-config-feedback-reason">${escapeHtml(failure.message)}</p>
    <p class="batch-config-feedback-next">${escapeHtml(failure.nextAction)}</p>
    ${failure.checking ? '<button type="button" class="btn btn-secondary" id="config-adjust-quantities">调整创作数量</button>' : ''}</div>`;
}
function newsLegacyMarkup(state) {
  const legacy = (!state.repurposeEnabled && state.quantities.repurpose > 0)
    || (state.quantities.repurpose === 0 && (state.repurposeSourceIds || []).length > 0);
  return legacy ? '<p class="batch-source-warning">旧草稿的改编数量、来源或开关不一致。请明确重新确认，不会沿用有歧义的创作意图。<button type="button" class="btn btn-secondary" id="config-reconfirm-news">确认使用当前改编数量</button></p>' : '';
}
function newsSourcesMarkup(state, context, summary) {
  return `<fieldset class="batch-news-group"><legend>新闻体</legend><p class="field-hint">根据已审核的客户资料创作新主题，或把已有内容改编成新闻体视频。</p>
    ${NEWS_SOURCES.map(([key,title,description])=>`<div class="batch-news-source-row"><div><label for="config-${key}">${title}</label><small id="config-${key}-hint">${description}</small></div>
      <div class="batch-quantity-stepper"><button type="button" data-quantity-target="${key}" data-quantity-step="-1" aria-label="减少${title}数量" aria-controls="config-${key}" ${state.quantities[key] === 0 ? 'disabled' : ''}>−</button><input id="config-${key}" type="number" min="0" max="40" step="1" inputmode="numeric" aria-describedby="config-${key}-hint batch-config-errors" value="${state.quantities[key] ?? ''}"><button type="button" data-quantity-target="${key}" data-quantity-step="1" aria-label="增加${title}数量" aria-controls="config-${key}" ${state.quantities[key] >= 40 ? 'disabled' : ''}>+</button></div></div>`).join('')}
    <p class="batch-news-total" aria-live="polite">本次新闻体合计：<strong id="config-news-total">${summary.newsTotal ?? '—'}</strong> 条。<span>创作新内容：<b id="config-news-novel">${state.quantities.novel ?? '—'}</b> 条；改编已有内容：<b id="config-news-repurpose">${state.quantities.repurpose ?? '—'}</b> 条。</span></p>
    <div id="config-news-legacy">${newsLegacyMarkup(state)}</div>
    <div id="config-repurpose-selection">${repurposeSelectionMarkup(state,context)}</div></fieldset>`;
}

export function configurationMarkup(state, context) {
  const summary = configurationSummary(state), esc = escapeHtml;
  const split = state.mode === "stage" && state.stage !== "steady";
  const errorList = summary.errors.map(error => `<li><a href="#config-${error.field}">${esc(error.message)}</a></li>`).join("");
  const stages = Object.entries(OPERATING_STAGES).map(([key, value]) => {
    const [period, title] = value.label.split(" · ");
    return `<label class="batch-stage-option" data-selected="${state.stage === key}"><input id="config-stage-${key}" type="radio" name="operating-stage" data-config-stage value="${key}" ${state.stage === key ? "checked" : ""}><span><small>${esc(period)}</small><strong>${esc(title)}</strong></span></label>`;
  }).join("");
  const speakers = context.speakers.map(person => `<option value="${esc(person.speaker_id)}" ${context.speakerId === person.speaker_id ? "selected" : ""}>${esc(person.display_name)}${person.public_role ? ` · ${esc(person.public_role)}` : ""}</option>`).join("");
  return `<main class="page batch-config-page">
    <a class="back-link" href="/customers/${encodeURIComponent(context.customer.business_id)}" data-route>← 返回客户</a>
    <header class="batch-config-heading"><span class="eyebrow">创作配置</span><h1>安排这次要创作的内容</h1><p>按运营阶段准备，或自由组合。生成之后，内容仍需人工审核。</p></header>
    <section class="batch-config-context"><div><span class="field-label">当前客户</span><strong>${esc(context.customer.display_name)}</strong><p>已带入客户业务档案，已有资料无需重复填写。</p></div><div><label for="config-speaker">适用出镜人</label><select id="config-speaker"><option value="">请选择出镜人</option>${speakers}</select></div></section>
    <p class="batch-config-notice" role="note">确认本次配置后，系统按合法来源逐次生成，保留失败和数量差额。内容审核与发布信息仍须分别人工确认。<a href="/create?business_id=${encodeURIComponent(context.customer.business_id)}${context.speakerId ? `&amp;speaker_id=${encodeURIComponent(context.speakerId)}` : ""}" data-route>进入已有单条创作流程</a></p>
    ${context.blocked ? `<p class="batch-config-warning">${esc(context.blockReason)} <a href="/customers/${encodeURIComponent(context.customer.business_id)}" data-route>查看客户资料</a></p>` : ""}
    ${context.existingBatch ? `<section class="batch-config-surface"><h2>此前已确认的批次</h2><p>目标 ${context.existingBatch.actual_target} 条。查看原批可继续核对进度，重新进入配置不会重复创建任务。</p>
      <div class="batch-config-existing-actions"><a class="btn btn-primary" href="/create/batch?batch_id=${encodeURIComponent(context.existingBatch.batch_id)}" data-route>查看原批进度与成果</a>
      <button type="button" class="btn btn-secondary" id="config-new-batch">用此配置安排新的一批</button></div></section>` : ''}
    ${!context.existingBatch && context.confirmationBlocked ? '<section class="batch-config-surface"><h2>此前确认需要重新核对权限</h2><p>配置草稿仍可编辑，原批次及已有成果保留；本次登录不能沿用此前的授权。</p><button type="button" class="btn btn-secondary" id="config-new-batch">明确建立新一批的配置</button></section>' : ''}
    <form id="batch-config-form" novalidate>
      <section class="batch-config-surface"><h2>1. 选择创作方式</h2><div class="batch-mode-options" role="group" aria-label="创作方式"><button type="button" data-config-mode="stage" aria-pressed="${state.mode === "stage"}">按运营阶段</button><button type="button" data-config-mode="free" aria-pressed="${state.mode === "free"}">自由组合</button></div>
      ${state.mode === "stage" ? `<fieldset id="config-stage" class="batch-stage-picker"><legend>运营阶段</legend><div class="batch-stage-options">${stages}</div></fieldset>${state.stage === "steady" ? `<div class="batch-cycle-fields"><label for="config-cycles">本次安排几个四天周期</label><input id="config-cycles" type="number" min="1" step="1" inputmode="numeric" value="${state.cycles ?? ""}"><label class="batch-checkbox"><input id="config-cyclesConfirmed" type="checkbox" ${state.cyclesConfirmed ? "checked" : ""}>我确认仅安排本次 ${state.cycles ?? "—"} 个周期，不会自动持续创作。</label><p class="field-hint">每周期推荐新闻 1、人设 3、故事 2、高转化 2 条，可调整本次实际数量。</p></div>` : `<p class="field-hint">推荐新闻新创作 ${OPERATING_STAGES[state.stage].news} 条、人设 ${OPERATING_STAGES[state.stage].persona} 条、故事 ${OPERATING_STAGES[state.stage].story} 条，可修改本次实际数量。</p>`}` : `<p class="field-hint">每种类型都可以为 0，按本次需要自由填写。</p>`}</section>
      <section class="batch-config-surface"><h2 id="config-quantities-heading" tabindex="-1">2. 配置视频数量</h2>${split ? `<div class="batch-combined-target"><label for="config-combinedTarget">本次人设＋故事合计目标</label><input id="config-combinedTarget" type="number" min="0" step="1" inputmode="numeric" value="${state.combinedTarget ?? ""}"><p class="field-hint">可修改目标；两项数量之和须与该目标一致。</p></div>` : ""}
      ${newsSourcesMarkup(state,context,summary)}<div class="batch-quantity-list">${CONFIG_TYPES.filter(([key])=>key !== 'novel' && key !== 'repurpose').map(([key, label]) => `<div class="batch-quantity-row"><div><label for="config-${key}">${label}</label>${key === "persona" || key === "story" ? `<small>${split ? "可修改数量，两项合计须与目标一致" : "可为 0"}</small>` : '<small>以已批准服务价值与合法引导为依据</small>'}</div><input id="config-${key}" aria-describedby="batch-config-errors" type="number" min="0" step="1" inputmode="numeric" value="${state.quantities[key] ?? ""}"></div>`).join("")}</div></section>
      <section class="batch-config-surface"><h2>3. 核对本次安排</h2><dl class="batch-config-totals"><div><dt>计划交付总量</dt><dd>${Number.isSafeInteger(summary.planned) ? summary.planned : "—"}<small>条${split && !summary.valid ? " · 尚待明确分配" : ""}</small></dd></div><div><dt>预计可交付</dt><dd>待核对<small>资格通过后确定</small></dd></div><div><dt>新增语义目标</dt><dd>${summary.valid ? summary.newContentTarget : "—"}<small>改编不重复计入新增</small></dd></div><div><dt>改编呈现目标</dt><dd>${summary.repurposeTarget ?? '—'}<small>以最终合法交付为准</small></dd></div></dl><p class="field-hint">实际交付和新增内容，以后续合法生成、审核及交付结果为准。目标时长仅作建议。</p>
      <div id="batch-config-errors" class="batch-config-errors" ${errorList ? "" : "hidden"}><strong>还需核对以下配置</strong><ul>${errorList}</ul></div><div id="config-feedback" class="batch-config-feedback" role="alert" aria-atomic="true" aria-labelledby="config-feedback-title" tabindex="-1" hidden></div><p id="batch-config-status" role="status">${summary.previewCurrent ? "配置已核对，尚未开始生成。修改配置后需要重新核对。" : "填写完成后核对本次配置。"}</p></section>
      <div class="batch-config-actions"><button class="btn btn-secondary" id="config-save" type="button">保存配置草稿</button><button class="btn btn-primary" id="config-check" type="submit" ${context.blocked ? "disabled" : ""}>核对创作资格</button><button class="btn btn-primary" id="config-confirm" type="button" hidden>确认并开始本批创作</button><a class="btn btn-secondary" href="/customers/${encodeURIComponent(context.customer.business_id)}/content" data-route>查看已有创作</a></div>
    </form></main>`;
}
export function createCreationConfigViews({ app, api, shell, bindCommonActions, skeletonPage, renderLoadError, navigate }) {
  let generation = 0;
  async function renderConfiguration() {
    const invocation = ++generation;
    const route = window.location.href, params = new URLSearchParams(window.location.search), businessId = params.get("business_id");
    const isCurrent = () => invocation === generation && window.location.href === route;
    if (!businessId) {
      app.innerHTML = shell("创作配置", '<main class="page page-form"><h1>先选择一个客户</h1><a class="btn btn-primary" href="/customers" data-route>去客户列表</a></main>'); bindCommonActions(); return;
    }
    skeletonPage("读取创作资料");
    try {
      const data = await api(`/api/create/options?business_id=${encodeURIComponent(businessId)}`);
      if (!isCurrent()) return;
      const context = scopedConfigurationContext(data, businessId, params.get("speaker_id") || "");
      let state = createConfiguration();
      const session = createConfigurationSession(api, businessId);
      const saved = await session.load();
      if (!isCurrent()) return;
      if (saved) {
        state = { ...saved.configuration, previewRevision: null };
        context.speakerId = context.speakers.some(person => person.speaker_id === saved.speaker_id) ? saved.speaker_id : "";
      }
      context.existingBatch = session.originalConfirmation();
      context.confirmationBlocked = session.blockedConfirmation();
      let busy = false, sourceLoad=0, failure = null, message = saved ? "已恢复你的配置草稿，请重新核对当前创作资格。" : "";
      async function loadRepurpose({open=true} = {}) {
        if (busy || !isCurrent()) return;
        if (!context.speakerId) { message='请先选择适用出镜人，再读取历史来源。'; render('config-speaker'); return; }
        const invocation=++sourceLoad, speaker=context.speakerId;
        session.invalidate();message='正在重新读取历史来源，旧预检已失效。';busy=true;context.repurpose={loading:true,open};render();
        try {
          const response=await api('/api/create/news/preview',{method:'POST',body:JSON.stringify({business_id:businessId,speaker_id:speaker})});
          if (!isCurrent() || invocation!==sourceLoad || context.speakerId!==speaker) return;
          const pre=response.preview;
          if (pre.schema_version!=='news-delivery-preview-v1.0' || pre.business_id!==businessId || pre.speaker_id!==speaker
              || pre.target_profile!=='news' || pre.reuse_intent!=='cross_profile_repurpose' || !Array.isArray(pre.eligible_sources)
              || pre.eligible_sources.some(s=>!s || typeof s.source_content_id!=='string')
              || new Set(pre.eligible_sources.map(s=>s.source_content_id)).size!==pre.eligible_sources.length) throw Error('历史来源无法对应当前客户、出镜人或已知来源版本。');
          context.repurpose={loaded:true,sources:pre.eligible_sources,open};
          message='已读取当前可用历史内容，开始前请重新核对创作资格。';
        } catch(error) {
          if (isCurrent() && invocation===sourceLoad) {
            context.repurpose={error:safeCreationMessage(error.message,'历史来源暂时无法读取，请重新核对资格。'),open};
            message='历史来源尚未通过核对，请按提示处理后重新预检。';
          }
        } finally { if (isCurrent() && invocation===sourceLoad) { busy=false;render(open ? 'config-load-repurpose' : null); } }
      }
      function renderFeedback() {
        const feedback = document.getElementById('config-feedback');
        feedback.hidden = !failure;
        feedback.innerHTML = failure ? configurationFailureMarkup(failure) : '';
        document.getElementById('batch-config-status').hidden = !!failure;
        document.getElementById('config-check').textContent = failure?.checking ? '重新核对创作资格' : '核对创作资格';
        document.getElementById('config-adjust-quantities')?.addEventListener('click', () => {
          const heading = document.getElementById('config-quantities-heading');
          heading.focus(); heading.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });
      }
      function render(focusId = null) {
        if (!isCurrent()) return;
        app.innerHTML = shell("创作配置", configurationMarkup(state, context)); bindCommonActions();
        const status = document.getElementById("batch-config-status");
        if (message) status.textContent = message;
        renderFeedback();
        document.getElementById("config-confirm").hidden = !session.isChecked(state, context.speakerId);
        if (session.isChecked(state, context.speakerId)) {
          const delivered = document.querySelectorAll(".batch-config-totals dd")[1];
          delivered.firstChild.textContent = `最多 ${session.checkedPreview().actual_target} 条`; delivered.querySelector("small").textContent = "须合法生成并分别审核、确认发布";
        }
        if (busy) document.querySelectorAll(".batch-config-page button,.batch-config-page input,.batch-config-page select").forEach(input => { input.disabled = true; });
        document.getElementById("batch-config-errors").addEventListener("click", event => {
          const link = event.target.closest('a[href^="#config-"]');
          if (!link || !isCurrent()) return;
          event.preventDefault();
          const field = document.getElementById(link.hash.slice(1));
          field?.focus(); field?.scrollIntoView({ block: "center", behavior: "smooth" });
        });
        function edited() { session.invalidate(); failure = null; renderFeedback(); message = "配置已修改，请重新核对创作资格。"; }
        document.getElementById('config-new-batch')?.addEventListener('click', () => {
          state = { ...state, quantities: { ...state.quantities }, revision: state.revision + 1, previewRevision: null,
            cyclesConfirmed: state.mode === 'stage' && state.stage === 'steady' ? false : state.cyclesConfirmed };
          context.existingBatch = null; context.confirmationBlocked = null; session.invalidate();
          message = '已转为新一批的配置。请重新核对当前合法来源；不会重复使用原批已占用的来源。'; render();
        });
        document.querySelectorAll("[data-config-mode]").forEach(button => button.addEventListener("click", () => {
          state = changeConfiguration(state, "mode", button.dataset.configMode); edited(); render();
        }));
        document.querySelectorAll("[data-config-stage]").forEach(input => input.addEventListener("change", () => {
          if (!input.checked) return;
          state = changeConfiguration(state, "stage", input.value); edited(); render(input.id);
        }));
        function updateQuantity(field, value) {
            if (busy || !isCurrent()) return;
            state = changeConfiguration(state, field, value);
            edited(); document.getElementById("config-confirm").hidden = true;
            if (field === "cycles") {
              for (const [key] of CONFIG_TYPES) {
                const quantity = document.getElementById(`config-${key}`);
                if (quantity) quantity.value = state.quantities[key] ?? "";
              }
              document.getElementById("config-cyclesConfirmed").checked = false;
            }
            const summary = configurationSummary(state);
            const totals = document.querySelectorAll(".batch-config-totals dd");
            totals[0].firstChild.textContent = Number.isSafeInteger(summary.planned) ? summary.planned : "—";
            totals[1].firstChild.textContent = "待核对";
            totals[1].querySelector("small").textContent = "资格通过后确定";
            totals[2].firstChild.textContent = summary.valid ? summary.newContentTarget : "—";
            totals[3].firstChild.textContent = summary.repurposeTarget ?? '—';
            document.getElementById('config-news-total').textContent = summary.newsTotal ?? '—';
            for (const [key] of NEWS_SOURCES) {
              document.getElementById(`config-news-${key}`).textContent = state.quantities[key] ?? '—';
              document.querySelectorAll(`[data-quantity-target="${key}"]`).forEach(button=>{
                button.disabled = button.dataset.quantityStep === '-1' ? state.quantities[key] === 0 : state.quantities[key] >= 40;
              });
            }
            if (field === 'repurpose') {
              if (state.quantities.repurpose === 0) context.repurpose = null;
              if (context.repurpose && (state.repurposeSourceIds || []).length > state.quantities.repurpose) context.repurpose.open = true;
              document.getElementById('config-repurpose-selection').innerHTML = repurposeSelectionMarkup(state,context);
              document.getElementById('config-news-legacy').innerHTML = newsLegacyMarkup(state);
              bindRepurpose();
            }
            const errors = document.getElementById("batch-config-errors");
            errors.hidden = !summary.errors.length;
            errors.querySelector("ul").innerHTML = summary.errors.map(error => `<li><a href="#config-${error.field}">${escapeHtml(error.message)}</a></li>`).join("");
            if (field === "cycles") {
              const checkbox = document.getElementById("config-cyclesConfirmed");
              checkbox.nextSibling.textContent = `我确认仅安排本次 ${state.cycles ?? "—"} 个周期，不会自动持续创作。`;
            }
            const status = document.getElementById("batch-config-status");
            status.textContent = field === 'repurpose' && state.quantities.repurpose === 0 ? '改编数量已设为 0，本次历史来源选择已清除，请重新核对配置。' : "配置已修改，请重新核对。";
            status.tabIndex = -1;
        }
        for (const field of ["cycles", "cyclesConfirmed", "combinedTarget", ...CONFIG_TYPES.map(([key]) => key)]) {
          const input = document.getElementById(`config-${field}`); if (!input) continue;
          if (input.type !== "number") input.addEventListener("change", () => {
            state = changeConfiguration(state, field, input.type === "checkbox" ? input.checked : input.value); edited(); render(`config-${field}`);
          });
          // Invalidate the in-memory check immediately, before blur/change.
          if (input.type === "number") input.addEventListener("input", () => updateQuantity(field,input.value));
        }
        document.querySelectorAll('[data-quantity-step]').forEach(button=>button.addEventListener('click',()=>{
          if (busy || !isCurrent()) return;
          const key=button.dataset.quantityTarget, old=state.quantities[key];
          const value=Math.max(0,(Number.isSafeInteger(old) && old >= 0 ? old : 0)+Number(button.dataset.quantityStep));
          updateQuantity(key,value);document.getElementById(`config-${key}`).value=state.quantities[key] ?? '';
        }));
        function bindRepurpose() {
          document.getElementById('config-load-repurpose')?.addEventListener('click',()=>loadRepurpose());
          document.getElementById('config-reconfirm-news')?.addEventListener('click',()=>{
            updateQuantity('repurpose',state.quantities.repurpose);document.getElementById('config-repurpose').focus();
          });
          document.getElementById('config-finish-repurpose')?.addEventListener('click',()=>{
            if (busy || !isCurrent() || !context.repurpose?.loaded || (state.repurposeSourceIds || []).length!==state.quantities.repurpose
                || state.repurposeSourceIds.some(id=>!context.repurpose.sources.some(s=>s.source_content_id===id))) return;
            context.repurpose.open=false;render('config-load-repurpose');
          });
          document.querySelectorAll('[data-repurpose-source]').forEach(input=>input.addEventListener('change',()=>{
            if (busy || !isCurrent()) return;
            const selected=new Set(state.repurposeSourceIds || []);
            if (input.checked) selected.add(input.value);else selected.delete(input.value);
            state=changeConfiguration(state,'repurposeSourceIds',[...selected]);edited();render(input.id);
          }));
        }
        bindRepurpose();
        document.getElementById("config-speaker").addEventListener("change", event => {
          context.speakerId = event.target.value;sourceLoad+=1;context.repurpose=null;
          state = { ...state, repurposeSourceIds:[], revision: state.revision + 1, previewRevision: null }; edited(); render("config-speaker");
          if (state.quantities.repurpose > 0) loadRepurpose();
        });
        async function act(action, { checking = false } = {}) {
          if (busy || !isCurrent()) return;
          busy = true; failure = null; message = "正在核对并保存，请稍候。"; render();
          try { await action(); }
          catch (error) {
            if (!isCurrent()) return;
            message = safeCreationMessage(error.message, "本次操作尚未确认，请重新核对。已有草稿会保留。");
            failure = { checking, message, nextAction: safeCreationMessage(error.detail?.next_action,
              checking ? '请核对对应数量与创作来源，调整后重新核对资格。' : '请保留当前配置，按提示核对后重试。') };
          }
          finally { busy = false; render(failure ? "config-feedback" : "batch-config-status"); }
        }
        document.getElementById("config-save").addEventListener("click", () => act(async () => {
          await session.save(state, context.speakerId); message = "配置草稿已保存，尚未创建内容或批准生成。";
        }));
        document.getElementById("config-confirm").addEventListener("click", () => act(async () => {
          const result = await session.confirm(state, context.speakerId);
          if (!isCurrent()) return;
          if (result?.batch_id) {
            session.invalidate(); message = "本批创作已确认，可查看逐项进度、人工审核和交付。";
            context.batchId = result.batch_id;
            navigate?.(`/create/batch?batch_id=${encodeURIComponent(result.batch_id)}`);
          }
        }));
        if (context.batchId) {
          const link = document.createElement("a"); link.className = "btn btn-primary";
          link.href = `/create/batch?batch_id=${encodeURIComponent(context.batchId)}`;
          link.dataset.route = ""; link.textContent = "查看本批创作进度与审核";
          document.querySelector(".batch-config-actions").append(link); bindCommonActions();
        }
        document.getElementById("batch-config-form").addEventListener("submit", event => {
          event.preventDefault();
          const existing = session.confirmedBatch(state, context.speakerId);
          if (existing) { navigate?.(`/create/batch?batch_id=${encodeURIComponent(existing.batch_id)}`); return; }
          const summary = configurationSummary(state);
          if (!context.speakerId) { document.getElementById("batch-config-status").textContent = "请先选择适用出镜人。"; document.getElementById("config-speaker").focus(); return; }
          if (summary.valid && !context.blocked) {
            act(async () => {
              const checked = await session.check(state, context.speakerId);
              message = `当前资料允许本次安排 ${checked.actual_target} 条，其中新增内容目标 ${checked.new_content_target} 条。请明确确认；生成后仍需人工审核与发布确认。`;
            }, { checking: true });
          } else render(summary.errors[0] ? `config-${summary.errors[0].field}` : "batch-config-status");
        });
        if (focusId) {
          const target = document.getElementById(focusId);
          if (target?.id === "batch-config-status") target.tabIndex = -1;
          target?.focus();
          if (focusId === 'config-feedback') target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      }
      render();
      if (state.quantities.repurpose > 0) await loadRepurpose({open:false});
    } catch (error) { if (isCurrent()) renderLoadError("创作配置暂时无法读取", error); }
  }
  return { renderConfiguration };
}
