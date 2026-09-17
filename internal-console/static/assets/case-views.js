import { caseCard, caseReviewContent, escapeHtml, progressPanel } from "./case-components.js";
import { startTaskPolling } from "./task-progress.js";

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

  function bindTaskProgress(task) {
    const host = document.querySelector("[data-live-progress]");
    if (!host) return;
    host.innerHTML = progressPanel(task);
    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,
      onUpdate: (next) => { if (document.querySelector("[data-live-progress]")) host.innerHTML = progressPanel(next); },
      onDone: (next) => {
        if (next.status === "awaiting_review") {
          host.insertAdjacentHTML("beforeend", `<a class="btn btn-primary btn-wide progress-review-link" href="/cases/${encodeURIComponent(next.subject_ref)}" data-route>去审核案例</a>`);
          bindCommonActions();
        }
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
          <div class="sticky-action"><button class="btn btn-primary btn-wide" type="submit">开始分析</button></div></form></section>
        <aside class="card notice-card"><h2>案例使用边界</h2><p>案例只用于内部结构研究。分析完成后仍需人工审核；批准入库也不会赋予原视频素材生产使用权。</p></aside></div></main>`;
    app.innerHTML = shell("添加案例", body);
    bindCommonActions();
    const input = document.querySelector("#case-url");
    const detection = document.querySelector("#source-detection");
    const updateDetection = () => {
      const value = input.value.trim();
      detection.textContent = !value ? "输入链接后自动识别来源" : /douyin\.com/i.test(value) ? "已识别：抖音视频" : "当前未识别到支持的视频来源";
      detection.className = value && /douyin\.com/i.test(value) ? "source-detection" : "source-detection muted";
    };
    input.addEventListener("input", updateDetection);
    document.querySelector("[data-paste]").addEventListener("click", async () => {
      if (!navigator.clipboard?.readText) return showToast("当前浏览器不支持读取剪贴板，请长按输入框粘贴。");
      try { input.value = await navigator.clipboard.readText(); updateDetection(); input.focus(); }
      catch { showToast("无法读取剪贴板，请手动粘贴链接。"); }
    });
    document.querySelector("#case-url-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.currentTarget.querySelector("button[type=submit]");
      const errorBox = document.querySelector("#case-form-error");
      const resultBox = document.querySelector("#case-result");
      errorBox.classList.remove("visible"); resultBox.innerHTML = ""; button.disabled = true; button.textContent = "正在提交…";
      try {
        const result = await api("/api/cases/analyze", { method: "POST", body: JSON.stringify({ url: input.value }) });
        if (result.duplicate && result.existing_case) {
          resultBox.innerHTML = `<div class="result-banner"><h3>这个案例已经分析过了</h3><p>${escapeHtml(result.existing_case.title)}</p><a class="btn btn-secondary" href="/cases/${encodeURIComponent(result.existing_case.case_id)}" data-route>查看已有案例</a></div>`;
          bindCommonActions();
        } else if (result.duplicate && result.existing_task) {
          resultBox.innerHTML = `<div data-live-progress></div>`; bindTaskProgress(result.existing_task);
        } else {
          resultBox.innerHTML = `<div data-live-progress></div>`; bindTaskProgress(result.task);
        }
      } catch (error) {
        const next = error.detail?.next_action ? `<div class="next-action"><strong>下一步</strong><span>${escapeHtml(error.detail.next_action)}</span></div>` : "";
        resultBox.innerHTML = `<div class="result-banner error"><h3>${escapeHtml(error.message)}</h3>${next}</div>`;
      } finally { button.disabled = false; button.textContent = "开始分析"; }
    });
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
          if (!window.confirm("确认已经对照原视频完成审核，并批准这个案例进入内部案例库？\n\n这不会赋予原视频素材客户生产使用权。")) return;
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
