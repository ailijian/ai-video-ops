import { boundaryReviewPanel, caseCard, caseReviewContent, escapeHtml, progressPanel } from "./case-components.js?v=case-final-review-1";
import { bindCaseMediaPreview } from "./case-media-preview.mjs?v=case-media-fit-1";
import { caseTaskResumeDestination, projectCaseSubmitState, projectFailedCaseTask, resetCaseSubmitState } from "./case-submit-state.mjs?v=mobile-reliability-2";
import { startTaskPolling } from "./task-progress.js?v=mobile-reliability-1";
import { detectCaseSourceInput, extractCaseSourceUrls } from "./case-source-detection.mjs?v=case-batch-1";
import { uploadCaseFile, validateCaseFile } from "./case-file-upload.mjs?v=source-upload-ui-2";
import { submitCaseBatch } from "./case-batch-submit.mjs?v=case-batch-1";
import { CASE_INDUSTRIES, CUSTOM_INDUSTRY, industryOptions, industryValue, setIndustryValue, syncCustomIndustry } from "./case-industry.mjs?v=industry-2";

const hasSpecificIndustry = (value) => Boolean(value?.trim() && !["待分类", "unknown"].includes(value.trim().toLowerCase()));

export function caseAcquisitionWarning(acquisition, { hasFile = false, unavailable = false } = {}) {
  if (hasFile || (acquisition?.mode === "qiyun" && acquisition.configured)) return "";
  if (acquisition?.mode === "qiyun") return "奇云付费解析尚未连接。请上传视频，或联系管理员检查配置。";
  if (acquisition?.mode === "legacy_downloader") return "当前使用原有下载方式，未启用奇云付费解析。获取失败时可上传本地视频。";
  if (acquisition?.mode === "upload_only") return "当前无法自动获取视频，请上传本地视频。";
  return unavailable ? "暂时无法确认视频获取方式，请刷新页面后再提交。" : "";
}

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
  let stopMediaPreview = null;
  let stopUpload = null;
  const stopTaskPolling = () => { stopPolling?.(); stopPolling = null; };
  const dispose = () => { stopTaskPolling(); stopMediaPreview?.(); stopMediaPreview = null; stopUpload?.(); stopUpload = null; };

  async function renderCases() {
    dispose();
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

  function bindTaskProgress(task, onLifecycleChange = () => {}, boundaryReview = null) {
    const host = document.querySelector("[data-live-progress]");
    if (!host) return;
    host.innerHTML = progressPanel(task, { embedded: host.dataset.embedded === "true", boundaryReview });
    onLifecycleChange(task.status, task);
    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,
      onUpdate: (next) => {
        if (document.querySelector("[data-live-progress]")) host.innerHTML = progressPanel(next, { embedded: host.dataset.embedded === "true", boundaryReview });
        onLifecycleChange(next.status, next);
      },
      onDone: (next) => {
        onLifecycleChange(next.status, next);
      },
    });
  }

  function renderCaseNew() {
    dispose();
    const body = `<main class="page page-form add-case-page">${pageHeading("", "添加案例", "粘贴一个或多个抖音视频链接，系统会逐条建立分析任务。")}
      <section class="work-surface add-case-surface">
        <form id="case-url-form" novalidate><div data-case-input-panel><div class="field"><label for="case-url">粘贴抖音分享内容或视频链接</label>
          <div class="input-combo"><textarea id="case-url" autocomplete="off" rows="3" placeholder="粘贴分享文本或视频链接；多个链接可按行粘贴" required></textarea><button class="paste-button" type="button" data-paste>粘贴</button></div>
          <div id="source-detection" class="source-detection muted">输入内容后自动识别来源</div>
          <div id="case-acquisition-status" class="source-acquisition-status warning" role="status" hidden></div>
          <div id="case-batch-choices" class="case-batch-choices" hidden></div></div>
          <div class="field case-industry-field" data-case-industry-panel><label for="case-industry">所属行业</label>
            <select id="case-industry" aria-describedby="case-industry-help">${industryOptions()}</select>
            <input id="case-industry-custom" type="text" maxlength="30" autocomplete="off" placeholder="填写行业名称" aria-label="自定义行业名称" hidden disabled>
            <p id="case-industry-help" class="field-hint">选择行业；列表没有时可选“自定义”。</p>
          </div>
          <div class="field case-file-field"><span class="case-file-label">或上传本地视频</span>
            <label class="case-file-picker">
              <input id="case-video-file" type="file" accept=".mp4,.mov,.m4v,.webm,video/mp4,video/quicktime,video/webm" aria-label="选择视频文件" aria-describedby="case-file-help case-file-selected">
              <span class="case-file-picker-main"><strong>选择本地视频</strong><small>MP4、MOV、M4V、WebM · 最大 256 MB</small></span>
              <span class="case-file-picker-action" aria-hidden="true">选择文件</span>
            </label>
            <p id="case-file-selected" class="case-file-selected" role="status" aria-live="polite">未选择文件</p>
            <p id="case-file-help" class="field-hint">自动获取失败时可上传对应的视频。最长 10 分钟、最高 4K，需保留画面和音轨。</p>
          </div></div>
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
    const industryInput = document.querySelector("#case-industry");
    const industryCustomInput = document.querySelector("#case-industry-custom");
    const industryPanel = document.querySelector("[data-case-industry-panel]");
    const detection = document.querySelector("#source-detection");
    const form = document.querySelector("#case-url-form");
    const fileInput = form.querySelector("#case-video-file");
    const fileSelected = form.querySelector("#case-file-selected");
    let uploadedFile = null;
    let uploadedUrl = null;
    let uploadedReceipt = null;
    let reviewCaseId = null;
    let reanalysisRequiresFile = false;
    let uploadRequired = false;
    let acquisition = null;
    let capabilityUnavailable = false;
    const pasteButton = document.querySelector("[data-paste]");
    const resultBox = document.querySelector("#case-result");
    const actionsHost = document.querySelector("[data-case-submit-actions]");
    const inputPanel = document.querySelector("[data-case-input-panel]");
    const profilePanel = document.querySelector("[data-case-profile-panel]");
    const batchChoices = document.querySelector("#case-batch-choices");
    const acquisitionStatus = document.querySelector("#case-acquisition-status");
    const selectedHint = () => form.querySelector('input[name="operator-profile-hint"]:checked')?.value || null;
    const selectedIndustry = () => industryValue(industryInput, industryCustomInput);
    const focusIndustry = () => (industryInput.value === CUSTOM_INDUSTRY ? industryCustomInput : industryInput).focus();
    const batchHints = new Map();
    const batchIndustries = new Map();
    const batchCustomUrls = new Set();
    let activeState = "idle";
    let activeCaseId = null;
    let activeTaskId = null;
    let reanalysisState = null;

    const actionMarkup = (projection) => {
      const actions = [];
      if (projection.submitVisible) {
        actions.push(`<button class="btn btn-primary btn-wide" type="submit" ${projection.submitDisabled || ((uploadRequired || reanalysisRequiresFile) && !fileInput.files.length) ? "disabled" : ""}>${projection.submitLabel}</button>`);
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
      industryInput.disabled = !["idle", "failed", "rejected"].includes(status);
      syncCustomIndustry(industryInput, industryCustomInput);
      pasteButton.disabled = projection.pasteDisabled;
      fileInput.disabled = projection.inputDisabled;
      inputPanel.hidden = !["idle", "failed", "rejected"].includes(status);
      industryPanel.hidden = extractCaseSourceUrls(input.value).length > 1 || !["idle", "failed", "rejected"].includes(status);
      profilePanel.hidden = !["idle", "failed", "rejected"].includes(status) || extractCaseSourceUrls(input.value).length > 1;
      actionsHost.innerHTML = actionMarkup(projection);
      actionsHost.querySelectorAll("[data-route]").forEach((link) => link.addEventListener("click", (event) => {
        event.preventDefault();
        navigate(link.getAttribute("href"));
      }));
    };

    const resetForAnotherCase = () => {
      stopTaskPolling();
      if (location.search) history.replaceState({}, "", "/cases/new");
      activeCaseId = null;
      activeTaskId = null;
      reanalysisState = null;
      input.value = "";
      setIndustryValue(industryInput, industryCustomInput);
      fileInput.value = "";
      fileSelected.textContent = "未选择文件";
      fileSelected.classList.remove("has-file");
      uploadedFile = uploadedUrl = uploadedReceipt = null;
      reviewCaseId = null;
      reanalysisRequiresFile = false;
      batchHints.clear();
      batchIndustries.clear();
      batchCustomUrls.clear();
      form.querySelectorAll('input[name="operator-profile-hint"]').forEach((radio) => { radio.checked = false; });
      resultBox.innerHTML = "";
      document.querySelector("#case-form-error").classList.remove("visible");
      const projection = resetCaseSubmitState();
      setSubmitState(projection.status);
      updateDetection();
      updateAcquisitionNotice();
      input.focus();
    };
    const updateDetection = () => {
      const urls = extractCaseSourceUrls(input.value);
      const projection = detectCaseSourceInput(input.value);
      detection.textContent = projection.label;
      detection.className = projection.recognized ? "source-detection" : "source-detection muted";
      const multi = urls.length > 1 && !reviewCaseId;
      industryPanel.hidden = multi || !["idle", "failed", "rejected"].includes(activeState);
      profilePanel.hidden = multi || !["idle", "failed", "rejected"].includes(activeState);
      batchChoices.hidden = !multi;
      if (!multi) { batchChoices.innerHTML = ""; return; }
      batchChoices.innerHTML = `<p class="field-hint">每个视频单独选择行业和结构类型；已存在的案例不会重复建立任务。</p>
        ${urls.map((url, index) => { const saved = batchIndustries.get(url) || ""; return `<div class="case-batch-choice"><span><strong>${index + 1}. ${escapeHtml(url)}</strong></span>
          <div class="case-batch-controls"><select data-batch-industry-url="${escapeHtml(url)}" aria-label="第 ${index + 1} 个视频的所属行业">${industryOptions(saved || (batchCustomUrls.has(url) ? CUSTOM_INDUSTRY : ""))}</select>
          <select data-batch-url="${escapeHtml(url)}" aria-label="第 ${index + 1} 个视频的结构类型">
            <option value="">选择结构类型</option>
            <option value="mix" ${batchHints.get(url) === "mix" ? "selected" : ""}>混剪型</option>
            <option value="news" ${batchHints.get(url) === "news" ? "selected" : ""}>新闻体</option>
            <option value="hybrid" ${batchHints.get(url) === "hybrid" ? "selected" : ""}>混合型</option>
            <option value="uncertain" ${batchHints.get(url) === "uncertain" ? "selected" : ""}>不确定</option>
          </select><input type="text" data-batch-industry-custom-url="${escapeHtml(url)}" maxlength="30" placeholder="填写行业名称" value="${escapeHtml(saved && !CASE_INDUSTRIES.includes(saved) ? saved : "")}" aria-label="第 ${index + 1} 个视频的自定义行业名称" ${batchCustomUrls.has(url) || saved && !CASE_INDUSTRIES.includes(saved) ? "" : "hidden disabled"}></div></div>`; }).join("")}`;
    };
    const updateAcquisitionNotice = () => {
      const warning = caseAcquisitionWarning(acquisition, {
        hasFile: Boolean(fileInput.files.length), unavailable: capabilityUnavailable,
      });
      acquisitionStatus.textContent = warning;
      acquisitionStatus.hidden = !warning;
    };
    batchChoices.addEventListener("change", (event) => {
      const select = event.target.closest("[data-batch-url]");
      if (select) batchHints.set(select.dataset.batchUrl, select.value);
      const industry = event.target.closest("[data-batch-industry-url]");
      if (industry) {
        const custom = industry.closest(".case-batch-controls").querySelector("[data-batch-industry-custom-url]");
        if (industry.value === CUSTOM_INDUSTRY) batchCustomUrls.add(industry.dataset.batchIndustryUrl);
        else batchCustomUrls.delete(industry.dataset.batchIndustryUrl);
        syncCustomIndustry(industry, custom);
        batchIndustries.set(industry.dataset.batchIndustryUrl, industryValue(industry, custom));
        if (industry.value === CUSTOM_INDUSTRY) custom.focus();
      }
    });
    batchChoices.addEventListener("input", (event) => {
      const custom = event.target.closest("[data-batch-industry-custom-url]");
      if (custom) batchIndustries.set(custom.dataset.batchIndustryCustomUrl, custom.value);
    });
    const showSubmissionResult = (result) => {
      if (!result.duplicate) {
        if (!result.task?.task_id) throw new Error("未取得任务编号，请到任务记录确认状态。");
        navigate(`/tasks/${encodeURIComponent(result.task.task_id)}`, true);
        return;
      }
      if (["queued", "running", "awaiting_review"].includes(result.state) && result.existing_task?.task_id) {
        navigate(`/tasks/${encodeURIComponent(result.existing_task.task_id)}`, true);
        return;
      }
      resultBox.innerHTML = duplicateResultHtml(result);
      setSubmitState(result.state, {
        caseId: result.case_id,
        taskId: result.existing_task?.task_id || null,
        reanalysis: result.state,
      });
    };
    const renderBatchResults = (results, total, pendingCount = null) => {
      const added = results.filter(({ response }) => response && !response.duplicate).length;
      const existing = results.filter(({ response }) => response?.duplicate).length;
      const unfinished = pendingCount ?? total - results.length;
      const rows = results.map(({ item, response, error }) => {
        const label = escapeHtml(item.url);
        if (error) {
          return `<li><span>${label}</span><strong class="case-batch-error">未提交</strong><small>${escapeHtml(error.detail?.next_action || error.message || "请稍后重试。")}</small></li>`;
        }
        const taskId = response.duplicate ? response.existing_task?.task_id : response.task?.task_id;
        const caseId = response.case_id;
        const state = response.duplicate ? response.state : "queued";
        const stateLabel = ({ queued: "已加入队列", running: "正在分析", awaiting_review: "待审核", approved: "已入库", failed: "需重新分析", rejected: "未收录" })[state] || "已有记录";
        const href = taskId && ["queued", "running", "failed"].includes(state) ? `/tasks/${encodeURIComponent(taskId)}`
          : caseId && ["awaiting_review", "approved", "rejected"].includes(state) ? `/cases/${encodeURIComponent(caseId)}` : null;
        const action = href ? `<a href="${href}" data-route>查看${["queued", "running"].includes(state) ? "进度" : state === "failed" ? "任务" : "案例"}</a>` : "";
        return `<li><span>${label}</span><strong>${stateLabel}</strong>${action}</li>`;
      }).join("");
      resultBox.innerHTML = `<div class="case-batch-results" role="status"><h3>${pendingCount === null ? "正在逐条提交" : "提交结果"}</h3>
        <p>已加入队列 ${added} 条 · 已有记录 ${existing} 条 · ${pendingCount === null ? `处理中 ${unfinished} 条` : `未提交 ${unfinished} 条`}</p>
        ${pendingCount ? '<p>未提交的链接已保留在输入框；请在任务完成或问题解决后重试。</p>' : ""}
        <ol>${rows}</ol>${results.length ? '<a class="inline-link" href="/tasks" data-route>查看所有任务</a>' : ""}</div>`;
      resultBox.querySelectorAll("[data-route]").forEach((link) => link.addEventListener("click", (event) => {
        event.preventDefault();
        navigate(link.getAttribute("href"));
      }));
    };
    const submitCaseSource = async (extra = {}) => {
      const file = fileInput.files[0];
      if (file) {
        const invalid = validateCaseFile(file);
        if (invalid) throw new Error(invalid);
      } else if (reanalysisRequiresFile) {
        throw new Error("请重新上传与来源对应的视频文件。");
      }
      if (!input.value.trim()) throw new Error("请粘贴来源链接或抖音分享内容。");
      const controller = new AbortController();
      stopUpload = () => controller.abort();
      if (file && (file !== uploadedFile || input.value !== uploadedUrl || !uploadedReceipt)) {
        resultBox.innerHTML = `<div class="result-banner" role="status"><h3>正在上传并检查视频</h3><p>请保持页面打开。上传完成后，会自动进入可恢复的任务进度页。</p></div>`;
        uploadedReceipt = await uploadCaseFile(api, { file, sourceUrl: input.value, signal: controller.signal });
        uploadedFile = file;
        uploadedUrl = input.value;
      }
      if (controller.signal.aborted || document.querySelector("#case-url-form") !== form) throw new DOMException("Aborted", "AbortError");
      resultBox.innerHTML = `<div class="result-banner" role="status"><h3>正在建立分析任务</h3></div>`;
      if (reviewCaseId) {
        const reviewed = await api(`/api/cases/${encodeURIComponent(reviewCaseId)}/review`, {
          method: "POST", body: JSON.stringify({ decision: "reanalyze", reason: extra.reason,
            operator_profile_hint: selectedHint(), industry: selectedIndustry(),
            ...(file ? { source_upload_id: uploadedReceipt.upload_id } : {}) }),
        });
        return { ...reviewed, duplicate: false, case_id: reviewCaseId };
      }
      return api("/api/cases/analyze", {
        method: "POST", body: JSON.stringify({ url: file ? uploadedReceipt.canonical_url : input.value,
          operator_profile_hint: selectedHint(), industry: selectedIndustry(),
          ...(file ? { source_upload_id: uploadedReceipt.upload_id } : {}), ...extra }),
      });
    };
    input.addEventListener("input", updateDetection);
    industryInput.addEventListener("change", () => {
      syncCustomIndustry(industryInput, industryCustomInput);
      if (industryInput.value === CUSTOM_INDUSTRY) industryCustomInput.focus();
    });
    fileInput.addEventListener("change", () => {
      const file = fileInput.files[0];
      fileSelected.textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : "未选择文件";
      fileSelected.classList.toggle("has-file", Boolean(file));
      updateAcquisitionNotice();
      setSubmitState(activeState);
    });
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
      if (!hasSpecificIndustry(selectedIndustry())) {
        showToast("请填写案例所属行业。");
        focusIndustry();
        return;
      }

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
        const restarted = await submitCaseSource({ reanalyze: true, reason });
        if (document.querySelector("#case-url-form") !== form) return;
        showSubmissionResult(restarted);
      } catch (error) {
        if (document.querySelector("#case-url-form") !== form) return;
        showToast(error.detail?.next_action || error.message);
        setSubmitState(reanalysisState || "failed");
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorBox = document.querySelector("#case-form-error");
      if (activeState !== "idle") return;
      errorBox.classList.remove("visible"); resultBox.innerHTML = "";
      const urls = extractCaseSourceUrls(input.value);
      if (urls.length > 1) {
        const showError = (message) => { errorBox.textContent = message; errorBox.classList.add("visible"); };
        if (urls.length > 20) return showError("一次最多添加 20 个链接，请分批提交。");
        if (fileInput.files.length) return showError("多个链接不能共用一个视频文件。请移除文件，或逐条上传对应视频。");
        if (uploadRequired) return showError("当前需要上传视频文件，请逐条添加并上传对应的视频。");
        if (urls.some((url) => !batchHints.get(url))) return showError("请为每个视频选择结构类型；不确定也可以选择。");
        if (urls.some((url) => !hasSpecificIndustry(batchIndustries.get(url)))) return showError("请为每个视频填写具体行业。");
        const items = urls.map((url) => ({ url, hint: batchHints.get(url), industry: batchIndustries.get(url).trim() }));
        const controller = new AbortController();
        const abortBatch = () => controller.abort();
        stopUpload = abortBatch;
        const batchProgress = [];
        setSubmitState("submitting");
        try {
          const batch = await submitCaseBatch(items, ({ url, hint, industry }) => api("/api/cases/analyze", {
            method: "POST", body: JSON.stringify({ url, operator_profile_hint: hint, industry }), signal: controller.signal,
          }), (result) => {
            batchProgress.push(result);
            if (document.querySelector("#case-url-form") === form) renderBatchResults(batchProgress, items.length);
          });
          if (document.querySelector("#case-url-form") !== form) return;
          input.value = batch.pending.map((item) => item.url).join("\n");
          if (batch.pending.length === 1) {
            const hint = form.querySelector(`input[name="operator-profile-hint"][value="${batch.pending[0].hint}"]`);
            if (hint) hint.checked = true;
            setIndustryValue(industryInput, industryCustomInput, batch.pending[0].industry);
          } else {
            setIndustryValue(industryInput, industryCustomInput);
          }
          setSubmitState("idle");
          updateDetection();
          renderBatchResults(batch.results, items.length, batch.pending.length);
        } catch (error) {
          if (document.querySelector("#case-url-form") !== form) return;
          if (error.name !== "AbortError") showError(error.detail?.next_action || error.message || "请到任务记录确认提交状态。");
          setSubmitState("idle");
          updateDetection();
        } finally { if (stopUpload === abortBatch) stopUpload = null; }
        return;
      }
      if (!selectedHint()) {
        errorBox.textContent = "请选择视频结构类型；不确定也可以选择。";
        errorBox.classList.add("visible");
        profilePanel.querySelector("input")?.focus();
        return;
      }
      if (!hasSpecificIndustry(selectedIndustry())) {
        errorBox.textContent = "请填写案例所属的具体行业。";
        errorBox.classList.add("visible");
        focusIndustry();
        return;
      }
      setSubmitState("submitting");
      try {
        const result = await submitCaseSource();
        if (document.querySelector("#case-url-form") !== form) return;
        showSubmissionResult(result);
      } catch (error) {
        if (document.querySelector("#case-url-form") !== form) return;
        const next = error.detail?.next_action || error.message || "请检查来源链接和视频文件后重新提交。";
        const progressUnavailable = error.detail?.code === "CASE_TASK_PROGRESS_UNAVAILABLE";
        resultBox.innerHTML = `<div class="result-banner error"><h3>${progressUnavailable ? "未找到当前进度" : "暂时无法分析这个视频"}</h3><p>${escapeHtml(next)}</p>${progressUnavailable ? '<a class="btn btn-secondary" href="/tasks" data-route>查看任务记录</a>' : ""}</div>`;
        resultBox.querySelector("[data-route]")?.addEventListener("click", (event) => {
          event.preventDefault();
          navigate("/tasks");
        });
        setSubmitState("idle");
      }
    });
    setSubmitState("idle");
    api("/api/capabilities").then((capabilities) => {
      if (document.querySelector("#case-url-form") !== form) return;
      uploadRequired = capabilities.case_analysis?.upload_required === true;
      acquisition = capabilities.case_analysis?.source_acquisition || null;
      capabilityUnavailable = !["qiyun", "legacy_downloader", "upload_only"].includes(acquisition?.mode);
      if (uploadRequired) {
        const description = document.querySelector(".add-case-page .page-heading-copy > p");
        if (description) description.textContent = "粘贴来源链接，并上传对应的视频文件。";
        form.querySelector(".case-file-label").textContent = "上传本地视频";
        form.querySelector("#case-file-help").textContent = "当前需要上传视频。最长 10 分钟、最高 4K，需保留画面和音轨。";
      }
      updateAcquisitionNotice();
      setSubmitState(activeState);
    }).catch(() => {
      if (document.querySelector("#case-url-form") !== form) return;
      capabilityUnavailable = true;
      updateAcquisitionNotice();
    });
    const reanalysisCaseId = new URLSearchParams(location.search).get("reanalyze_case");
    if (reanalysisCaseId) {
      setSubmitState("restoring");
      api(`/api/cases/${encodeURIComponent(reanalysisCaseId)}`).then((detail) => {
        if (document.querySelector("#case-url-form") !== form) return;
        reviewCaseId = reanalysisCaseId;
        reanalysisRequiresFile = detail.review_media?.operator_uploaded === true;
        input.value = detail.source_url || "";
        setIndustryValue(industryInput, industryCustomInput, detail.industry === "待分类" ? "" : detail.industry);
        const hint = detail.operator_profile_hint;
        if (["mix", "news", "hybrid", "uncertain"].includes(hint)) {
          form.querySelector(`input[name="operator-profile-hint"][value="${hint}"]`).checked = true;
        }
        updateDetection();
        resultBox.innerHTML = `<div class="result-banner"><h3>准备重新分析</h3><p>${reanalysisRequiresFile ? "请重新上传对应的视频文件。" : "可自动获取原视频，或上传对应的视频文件。"}提交时需要说明原因，原有记录不会被覆盖。</p></div>`;
        setSubmitState("rejected", { caseId: reviewCaseId, reanalysis: "rejected" });
      }).catch((error) => { if (document.querySelector("#case-url-form") === form) { showToast(error.message); setSubmitState("idle"); } });
      return;
    }
    const retryTaskId = new URLSearchParams(location.search).get("retry_task");
    if (retryTaskId) {
      setSubmitState("restoring");
      resultBox.innerHTML = `<div class="result-banner"><h3>正在恢复上次任务</h3></div>`;
      api(`/api/tasks/${encodeURIComponent(retryTaskId)}`).then(({ task }) => {
        if (document.querySelector("#case-url-form") !== form) return;
        const resumeDestination = caseTaskResumeDestination(task);
        if (resumeDestination) {
          navigate(resumeDestination, true);
          return;
        }
        const retry = projectFailedCaseTask(task);
        if (!retry || retry.taskId !== retryTaskId) {
          throw new Error("这条任务不能从添加案例页恢复。请返回任务记录确认状态。");
        }
        input.value = retry.sourceUrl;
        setIndustryValue(industryInput, industryCustomInput, retry.industry === "待分类" ? "" : retry.industry);
        if (retry.operatorProfileHint) {
          const choice = form.querySelector(`input[name="operator-profile-hint"][value="${retry.operatorProfileHint}"]`);
          if (choice) choice.checked = true;
        }
        updateDetection();
        resultBox.innerHTML = `<div class="result-banner error"><h3>上次分析未完成</h3><p>请核对来源后重新分析；也可以上传对应的视频文件。上次任务记录会保留。</p></div>`;
        setSubmitState("failed", { caseId: retry.caseId, taskId: retry.taskId, reanalysis: "failed" });
      }).catch((error) => {
        if (document.querySelector("#case-url-form") !== form) return;
        resultBox.innerHTML = `<div class="result-banner error"><h3>无法恢复这条任务</h3><p>${escapeHtml(error.message || "请返回任务记录确认状态。")}</p></div>`;
        setSubmitState("idle");
      });
    }
  }

  async function renderCaseDetail(caseId) {
    dispose(); skeletonPage("案例审核");
    try {
      const detail = await api(`/api/cases/${encodeURIComponent(caseId)}`);
      app.innerHTML = shell("案例审核", caseReviewContent(detail, statusPill));
      stopMediaPreview = bindCaseMediaPreview(app);
      bindCommonActions();
      document.querySelector("[data-profile-annotation]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const decision = await openModal({
          title: detail.profile_annotation ? "修改历史补充" : "补充结构类型",
          description: "这是对历史案例的人工标记，不改变已批准案例或创作可用范围。请选择你观察到的结构类型。",
          confirmLabel: "保存补充",
          profileHintRequired: true,
          reasonOptional: true,
          reasonLabel: "备注（选填）",
          reasonPlaceholder: "可补充选择这个类型的原因",
        });
        if (!decision.confirmed) return;
        button.disabled = true;
        try {
          await api(`/api/cases/${encodeURIComponent(caseId)}/profile-annotation`, {
            method: "POST",
            body: JSON.stringify({
              operator_profile_hint: decision.profileHint,
              note: decision.reason,
              approved_case_sha256: detail.approved_case_sha256,
              expected_annotation_sha256: detail.profile_annotation_sha256,
            }),
          });
          showToast("历史补充已保存");
          return renderCaseDetail(caseId);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
        }
      });
      document.querySelector("[data-industry-annotation]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const decision = await openModal({
          title: detail.industry_annotation ? "修改历史补充行业" : "补充行业",
          description: "这是对历史案例的人工补充，不改变已入库案例。",
          confirmLabel: "保存补充",
          industryRequired: true,
          industryValue: detail.industry_annotation?.industry || "",
          reasonOptional: true,
          reasonLabel: "备注（选填）",
          reasonPlaceholder: "可补充选择这个行业的原因",
        });
        if (!decision.confirmed) return;
        button.disabled = true;
        try {
          await api(`/api/cases/${encodeURIComponent(caseId)}/industry-annotation`, {
            method: "POST",
            body: JSON.stringify({
              industry: decision.industry,
              note: decision.reason,
              approved_case_sha256: detail.approved_case_sha256,
              expected_annotation_sha256: detail.industry_annotation_sha256,
            }),
          });
          showToast("行业补充已保存");
          return renderCaseDetail(caseId);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
        }
      });
      document.querySelectorAll("[data-review-action]").forEach((button) => button.addEventListener("click", async () => {
        if (button.dataset.reviewAction === "reanalyze") {
          return navigate(`/cases/new?reanalyze_case=${encodeURIComponent(caseId)}`);
        }
        const action = button.dataset.reviewAction;
        let reason = "";
        let profileHint = null;
        let evidenceReview = null;
        if (action === "approve") {
          if (detail.evidence_review?.required) {
            const evidence = detail.evidence_review;
            if (!evidence.available) { showToast("待确认的分析证据暂时无法读取，请刷新后重试。"); return; }
            const checks = [...document.querySelectorAll("[data-evidence-kind][data-item-id]")];
            const missing = checks.find((item) => !item.checked);
            if (missing) { showToast("请先逐项确认分析疑点。"); missing.focus(); return; }
            evidenceReview = {
              candidate_sha256: evidence.candidate_sha256,
              narration_sha256: evidence.narration_sha256,
              shot_sha256: evidence.shot_sha256,
              narration_decisions: checks.filter((item) => item.dataset.evidenceKind === "narration").map((item) => ({ item_id: item.dataset.itemId, action: "keep" })),
              shot_decisions: checks.filter((item) => item.dataset.evidenceKind === "shot").map((item) => ({ item_id: item.dataset.itemId, action: "keep" })),
            };
          }
          const recovery = button.textContent.includes("恢复");
          const decision = await openModal({
            title: recovery ? "完成上次批准？" : "批准这个案例？",
            description: recovery
              ? "系统只会完成上次未保存完的批准，不会重复审核。批准不会改变原视频素材使用权。"
              : evidenceReview
                ? "请确认你已对照原视频核对所有疑点，并认可当前展示的原识别与分镜。批准不会获得原视频素材使用权。"
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
          const result = await api(`/api/cases/${encodeURIComponent(caseId)}/review`, { method: "POST", body: JSON.stringify({ decision: action, reason, operator_profile_hint: profileHint, evidence_review: evidenceReview }) });
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
    dispose(); skeletonPage("任务进度");
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
      app.innerHTML = shell("任务进度", `<main class="page task-detail-page">${pageHeading("任务进度", "案例分析", "进度来自实际分析步骤，离开页面后仍会继续。")}
        <div data-live-progress>${progressPanel(payload.task, { boundaryReview: payload.boundary_review })}</div>
        ${boundaryReviewPanel(payload.boundary_review)}</main>`);
      bindCommonActions();
      const form = app.querySelector("[data-boundary-review]");
      form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
          const decisions = payload.boundary_review.items.map((item, index) => ({
            frame_id: item.frame_id,
            action: form.querySelector(`input[name="boundary-${index}"]:checked`)?.value,
          }));
          await api(`/api/tasks/${encodeURIComponent(taskId)}/boundary-review`, {
            method: "POST",
            body: JSON.stringify({ shot_sha256: payload.boundary_review.shot_sha256, decisions }),
          });
          showToast("已确认分镜，正在继续分析");
          return renderTaskDetail(taskId);
        } catch (error) {
          button.disabled = false;
          showToast(error.message || "确认失败，请刷新后重试。");
        }
      });
      const initialStatus = payload.task.status;
      bindTaskProgress(payload.task, (status) => {
        if (status === "failed" && initialStatus !== "failed") renderTaskDetail(taskId);
      }, payload.boundary_review);
    } catch (error) { renderLoadError("任务暂时无法读取", error); }
  }

  return { renderCases, renderCaseNew, renderCaseDetail, renderTaskDetail, dispose };
}
