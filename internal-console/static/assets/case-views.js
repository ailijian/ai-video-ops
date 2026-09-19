import { caseCard, caseReviewContent, escapeHtml, progressPanel } from "./case-components.js?v=production-acceptance-1";
import { projectCaseSubmitState, resetCaseSubmitState } from "./case-submit-state.mjs?v=production-acceptance-1";
import { startTaskPolling } from "./task-progress.js";

function duplicateResultHtml(result) {
  const state = result.state || "";

  if (state === "approved" && result.existing_case) {
    return `<div class="result-banner">
      <h3>这个视频已经在案例库里</h3>
      <p>${escapeHtml(result.existing_case.title || "")}</p>
    </div>`;
  }

  if (state === "awaiting_review") {
    return `<div class="result-banner">
      <h3>这个视频已经分析完成</h3>
      <p>现在正在等待人工审核，无需重复分析。</p>
    </div>`;
  }

  if (state === "running" && result.existing_task) {
    return `<div class="result-banner">
      <h3>这个视频正在分析</h3>
      <p>无需重复提交，可以继续查看当前任务。</p>
    </div>`;
  }

  if (state === "rejected") {
    return `<div class="result-banner">
      <h3>这个案例之前没有收录</h3>
      <p>${escapeHtml(result.rejection_reason || "如果你现在认为值得重新评估，可以显式重新分析。")}</p>
    </div>`;
  }

  if (state === "failed") {
    return `<div class="result-banner">
      <h3>这个视频之前分析失败</h3>
      <p>可以重新建立一个分析任务；旧记录不会被覆盖。</p>
    </div>`;
  }

  return `<div class="result-banner">
    <h3>${escapeHtml(
      result.message || "这个视频已经提交过"
    )}</h3>
  </div>`;
}

export function createCaseViews({ app, api, navigate, shell, bindCommonActions, pageHeading, skeletonPage, statusPill, showToast, renderLoadError }) {
  let stopPolling = null;
  const stopTaskPolling = () => { stopPolling?.(); stopPolling = null; };

  async function renderCases() {
    stopTaskPolling();
    skeletonPage("案例库");
    try {
      const data = await api("/api/cases");
      const cases = data.cases;
      const content = cases.length ? `<div class="filter-row" role="group" aria-label="案例状态筛选">
          <button class="filter-chip active" data-filter="all" type="button">全部 ${cases.length}</button>
          <button class="filter-chip" data-filter="awaiting_review" type="button">待审核 ${cases.filter((item) => item.status === "awaiting_review").length}</button>
          <button class="filter-chip" data-filter="approved" type="button">已入库 ${cases.filter((item) => item.status === "approved").length}</button>
        </div><div class="case-list">${cases.map((item) => caseCard(item, statusPill)).join("")}</div>` :
        `<section class="card empty-state"><h2>案例库还是空的</h2><p>先添加一个真实视频，完成分析后再人工审核。</p><a class="btn btn-primary" href="/cases/new" data-route>添加案例</a></section>`;
      app.innerHTML = shell("案例库", `<main class="page">${pageHeading("案例", "案例库", "只用于结构研究，不代表原视频素材可以用于客户生产。", '<div class="section"><a class="btn btn-primary" href="/cases/new" data-route>+ 添加案例</a></div>')}${content}</main>`);
      bindCommonActions();
      document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
        document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
        document.querySelectorAll("[data-case-status]").forEach((card) => {
          card.hidden = button.dataset.filter !== "all" && card.dataset.caseStatus !== button.dataset.filter;
        });
      }));
    } catch (error) { renderLoadError("案例库暂时无法读取", error); }
  }

  function bindTaskProgress(task, onLifecycleChange = () => {}) {
    const host = document.querySelector("[data-live-progress]");
    if (!host) return;
    host.innerHTML = progressPanel(task);
    onLifecycleChange(task.status, task);
    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,
      onUpdate: (next) => {
        if (document.querySelector("[data-live-progress]")) host.innerHTML = progressPanel(next);
        onLifecycleChange(next.status, next);
      },
      onDone: (next) => {
        onLifecycleChange(next.status, next);
      },
    });
  }

  function renderCaseNew() {
    stopTaskPolling();
    const body = `<main class="page">${pageHeading("添加案例", "添加一个视频案例", "粘贴完整的抖音视频链接，提交后可以离开页面。")}
      <div class="url-layout"><section class="card url-panel"><h2>视频链接</h2><p>系统会先检查是否已经分析过，再启动真实分析任务。</p>
        <form id="case-url-form" novalidate><div class="field"><label for="case-url">粘贴视频链接</label>
          <div class="input-combo"><input id="case-url" type="url" inputmode="url" autocomplete="off" placeholder="https://www.douyin.com/video/..." required><button class="paste-button" type="button" data-paste>粘贴</button></div>
          <div id="source-detection" class="source-detection muted">输入链接后自动识别来源</div></div>
          <div id="case-form-error" class="form-error" role="alert"></div><div id="case-result"></div>
          <div class="sticky-action case-submit-actions" data-case-submit-actions></div></form></section>
        <aside class="card notice-card"><h2>案例使用边界</h2><p>案例只用于内部结构研究。分析完成后仍需人工审核；批准入库也不会赋予原视频素材生产使用权。</p></aside></div></main>`;
    app.innerHTML = shell("添加案例", body);
    bindCommonActions();
    const input = document.querySelector("#case-url");
    const detection = document.querySelector("#source-detection");
    const form = document.querySelector("#case-url-form");
    const pasteButton = document.querySelector("[data-paste]");
    const resultBox = document.querySelector("#case-result");
    const actionsHost = document.querySelector("[data-case-submit-actions]");
    let activeState = "idle";
    let activeCaseId = null;
    let reanalysisState = null;

    const actionMarkup = (projection) => {
      const actions = [];
      if (projection.submitVisible) {
        actions.push(`<button class="btn btn-primary btn-wide" type="submit" ${projection.submitDisabled ? "disabled" : ""}>${projection.submitLabel}</button>`);
      }
      if (projection.primaryAction?.kind === "review") {
        actions.push(`<a class="btn btn-primary btn-wide" href="/cases/${encodeURIComponent(activeCaseId || "")}" data-route>去审核案例</a>`);
      } else if (projection.primaryAction?.kind === "existing") {
        actions.push(`<a class="btn btn-primary btn-wide" href="/cases/${encodeURIComponent(activeCaseId || "")}" data-route>查看已有案例</a>`);
      } else if (projection.primaryAction?.kind === "reanalyze") {
        actions.push(`<button class="btn btn-primary btn-wide" type="button" data-explicit-reanalysis>重新分析</button>`);
      }
      if (projection.showNewCaseReset) {
        actions.push(`<button class="btn btn-quiet btn-wide" type="button" data-new-case-reset>添加另一个案例</button>`);
      }
      return actions.join("");
    };

    const setSubmitState = (status, { caseId = activeCaseId, reanalysis = reanalysisState } = {}) => {
      activeState = status;
      activeCaseId = caseId;
      reanalysisState = reanalysis;
      const projection = projectCaseSubmitState(status);
      input.disabled = projection.inputDisabled;
      pasteButton.disabled = projection.pasteDisabled;
      actionsHost.innerHTML = actionMarkup(projection);
      bindCommonActions();
    };

    const resetForAnotherCase = () => {
      stopTaskPolling();
      activeCaseId = null;
      reanalysisState = null;
      input.value = "";
      resultBox.innerHTML = "";
      document.querySelector("#case-form-error").classList.remove("visible");
      const projection = resetCaseSubmitState();
      setSubmitState(projection.status);
      updateDetection();
      input.focus();
    };
    const updateDetection = () => {
      const value = input.value.trim();
      detection.textContent = !value ? "输入链接后自动识别来源" : /douyin\.com/i.test(value) ? "已识别：抖音视频" : "当前未识别到支持的视频来源";
      detection.className = value && /douyin\.com/i.test(value) ? "source-detection" : "source-detection muted";
    };
    input.addEventListener("input", updateDetection);
    pasteButton.addEventListener("click", async () => {
      if (!navigator.clipboard?.readText) return showToast("当前浏览器不支持读取剪贴板，请长按输入框粘贴。");
      try { input.value = await navigator.clipboard.readText(); updateDetection(); input.focus(); }
      catch { showToast("无法读取剪贴板，请手动粘贴链接。"); }
    });
    actionsHost.addEventListener("click", async (event) => {
      const resetButton = event.target.closest("[data-new-case-reset]");
      if (resetButton) return resetForAnotherCase();
      const reanalyzeButton = event.target.closest("[data-explicit-reanalysis]");
      if (!reanalyzeButton || !projectCaseSubmitState(activeState).allowReanalysis) return;

      let reason = "分析失败后由运营人员显式重新分析。";
      if (reanalysisState === "rejected") {
        reason = window.prompt("请填写为什么需要重新分析这个案例", "")?.trim() || "";
        if (!reason) return;
      }
      setSubmitState("submitting");
      try {
        const restarted = await api("/api/cases/analyze", {
          method: "POST",
          body: JSON.stringify({ url: input.value, reanalyze: true, reason }),
        });
        resultBox.innerHTML = `<div data-live-progress></div>`;
        bindTaskProgress(restarted.task, (status, task) => setSubmitState(status, {
          caseId: task.subject_ref || activeCaseId,
          reanalysis: status,
        }));
      } catch (error) {
        showToast(error.detail?.next_action || error.message);
        setSubmitState(reanalysisState || "failed");
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorBox = document.querySelector("#case-form-error");
      if (activeState !== "idle") return;
      errorBox.classList.remove("visible"); resultBox.innerHTML = "";
      setSubmitState("submitting");
      try {
        const result = await api("/api/cases/analyze", { method: "POST", body: JSON.stringify({ url: input.value }) });
        if (result.duplicate) {
          resultBox.innerHTML = duplicateResultHtml(result);
          setSubmitState(result.state, { caseId: result.case_id, reanalysis: result.state });
        } else {
          resultBox.innerHTML = `<div data-live-progress></div>`;
          bindTaskProgress(result.task, (status, task) => setSubmitState(status, {
            caseId: task.subject_ref || result.case_id,
            reanalysis: status,
          }));
        }
      } catch (error) {
        const next = error.detail?.next_action ? `<div class="next-action"><strong>下一步</strong><span>${escapeHtml(error.detail.next_action)}</span></div>` : "";
        resultBox.innerHTML = `<div class="result-banner error"><h3>${escapeHtml(error.message)}</h3>${next}</div>`;
        setSubmitState("idle");
      }
    });
    setSubmitState("idle");
  }

  async function renderCaseDetail(caseId) {
    stopTaskPolling(); skeletonPage("案例审核");
    try {
      const detail = await api(`/api/cases/${encodeURIComponent(caseId)}`);
      app.innerHTML = shell("案例审核", caseReviewContent(detail, statusPill));
      bindCommonActions();
      document.querySelectorAll("[data-review-action]").forEach((button) => button.addEventListener("click", async () => {
        const action = button.dataset.reviewAction;
        let reason = "";
        if (action === "approve") {
          const recovery = button.textContent.includes("恢复");
          const prompt = recovery
            ? "确认恢复同一 Attempt 尚未完成的审批发布？\n\n系统不会执行第二次人工审批，也不会改变原视频素材使用权。"
            : "确认已经对照原视频完成审核，并批准这个案例进入内部案例库？\n\n这不会赋予原视频素材客户生产使用权。";
          if (!window.confirm(prompt)) return;
        } else {
          reason = window.prompt(action === "reanalyze" ? "请填写需要重新分析的原因" : "请填写不收录的原因", "")?.trim() || "";
          if (!reason) return;
        }
        document.querySelectorAll("[data-review-action]").forEach((item) => { item.disabled = true; });
        try {
          const result = await api(`/api/cases/${encodeURIComponent(caseId)}/review`, { method: "POST", body: JSON.stringify({ decision: action, reason }) });
          if (action === "approve") { showToast("案例已进入案例库"); return renderCaseDetail(caseId); }
          if (action === "reanalyze") { showToast("已退回重新分析"); return navigate(`/tasks/${result.task.task_id}`); }
          showToast("已记录为不收录"); navigate("/cases");
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          document.querySelectorAll("[data-review-action]").forEach((item) => { item.disabled = false; });
        }
      }));
    } catch (error) { renderLoadError("案例暂时无法读取", error); }
  }

  async function renderTaskDetail(taskId) {
    stopTaskPolling(); skeletonPage("任务进度");
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
      app.innerHTML = shell("任务进度", `<main class="page task-detail-page">${pageHeading("任务进度", "案例分析", "进度来自实际分析步骤，离开页面后仍会继续。")}
        <div data-live-progress>${progressPanel(payload.task)}</div></main>`);
      bindCommonActions(); bindTaskProgress(payload.task);
    } catch (error) { renderLoadError("任务暂时无法读取", error); }
  }

  return { renderCases, renderCaseNew, renderCaseDetail, renderTaskDetail, stopTaskPolling };
}
