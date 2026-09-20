import { caseCard, caseReviewContent, escapeHtml, progressPanel } from "./case-components.js?v=operator-attribution-v1";
import { projectCaseSubmitState, resetCaseSubmitState } from "./case-submit-state.mjs?v=productized-stage1-5";
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

export function createCaseViews({ app, api, navigate, shell, bindCommonActions, pageHeading, skeletonPage, statusPill, showToast, openModal, renderLoadError }) {
  let stopPolling = null;
  const stopTaskPolling = () => { stopPolling?.(); stopPolling = null; };

  async function renderCases() {
    stopTaskPolling();
    skeletonPage("案例");
    try {
      const data = await api("/api/cases");
      const cases = data.cases;
      const content = cases.length ? `<div class="filter-row" role="group" aria-label="案例状态筛选">
          <button class="filter-chip active" data-filter="all" type="button">全部 ${cases.length}</button>
          <button class="filter-chip" data-filter="awaiting_review" type="button">待审核 ${cases.filter((item) => item.status === "awaiting_review").length}</button>
          <button class="filter-chip" data-filter="approved" type="button">已入库 ${cases.filter((item) => item.status === "approved").length}</button>
        </div><div class="case-list">${cases.map((item) => caseCard(item, statusPill)).join("")}</div>` :
        `<section class="state-panel empty-state"><h2>还没有案例</h2><p>添加一个抖音视频，分析完成后即可审核。</p></section>`;
      app.innerHTML = shell("案例", `<main class="page page-standard case-library-page">${pageHeading("", "案例", "浏览和审核团队已经分析的视频案例。", '<a class="btn btn-primary" href="/cases/new" data-route>+ 添加案例</a>')}${content}</main>`);
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
    host.innerHTML = progressPanel(task, { embedded: host.dataset.embedded === "true" });
    onLifecycleChange(task.status, task);
    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,
      onUpdate: (next) => {
        if (document.querySelector("[data-live-progress]")) host.innerHTML = progressPanel(next, { embedded: host.dataset.embedded === "true" });
        onLifecycleChange(next.status, next);
      },
      onDone: (next) => {
        onLifecycleChange(next.status, next);
      },
    });
  }

  function renderCaseNew() {
    stopTaskPolling();
    const body = `<main class="page page-form add-case-page">${pageHeading("", "添加案例", "粘贴抖音视频链接，分析会在后台继续。")}
      <section class="work-surface add-case-surface">
        <form id="case-url-form" novalidate><div data-case-input-panel><div class="field"><label for="case-url">粘贴抖音视频链接</label>
          <div class="input-combo"><input id="case-url" type="url" inputmode="url" autocomplete="off" placeholder="https://www.douyin.com/video/..." required><button class="paste-button" type="button" data-paste>粘贴</button></div>
          <div id="source-detection" class="source-detection muted">输入链接后自动识别来源</div></div></div>
          <fieldset class="case-profile-choice" data-case-profile-panel><legend>这个视频更接近哪种结构？</legend>
            <label><input type="radio" name="operator-profile-hint" value="mix"><span><strong>混剪型</strong><small>以口播 / 叙事为主，画面配合表达。</small></span></label>
            <label><input type="radio" name="operator-profile-hint" value="news"><span><strong>新闻体</strong><small>短促的信息卡点或新闻式表达。</small></span></label>
            <label><input type="radio" name="operator-profile-hint" value="hybrid"><span><strong>混合型</strong><small>两种结构都比较明显。</small></span></label>
            <label><input type="radio" name="operator-profile-hint" value="uncertain"><span><strong>不确定</strong><small>先交给系统分析。</small></span></label>
          </fieldset>
          <div id="case-form-error" class="form-error" role="alert"></div><div id="case-result"></div>
          <div class="case-submit-actions" data-case-submit-actions></div>
          <p class="governance-copy">批准后的案例只用于内部参考，不会获得原视频素材使用权。</p>
        </form>
      </section></main>`;
    app.innerHTML = shell("添加案例", body);
    bindCommonActions();
    const input = document.querySelector("#case-url");
    const detection = document.querySelector("#source-detection");
    const form = document.querySelector("#case-url-form");
    const pasteButton = document.querySelector("[data-paste]");
    const resultBox = document.querySelector("#case-result");
    const actionsHost = document.querySelector("[data-case-submit-actions]");
    const inputPanel = document.querySelector("[data-case-input-panel]");
    const profilePanel = document.querySelector("[data-case-profile-panel]");
    const selectedHint = () => form.querySelector('input[name="operator-profile-hint"]:checked')?.value || null;
    let activeState = "idle";
    let activeCaseId = null;
    let activeTaskId = null;
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
      } else if (projection.primaryAction?.kind === "progress" && activeTaskId) {
        actions.push(`<a class="btn btn-primary btn-wide" href="/tasks/${encodeURIComponent(activeTaskId)}" data-route>查看当前进度</a>`);
      }
      if (projection.showNewCaseReset) {
        actions.push(`<button class="btn btn-quiet btn-wide" type="button" data-new-case-reset>添加另一个案例</button>`);
      }
      return actions.join("");
    };

    const setSubmitState = (status, { caseId = activeCaseId, taskId = activeTaskId, reanalysis = reanalysisState } = {}) => {
      activeState = status;
      activeCaseId = caseId;
      activeTaskId = taskId;
      reanalysisState = reanalysis;
      const projection = projectCaseSubmitState(status);
      input.disabled = projection.inputDisabled;
      pasteButton.disabled = projection.pasteDisabled;
      inputPanel.hidden = status !== "idle";
      profilePanel.hidden = !["idle", "failed", "rejected"].includes(status);
      actionsHost.innerHTML = actionMarkup(projection);
      bindCommonActions();
    };

    const resetForAnotherCase = () => {
      stopTaskPolling();
      activeCaseId = null;
      activeTaskId = null;
      reanalysisState = null;
      input.value = "";
      form.querySelectorAll('input[name="operator-profile-hint"]').forEach((radio) => { radio.checked = false; });
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
        const decision = await openModal({
          title: "重新分析这个案例？",
          description: "请说明重新分析的原因，新的分析会单独记录。",
          confirmLabel: "重新分析",
          reasonLabel: "重新分析原因",
          reasonRequired: true,
        });
        if (!decision.confirmed) return;
        reason = decision.reason;
      }
      setSubmitState("submitting");
      try {
        const restarted = await api("/api/cases/analyze", {
          method: "POST",
          body: JSON.stringify({ url: input.value, reanalyze: true, reason, operator_profile_hint: selectedHint() }),
        });
        resultBox.innerHTML = `<div data-live-progress data-embedded="true"></div>`;
        bindTaskProgress(restarted.task, (status, task) => setSubmitState(status, {
          caseId: task.subject_ref || activeCaseId,
          taskId: task.task_id,
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
      if (!selectedHint()) {
        errorBox.textContent = "请选择视频结构类型；不确定也可以选择。";
        errorBox.classList.add("visible");
        profilePanel.querySelector("input")?.focus();
        return;
      }
      setSubmitState("submitting");
      try {
        const result = await api("/api/cases/analyze", { method: "POST", body: JSON.stringify({ url: input.value, operator_profile_hint: selectedHint() }) });
        if (result.duplicate) {
          resultBox.innerHTML = duplicateResultHtml(result);
          setSubmitState(result.state, {
            caseId: result.case_id,
            taskId: result.existing_task?.task_id || null,
            reanalysis: result.state,
          });
        } else {
          resultBox.innerHTML = `<div data-live-progress data-embedded="true"></div>`;
          bindTaskProgress(result.task, (status, task) => setSubmitState(status, {
            caseId: task.subject_ref || result.case_id,
            taskId: task.task_id,
            reanalysis: status,
          }));
        }
      } catch (error) {
        const next = error.detail?.next_action || "请检查视频链接后重新提交。";
        resultBox.innerHTML = `<div class="result-banner error"><h3>暂时无法分析这个视频</h3><p>${escapeHtml(next)}</p></div>`;
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
        let profileHint = null;
        if (action === "approve") {
          const recovery = button.textContent.includes("恢复");
          const decision = await openModal({
            title: recovery ? "完成上次批准？" : "批准这个案例？",
            description: recovery
              ? "系统只会完成上次未保存完的批准，不会重复审核。批准不会改变原视频素材使用权。"
              : "请确认你已经对照原视频检查内容与结构。批准后会进入案例库，但不会获得原视频素材使用权。",
            confirmLabel: recovery ? "完成批准" : "批准入库",
          });
          if (!decision.confirmed) return;
        } else {
          const reanalyze = action === "reanalyze";
          const decision = await openModal({
            title: reanalyze ? "重新分析这个案例？" : "不收录这个案例？",
            description: reanalyze ? "请说明需要重新分析的原因。" : "请说明不收录的原因，方便团队后续判断。",
            confirmLabel: reanalyze ? "重新分析" : "确认不收录",
            reasonLabel: reanalyze ? "重新分析原因" : "不收录原因",
            reasonRequired: true,
            danger: !reanalyze,
            profileHintRequired: reanalyze && !detail.operator_profile_hint,
          });
          if (!decision.confirmed) return;
          reason = decision.reason;
          profileHint = decision.profileHint || null;
        }
        document.querySelectorAll("[data-review-action]").forEach((item) => { item.disabled = true; });
        try {
          const result = await api(`/api/cases/${encodeURIComponent(caseId)}/review`, { method: "POST", body: JSON.stringify({ decision: action, reason, operator_profile_hint: profileHint }) });
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
