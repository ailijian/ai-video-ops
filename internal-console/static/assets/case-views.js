import { mountRecovery } from "./review-workflow-ui.mjs?v=case-recovery-ui1";
import { caseRecovery } from "./case-review-result.mjs?v=case-joint-1";
import { nativeNotesMarkup } from './case-excel-native.mjs?v=excel-native-1';
import { makeTypeConfirmation,typeConfirmationMarkup,typeLabel } from './case-type-confirmation.mjs?v=case-joint-1';
import { shareConfirmation, shareResultMessage, sharePreviewCard } from "./case-share-confirmation.mjs?v=case-joint-1";
import { bindEvidenceWorkspace, reviewWorkspace } from "./case-evidence-workspace.mjs?v=case-review-ux1";
import { formatConsoleTime } from "./ui-format.mjs?v=ui-1";
import { boundaryReviewPanel, caseCard, caseReviewContent, escapeHtml, progressPanel } from "./case-components.js?v=case-joint-1";
import { bindCaseMediaPreview } from "./case-media-preview.mjs?v=case-media-fit-1";
import { caseTaskResumeDestination } from "./case-submit-state.mjs?v=mobile-reliability-2";
import { startTaskPolling } from "./task-progress.js?v=mobile-reliability-1";
import { detectCaseSourceInput, extractCaseSourceUrls } from "./case-source-detection.mjs?v=case-batch-1";
import { uploadCaseFile, validateCaseFile } from "./case-file-upload.mjs?v=source-upload-ui-2";
import { intakeCounts, intakeItemState, intakeStage, UNCERTAIN_INDUSTRY, classificationDraft, classificationSubmittable, classificationDiffers, batchConfirmableItems, confirmedClassificationLabel } from "./case-batch-submit.mjs?v=flow-closure-2";
import { CASE_INDUSTRIES, industryOptions, industryValue, syncCustomIndustry } from "./case-industry.mjs?v=industry-2";
import { caseListCard, caseStateLabels, formatCaseDuration, listEmpty, listSkeleton, searchIcon } from "./list-ui.mjs?v=case-joint-1";

export function caseAcquisitionWarning(acquisition, { hasFile = false, unavailable = false } = {}) {
  if (hasFile || (acquisition?.mode === "qiyun" && acquisition.configured)) return "";
  if (acquisition?.mode === "qiyun") return "奇云付费解析尚未连接。请上传视频，或联系管理员检查配置。";
  if (acquisition?.mode === "legacy_downloader") return "当前使用原有下载方式，未启用奇云付费解析。获取失败时可上传本地视频。";
  if (acquisition?.mode === "upload_only") return "当前无法自动获取视频，请上传本地视频。";
  return unavailable ? "暂时无法确认视频获取方式，请刷新页面后再提交。" : "";
}

export function bindCaseReviewNavigation(root) {
  root.querySelector("[data-scroll-review-decision]")?.addEventListener("click", () => {
    const decision = root.querySelector("#case-review-decision");
    decision?.scrollIntoView({block: "start"});
    decision?.focus({preventScroll: true});
  });
}

export function createCaseViews({ app, api, navigate, shell, bindCommonActions, pageHeading, skeletonPage, statusPill, showToast, openModal, renderLoadError }) {
  let stopPolling = null;
  let stopMediaPreview = null;
  let stopUpload = null;
  let renderVersion = 0;
  const stopTaskPolling = () => { stopPolling?.(); stopPolling = null; };
  const dispose = () => { renderVersion++; stopTaskPolling(); stopMediaPreview?.(); stopMediaPreview = null; stopUpload?.(); stopUpload = null; };

  async function renderCases() {
    dispose();
    const version = renderVersion;
    app.innerHTML = shell("案例", `<main class="page page-standard brand-list-page case-library-page">${pageHeading("", "案例", "找到值得参考的视频，也关注自己的每一次投稿。")}${listSkeleton()}</main>`);
    bindCommonActions();
    try {
      const params = new URLSearchParams(location.search);
      const view = ["shared", "mine", "review"].includes(params.get("view")) ? params.get("view") : "shared";
      const query = new URLSearchParams({view, search:params.get("search") || "", industry:params.get("industry") || "", video_type:params.get("video_type") || "", status:params.get("status") || "", page:String(Math.max(1, Number(params.get("page")) || 1))});
      const data = await api(`/api/cases?${query}`);
      if (version !== renderVersion || location.pathname !== "/cases") return;
      const link = patch => `/cases?${new URLSearchParams({...Object.fromEntries(query), ...patch})}`;
      const returnPath = `/cases?${query}`;
      const views = [["shared", "共享案例库"], ["mine", "我的投稿"], ...(data.capabilities?.case_library_reviewer ? [["review", "审核工作"]] : [])];
      const tabs = `<nav class="list-view-tabs" aria-label="案例视图">${views.map(([value,label])=>`<a href="/cases?view=${value}" data-route class="${value===view?"active":""}" ${value===view?'aria-current="page"':""}>${label}</a>`).join("")}</nav>`;
      const search = query.get("search"), industry = query.get("industry"), status = query.get("status"), videoType=query.get('video_type');
      const filters = view === "shared"
        ? `<label class="list-select-label">行业<select id="case-industry-filter" aria-label="行业"><option value="">全部行业</option>${(data.industries || []).map(value=>`<option ${value===industry?"selected":""} value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("")}</select></label>${data.video_types?.length ? `<label class="list-select-label">视频类型<select id="case-type-filter" aria-label="视频类型"><option value="">全部类型</option>${data.video_types.map(value=>`<option value="${escapeHtml(value)}" ${value===videoType?'selected':''}>${escapeHtml(typeLabel(value))}</option>`).join("")}</select></label>` : ""}`
        : `<label class="list-select-label">状态<select id="case-status-filter" aria-label="状态"><option value="">全部状态</option>${Object.keys(data.status_counts || {}).map(value=>`<option value="${escapeHtml(value)}" ${value===status?"selected":""}>${caseStateLabels[value] || "待处理"}</option>`).join("")}</select></label>`;
      const toolbar = `<form class="list-toolbar" id="case-search-form"><div class="list-search">${searchIcon}<label class="sr-only" for="case-search">搜索视频标题</label><input id="case-search" type="search" maxlength="120" placeholder="搜索视频标题" value="${escapeHtml(search)}"><button class="btn btn-secondary btn-compact" type="submit">搜索</button></div>${filters}</form>`;
      const emptyTitle = search || industry || status ? "没有找到符合条件的视频" : view === "shared" ? "优秀案例，等待下一次分享" : view === "mine" ? "从第一条视频投稿开始" : "暂时没有待处理案例";
      const emptyText = search || industry || status ? "试试其他关键词，或调整筛选条件。" : view === "shared" ? "正式获准共享的视频会出现在这里。" : view === "mine" ? "提交视频后，可以在这里继续解析、核对和查看审核进度。" : "新案例完成解析后，会进入审核工作。";
      const cards = data.cases.length ? `<div class="case-library-list">${data.cases.map(item=>caseListCard(item,statusPill,returnPath)).join("")}</div>` : listEmpty(emptyTitle,emptyText);
      const page = Number(data.page), pages = Math.max(1, Math.ceil(data.total / data.page_size));
      const pagination = pages > 1 ? `<nav class="list-pagination" aria-label="案例分页">${page>1?`<a class="btn btn-secondary" href="${escapeHtml(link({page:String(page-1)}))}" data-route>上一页</a>`:""}<span>${page} / ${pages}</span>${page<pages?`<a class="btn btn-secondary" href="${escapeHtml(link({page:String(page+1)}))}" data-route>下一页</a>`:""}</nav>` : "";
      app.innerHTML = shell("案例", `<main class="page page-standard brand-list-page case-library-page">${pageHeading("", "案例", view === "shared" ? "值得参考的结构，来自正式获准共享的视频。" : view === "mine" ? "每一条投稿，都有清楚的进度和下一步。" : "核对证据、正式收录，再独立决定共享展示。", '<a class="btn btn-secondary" href="/cases/excel-preview" data-route>Excel 批量导入</a><a class="btn btn-primary" href="/cases/new" data-route>提交视频</a>')}${tabs}${toolbar}<p class="list-result-count">${data.total} 条${view === "mine" ? "投稿" : "案例"}</p>${cards}${pagination}</main>`);
      bindCommonActions();
      document.querySelector("#case-search-form")?.addEventListener("submit", event=>{event.preventDefault();navigate(link({search:document.querySelector("#case-search").value.trim(),page:"1"}));});
      document.querySelector("#case-industry-filter")?.addEventListener("change", event=>navigate(link({industry:event.target.value,page:"1"})));
      document.querySelector("#case-status-filter")?.addEventListener("change", event=>navigate(link({status:event.target.value,page:"1"})));
      document.querySelector("#case-type-filter")?.addEventListener("change", event=>navigate(link({video_type:event.target.value,page:"1"})));
      bindCardCovers();
    } catch (error) { if(version===renderVersion) error.status===404 ? renderCaseRestricted("无法访问这个案例视图") : renderLoadError("案例暂时无法读取", error); }
  }

  function renderCaseRestricted(title="无法访问这个案例") {
    app.innerHTML=shell("案例",`<main class="page page-standard brand-list-page">${listEmpty(title,"记录不存在或当前账号没有查看权限。请返回案例列表。")}<p><a class="btn btn-secondary" href="/cases" data-route>返回案例列表</a></p></main>`);
    bindCommonActions();
  }

  function bindCardCovers() {
    app.querySelectorAll(".case-card-cover img").forEach(img=>{
      const fallback=()=>{img.hidden=true;img.parentElement.querySelector(".case-cover-placeholder").hidden=false;};
      img.addEventListener("error",fallback,{once:true});
      if(img.complete && !img.naturalWidth) fallback();
    });
  }

  function caseReturnPath() {
    const path=new URLSearchParams(location.search).get("return") || "/cases";
    return /^\/cases(?:\?|$)/.test(path) ? path : "/cases";
  }

  function publicationPanel(detail) {
    const context=detail.publication_context;
    if(!detail.permissions?.can_publish) return "";
    const typePanel=detail.video_type_context && context?.available?`<details class="publication-panel" id="case-type-management"><summary>视频类型管理 <span>${escapeHtml(typeLabel(detail.video_type_context.current?.record.confirmed_type_id))}</span></summary>${typeConfirmationMarkup(detail.video_type_context,escapeHtml)}<p>历史案例的类型变更不会重新批准案例，也不会自动重新共享。</p><button type="button" class="btn btn-secondary" data-type-action="change">保存类型核对</button>${detail.video_type_context.current?'<button type="button" class="btn btn-ghost" data-type-action="withdraw">撤回当前类型</button>':''}</details>`:'';
    if(!context?.available)return `${typePanel}<section class="work-surface"><h2>共享展示暂不可发布</h2><p>${escapeHtml(context?.blocker?.message || "原批准的来源、隐私或收据证据尚未完整核对。")}</p><p>${escapeHtml(context?.blocker?.next_action || "请由审核或运维人员按原来源补证；历史批准记录保留，不会自动公开。")}</p>${context?.withdraw_context?'<button type="button" class="btn btn-secondary" data-withdraw-unavailable-display>撤回现有共享</button>':''}</section>`;
    return `${typePanel}<details class="publication-panel"><summary>共享展示管理 <span>${context.published?"当前已共享":"尚未共享"}</span></summary><form id="case-publication-form">
      <p>案例收录与共享展示分别确认。仅发布下列已核对的展示内容。</p>
      <p>本次展示类型：${escapeHtml(typeLabel(detail.video_type_context?.current?.record.confirmed_type_id))}</p>
      <div class="field"><label for="display-title">共享标题</label><input id="display-title" maxlength="120" required value="${escapeHtml(detail.shared_display?.title || detail.title)}"></div>
      <div class="field"><label for="display-summary">结构参考（选填）</label><textarea id="display-summary" maxlength="1000" rows="3" placeholder="只整理合法的结构启发，不包含私人转写或客户资料。">${escapeHtml(detail.shared_display?.structure_summary || "")}</textarea></div>
      ${context.cover_available ? '<label class="publication-check"><input id="share-cover" type="checkbox">同时展示已有封面，单独确认展示许可</label><div class="publication-cover-fields" hidden><div class="field"><label for="cover-reference">展示许可证据</label><input id="cover-reference" maxlength="1000" placeholder="对应原案例与封面的授权证据引用"></div><div class="field"><label for="cover-statement">许可范围说明</label><textarea id="cover-statement" maxlength="1000" rows="2"></textarea></div></div>' : '<p class="field-hint">暂无可核对的封面，共享卡片会显示统一占位。</p>'}
      <label class="publication-check"><input id="display-confirmed" type="checkbox" required>已核对标题、分类与参考内容，确认不含未获准公开的信息</label>
      <div class="publication-actions"><button class="btn btn-primary" type="submit">确认共享展示</button>${context.published?'<button class="btn btn-secondary" type="button" data-withdraw-display>撤回共享</button>':""}</div><p class="form-error" data-publication-error role="alert"></p>
    </form></details>`;
  }

  function bindPublication(detail,caseId) {
    let pendingTypeOperation=null;
    app.querySelectorAll('[data-type-action]').forEach(button=>button.addEventListener('click',async()=>{
      const type=detail.video_type_context;const withdraw=button.dataset.typeAction==='withdraw';
      try{
        const confirmation=withdraw?null:makeTypeConfirmation(type,{typeId:app.querySelector('#case-video-type').value,
          otherNote:app.querySelector('#case-other-type').value,reason:app.querySelector('#case-type-reason').value});
        if(pendingTypeOperation && pendingTypeOperation.withdraw!==withdraw){showToast('请先核对上次类型保存结果。');return;}
        if(!pendingTypeOperation){
          const answer=await openModal({title:withdraw?'撤回当前类型？':'保存历史案例的类型核对？',description:'原案例收录保持。类型变化后，旧类型的共享展示停止；再次共享需明确核对。',confirmLabel:withdraw?'撤回类型':'保存类型核对'});
          if(!answer.confirmed)return;
        }
        button.disabled=true;
        const context=detail.publication_context;
        pendingTypeOperation ||= {withdraw,payload:{
          operation_id:'type_'+(withdraw?'withdraw_':'')+crypto.randomUUID().replaceAll('-',''),action:withdraw?'revoke_type':confirmation.type_id==null?'defer_type':'confirm_type',
          confirmation,approved_case_sha256:context.approved_case_sha256,approval_receipt_sha256:context.approval_receipt_sha256,
          expected_parent_sha256:type.source.parent_decision_sha256}};
        await api(`/api/cases/${encodeURIComponent(caseId)}/type-decisions`,{method:'POST',body:JSON.stringify(pendingTypeOperation.payload)});
        showToast(withdraw?'类型已撤回':'类型核对已保存；共享需另行确认');await renderCaseDetail(caseId);
      }catch(error){showToast(error.message);button.disabled=false;if(error.status===422)pendingTypeOperation=null;else button.textContent='继续原类型保存';}
    }));
    app.querySelector('[data-withdraw-unavailable-display]')?.addEventListener('click',async()=>{
      const answer=await openModal({title:'撤回现有共享？',description:'停止对外展示，原收录与历史收据保留。',confirmLabel:'撤回共享'});
      if(!answer.confirmed)return;
      const context=detail.publication_context.withdraw_context;
      try{await api(`/api/cases/${encodeURIComponent(caseId)}/publication`,{method:'POST',body:JSON.stringify({action:'withdraw',
        approved_case_sha256:context.approved_case_sha256,approval_receipt_sha256:context.approval_receipt_sha256,
        expected_display_receipt_sha256:context.display_receipt_sha256})});await renderCaseDetail(caseId);}catch(error){showToast(error.message);}
    });
    const form=app.querySelector("#case-publication-form");if(!form)return;
    let publicationOperation=null;
    const cover=app.querySelector("#share-cover");
    cover?.addEventListener("change",()=>{app.querySelector(".publication-cover-fields").hidden=!cover.checked;});
    const submit=async(action)=>{
      const context=detail.publication_context;
      const payload={action,title:app.querySelector("#display-title").value,structure_summary:app.querySelector("#display-summary").value,
        approved_case_sha256:context.approved_case_sha256,approval_receipt_sha256:context.approval_receipt_sha256,
        expected_display_receipt_sha256:context.display_receipt_sha256};
      if(action==='publish' && detail.video_type_context?.current){
        publicationOperation ||= 'pub_'+crypto.randomUUID().replaceAll('-','');
        payload.publication_operation_id=publicationOperation;payload.expected_type_decision_sha256=detail.video_type_context.current.ref.sha256;
      }
      if(action==="publish" && cover?.checked)payload.cover_evidence={reference:app.querySelector("#cover-reference").value,statement:app.querySelector("#cover-statement").value,display_rights_confirmed:true};
      form.querySelectorAll("button").forEach(button=>button.disabled=true);
      try{await api(`/api/cases/${encodeURIComponent(caseId)}/publication`,{method:"POST",body:JSON.stringify(payload)});showToast(action==="publish"?"共享展示已发布":"共享展示已撤回");await renderCaseDetail(caseId);}
      catch(error){const host=form.querySelector("[data-publication-error]");host.textContent=error.detail?.message || error.message;host.classList.add("visible");form.querySelectorAll("button").forEach(button=>button.disabled=false);}
    };
    form.addEventListener("submit",event=>{event.preventDefault();if(form.reportValidity())submit("publish");});
    app.querySelector("[data-withdraw-display]")?.addEventListener("click",async()=>{const decision=await openModal({title:"撤回共享展示？",description:"普通浏览用户将不能继续读取此案例的共享内容和封面，原收录记录会保留。",confirmLabel:"撤回共享"});if(decision.confirmed)submit("withdraw");});
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


  const profileLabels = { mix: "素材混剪", news: "新闻体", hybrid: "混合型", uncertain: "暂不确定" };
  const intakeSteps = (step) => `<ol class="intake-steps" aria-label="录入步骤">${["粘贴链接", "自动解析", "确认分类"].map((label, i) => `<li class="${i === step ? "active" : ""}"><span>${i + 1}</span>${label}</li>`).join("")}</ol>`;

  async function renderCaseNew() {
    dispose();
    const params = new URLSearchParams(location.search);
    app.innerHTML = shell("添加案例", `<main class="page page-form add-case-page">
      ${pageHeading("", "添加案例", "粘贴视频链接，系统会自动分析内容并推荐分类。")}
      ${intakeSteps(0)}<section class="work-surface add-case-surface"><h2>粘贴链接，开始解析</h2>
      <form id="case-url-form" novalidate><div class="field"><label for="case-url">视频链接</label>
        <div class="input-combo"><textarea id="case-url" rows="5" maxlength="40000" placeholder="粘贴抖音分享内容或视频链接，多个链接可以一起粘贴。" required></textarea><button class="paste-button" type="button" data-paste>粘贴</button></div>
        <p class="field-hint">无需提前判断视频类型，分析完成后可以修改。</p>
        <p id="source-detection" class="source-detection muted">当前支持抖音，每批最多 10 条有效视频。</p>
        <p id="case-acquisition-status" class="warning" role="status" hidden></p></div>
        <details class="intake-upload"><summary>自动获取失败？上传本地视频</summary>
          <div class="field case-file-field"><label for="case-video-file">选择与来源链接对应的视频文件</label>
            <input id="case-video-file" type="file" accept=".mp4,.mov,.m4v,.webm,video/mp4,video/quicktime,video/webm">
            <p id="case-file-selected" class="field-hint" role="status">MP4、MOV、M4V、WebM · 最大 256 MB</p>
            <p class="field-hint">每个文件对应一个来源链接。最长 10 分钟、最高 4K；上传仍须确认来源与使用权限。</p></div></details>
        <div id="case-form-error" class="form-error" role="alert"></div><div id="case-result" role="status"></div>
        <button class="btn btn-primary btn-wide" type="submit">开始解析</button>
        <p class="governance-copy">批准后的案例只用于内部参考，不会获得原视频素材使用权。</p>
      </form></section></main>`);
    bindCommonActions();
    const form = app.querySelector("#case-url-form"), input = form.querySelector("#case-url");
    const fileInput = form.querySelector("#case-video-file"), button = form.querySelector('[type="submit"]');
    const errorBox = form.querySelector("#case-form-error"), result = form.querySelector("#case-result");
    let busy=false, retryTask=null, reviewCase=null, reviewCaseContext=null, requestId=crypto.randomUUID(), requestText=null;
    let uploaded=null, uploadedFile=null, uploadedText=null, reviewCanReview=false;
    const update=()=>{form.querySelector("#source-detection").textContent=detectCaseSourceInput(input.value).label;};
    input.addEventListener("input",update);
    fileInput.addEventListener("change",()=>{form.querySelector("#case-file-selected").textContent=fileInput.files[0]?.name||"未选择文件";});
    form.querySelector("[data-paste]").addEventListener("click",async()=>{
      try{input.value=await navigator.clipboard.readText();update();}catch{showToast("请长按输入框或使用键盘粘贴链接。");}
    });
    api("/api/capabilities").then(data=>{
      if(!form.isConnected)return;
      const notice=form.querySelector("#case-acquisition-status"), warning=caseAcquisitionWarning(data.case_analysis?.source_acquisition);
      notice.textContent=warning;notice.hidden=!warning;
      if(data.case_analysis?.upload_required)form.querySelector("details").open=true;
    }).catch(()=>{});
    if(params.get("retry_task")){
      try{
        const {task}=await api(`/api/tasks/${encodeURIComponent(params.get("retry_task"))}`);
        if(!form.isConnected)return;
        const destination=caseTaskResumeDestination(task);
        if(destination)return navigate(destination,true);
        retryTask=task;input.value=task.payload?.source_url||"";
        result.innerHTML='<p class="warning">恢复原任务会复用已完成步骤；上传替代文件会建立有独立来源记录的新尝试。</p>';
      }catch(error){errorBox.textContent=error.message;errorBox.classList.add("visible");}
    }
    if(params.get("reanalyze_case")){
      reviewCase=params.get("reanalyze_case");
      const detail=await api(`/api/cases/${encodeURIComponent(reviewCase)}${params.get("attempt_id")?`?attempt_id=${encodeURIComponent(params.get("attempt_id"))}`:""}`);
      if(!form.isConnected)return;
      input.value=detail.source_url||"";
      reviewCanReview=Boolean(detail.permissions?.can_review && detail.review?.can_review && detail.approval_context);
      reviewCaseContext=detail.approval_context?.token;
      result.innerHTML='<p class="warning">重新分析需要说明原因，原有审核记录会保留。</p>';
    }
    if(params.get("source"))input.value=params.get("source");
    update();
    form.addEventListener("submit",async event=>{
      event.preventDefault();if(busy)return;errorBox.classList.remove("visible");
      if(!input.value.trim()){errorBox.textContent="请粘贴抖音分享内容或视频链接。";errorBox.classList.add("visible");return;}
      const file=fileInput.files[0];
      if(file&&extractCaseSourceUrls(input.value).length!==1){errorBox.textContent="本地视频只能对应一个来源链接。";errorBox.classList.add("visible");return;}
      busy=true;button.disabled=true;input.disabled=true;fileInput.disabled=true;
      const controller=new AbortController();stopUpload=()=>controller.abort();
      try{
        const originalText=input.value.trim();
        if(requestText!==originalText){requestText=originalText;requestId=crypto.randomUUID();}
        let text=originalText;
        if(file&&(file!==uploadedFile||originalText!==uploadedText)){
          const invalid=validateCaseFile(file);if(invalid)throw new Error(invalid);
          result.innerHTML="<p>正在上传并检查视频，请保持页面打开。上传完成后任务可以恢复查看。</p>";
          uploaded=await uploadCaseFile(api,{file,sourceUrl:text,signal:controller.signal});
          uploadedFile=file;uploadedText=originalText;requestId=crypto.randomUUID();
        }
        if(controller.signal.aborted||!form.isConnected)return;
        if(reviewCase){
          const decision=await openModal({title:"重新分析这个案例？",description:"新尝试保留独立记录。",confirmLabel:"重新分析",reasonRequired:true,reasonLabel:"重新分析原因"});
          if(!decision.confirmed)return;
          if(reviewCanReview)await api(`/api/cases/${encodeURIComponent(reviewCase)}/review`,{method:"POST",body:JSON.stringify({review_context:reviewCaseContext,decision:"reanalyze",reason:decision.reason,...(file?{source_upload_id:uploaded.upload_id}:{})})});
          else await api("/api/cases/analyze",{method:"POST",body:JSON.stringify({url:input.value.trim(),reanalyze:true,reason:decision.reason,...(file?{source_upload_id:uploaded.upload_id}:{})})});
        }else if(retryTask){
          if(file)await api("/api/cases/analyze",{method:"POST",body:JSON.stringify({url:uploaded.canonical_url,source_upload_id:uploaded.upload_id,reanalyze:true})});
          else await api(`/api/tasks/${encodeURIComponent(retryTask.task_id)}/retry`,{method:"POST"});
        }
        result.innerHTML="<p>正在读取链接并建立可恢复的解析记录…</p>";
        const group=await api("/api/case-intake/groups",{method:"POST",body:JSON.stringify({
          text:file?uploaded.canonical_url:text,client_request_id:requestId,...(file&&!retryTask&&!reviewCase?{source_upload_id:uploaded.upload_id}:{})})});
        if(form.isConnected)navigate(`/case-intake/${encodeURIComponent(group.group_id)}`);
      }catch(error){
        if(reviewCase && reviewCanReview && error.name!=="AbortError") {
          const pending=await api(`/api/review-commands/case/${encodeURIComponent(reviewCase)}`).catch(()=>({operations:[]}));
          if(pending.operations?.length && form.isConnected) {
            showToast("审核提交尚未完成，请在投稿详情继续原操作。");navigate(`/cases/${encodeURIComponent(reviewCase)}`);return;
          }
        }
        if(form.isConnected&&error.name!=="AbortError"){errorBox.textContent=error.detail?.message||error.message;errorBox.classList.add("visible");}
      }finally{busy=false;button.disabled=false;input.disabled=false;fileInput.disabled=false;stopUpload=null;}
    });
  }

  async function renderIntakeGroup(groupId, singleCaseId=null){
    dispose();skeletonPage("案例解析中");
    let cancelled=false,timer=null,filter="all",last=null,submitting=false,revision=null;
    const drafts=new Map(),editing=new Set();
    stopPolling=()=>{cancelled=true;clearTimeout(timer);};
    const load=async()=>{
      if(!singleCaseId)return api(`/api/case-intake/groups/${encodeURIComponent(groupId)}`);
      const [detail,classification]=await Promise.all([api(`/api/cases/${encodeURIComponent(singleCaseId)}${location.search}`),api(`/api/cases/${encodeURIComponent(singleCaseId)}/classification${location.search}`)]);
      return {group_id:null,items:[{position:0,state:"linked",case_id:singleCaseId,source_url:detail.source_url,case:detail,classification}]};
    };
    const save=async(item,draft)=>api(`/api/cases/${encodeURIComponent(item.case_id)}/classification`,{
      method:"POST",body:JSON.stringify({attempt_id:item.classification.attempt_id,industry:draft.industry===UNCERTAIN_INDUSTRY?null:draft.industry,profile:draft.profile,
        candidate_sha256:item.classification.candidate_sha256,expected_confirmation_sha256:item.classification.confirmation_sha256})});
    const refresh=async()=>{
      try{
        const group=await load();if(cancelled)return;const next=JSON.stringify(group);last=group;if(next!==revision){revision=next;draw();}
        if(intakeCounts(group.items).analyzing)timer=setTimeout(refresh,3000);
      }catch(error){if(!cancelled)renderLoadError("解析记录暂时无法读取",error);}
    };
    const draw=()=>{
      const counts=intakeCounts(last.items);
      const batchMode=counts.total>1;
      const rows=last.items.filter(item=>filter==="all"||intakeItemState(item)===filter);
      const cards=rows.map(item=>{
        const state=intakeItemState(item),rec=item.classification?.suggestion,human=item.classification?.human;
        const draft=drafts.get(item.position)||classificationDraft(item.classification||{});
        if(rec)drafts.set(item.position,draft);
        const title=item.case?.title||(item.case_id?`视频 ${item.case_id}`:"未识别的视频链接");
        const duration=item.case?.duration_seconds==null?"时长待解析":`${Math.round(item.case.duration_seconds)} 秒`;
        let body="";
        if(state==="submitted")body+="<p>本次投稿已记录，未建立新的解析任务。可在我的投稿中查看；有正式共享结果时，可从共享案例库浏览。</p>";
        else if(state==="input_duplicate")body+="<p>当前输入中重复的视频，已合并处理，不会重复获取或分析。</p>";
        else if(state==="approved")body+=`<p>该视频已经添加过</p><a class="btn btn-secondary" href="/cases/${item.case_id}" data-route>查看已有案例</a>`;
        else if(rec&&state!=="failed"){
          if(state==="confirmed")body+=`<div class="intake-confirmed"><p><strong>${confirmedClassificationLabel(human)}</strong></p><p>${escapeHtml(human.industry||"行业暂不确定")} · ${profileLabels[human.profile]}</p><small>操作人 ${escapeHtml(String(human.confirmed_by_phone).replace(/^(\d{3})\d+(\d{4})$/,"$1****$2"))} · ${escapeHtml(formatConsoleTime(human.confirmed_at))}</small></div>`;
          else body+=`<div class="intake-recommendation"><p><strong>系统推荐</strong> ${escapeHtml(rec.industry||"行业暂不确定")} · ${profileLabels[rec.observed_source_profile]||"暂不确定"}</p><p>${escapeHtml(rec.profile_reason)}</p></div>`;
          body+=`<details class="intake-evidence"><summary>查看推荐依据与来源</summary><p>系统建议：${escapeHtml(rec.industry||"行业暂不确定")} · ${profileLabels[rec.observed_source_profile]||"暂不确定"}</p><p>${escapeHtml(rec.industry_reason)}</p><p>${escapeHtml(rec.profile_reason)}</p>${rec.shot_refs?.length?`<p>对应画面：${escapeHtml(rec.shot_refs.join("、"))}</p>`:""}<p>${escapeHtml(item.source_url||"")}</p></details>`;
          if(item.classification.can_confirm&&(state!=="confirmed"||editing.has(item.position)))body+=`<form data-classify="${item.position}" class="intake-classify-form"><div class="intake-selects">
            <div class="field"><label for="intake-industry-${item.position}">所属行业</label><select id="intake-industry-${item.position}" data-industry>${industryOptions(draft.industry,{uncertainValue:UNCERTAIN_INDUSTRY})}</select><input data-custom maxlength="30" aria-label="自定义行业名称" value="${escapeHtml(CASE_INDUSTRIES.includes(draft.industry)||draft.industry===UNCERTAIN_INDUSTRY?"":draft.industry)}" ${draft.industry&&draft.industry!==UNCERTAIN_INDUSTRY&&!CASE_INDUSTRIES.includes(draft.industry)?"":"hidden disabled"}></div>
            <div class="field"><label for="intake-profile-${item.position}">创作参考方向</label><select id="intake-profile-${item.position}" data-profile><option value="">请选择</option>${Object.entries(profileLabels).map(([v,label])=>`<option value="${v}" ${draft.profile===v?"selected":""}>${label}</option>`).join("")}</select></div></div>
            ${batchMode&&state==="needs_confirmation"?`<label class="intake-check"><input type="checkbox" data-checked ${draft.checked?"checked":""} ${classificationSubmittable(draft,{batch:true})?"":"disabled"}>已逐条检查，加入批量确认</label>`:""}
            <button class="btn ${state==="confirmed"?"btn-secondary":"btn-primary"}" type="submit">${state==="confirmed"?"保存分类修改":"确认分类"}</button>${state==="confirmed"?'<button class="btn btn-text" type="button" data-cancel-edit>取消修改</button>':""}</form>`;
          if(state==="confirmed")body+=`<div class="intake-card-actions"><a class="btn btn-primary" href="/cases/${item.case_id}" data-route>查看投稿详情</a>${!editing.has(item.position)&&item.classification.can_confirm?`<button class="btn btn-text" type="button" data-edit-classify="${item.position}">修改分类</button>`:""}</div>`;
          else if(!item.classification.can_confirm)body+=`<a class="btn btn-secondary" href="/cases/${item.case_id}" data-route>查看投稿详情</a>`;
        }else if(state==="failed"){
          body+=`<p class="warning">${escapeHtml(item.message||item.task?.error_message||"解析未完成，请检查来源后重试。")}</p>`;
          if(item.task)body+=`<div class="intake-card-actions"><button class="btn btn-secondary" type="button" data-retry="${item.task.task_id}">${item.task.error_code==="SOURCE_ACQUISITION_FAILED"?"重试获取":"重试失败阶段"}</button><a class="btn btn-secondary" href="/cases/new?retry_task=${encodeURIComponent(item.task.task_id)}" data-route>上传本地视频</a><a class="inline-link" href="/tasks/${encodeURIComponent(item.task.task_id)}" data-route>查看任务详情</a></div>`;
          else body+=`<a class="btn btn-secondary" href="/cases/new?source=${encodeURIComponent(item.canonical_url||item.source_url||"")}" data-route>检查链接 / 上传本地视频</a>`;
        }else body+='<p class="field-hint">状态来自后台任务；按队列顺序处理，不会同时启动多个高负载模型任务。</p>';
        return `<article class="panel intake-result-card" data-intake-state="${state}"><div class="intake-card-heading">${item.case?.cover_url?`<img class="intake-cover" src="${escapeHtml(item.case.cover_url)}" alt="视频来源封面" loading="lazy">`:'<div class="intake-cover-placeholder" aria-label="没有可用封面">视频</div>'}<div><h2>${escapeHtml(title)}</h2><p>${item.case_id?"抖音":"来源待核对"} · ${duration}</p><span class="status-pill">${intakeStage(item)}</span></div></div>${body}</article>`;
      }).join("");
      app.innerHTML=shell("案例解析",`<main class="page page-standard intake-results-page">${pageHeading("",counts.analyzing?"案例解析中":counts.needs_confirmation?"请确认系统推荐的分类":counts.confirmed?(counts.total===1?confirmedClassificationLabel(last.items.find(item=>intakeItemState(item)==="confirmed").classification.human):"分类已确认"):"案例解析结果",counts.analyzing?"正在分析视频内容":counts.needs_confirmation?"分类核对后，由指定审核人决定是否收录。":counts.confirmed?"分类结果已保存，等待指定审核人处理。":"查看解析结果，失败项目可单独重试。")}
        ${intakeSteps(counts.analyzing?1:2)}<section class="intake-overview panel"><div class="intake-counts">${[["本批总数",counts.total],["分析中",counts.analyzing],["待确认",counts.needs_confirmation],["已确认",counts.confirmed],["失败",counts.failed],["已入库",counts.approved],...(counts.submitted?[["投稿已记录",counts.submitted]]:[]),...(counts.completed?[["任务已结束",counts.completed]]:[])].map(([label,n])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join("")}</div><p>${counts.analyzing ? "可以离开当前页面，解析任务会继续进行。" : "本批处理结果已保存，可从我的投稿继续查看。"}</p>${counts.duplicates?`<p>另有 ${counts.duplicates} 条输入内重复链接，已合并处理。</p>`:""}</section>
        <div class="intake-toolbar"><div class="filter-row">${[["all","全部"],["needs_confirmation","待确认"],["confirmed","已确认"],["failed","失败"]].map(([value,label])=>`<button class="filter-chip ${filter===value?"active":""}" type="button" data-intake-filter="${value}">${label}</button>`).join("")}</div><button class="btn btn-secondary" type="button" data-confirm-checked hidden disabled>批量确认已检查的分类</button></div>
        <p class="field-hint">分类确认不会批准案例入库，也不会授予创作可用资格；未确定分类请逐条确认。</p><div class="intake-result-grid">${cards||'<section class="panel"><p>此分类下暂无视频。</p></section>'}</div></main>`);
      bindCommonActions();
      const updateBatchButton=()=>{const button=app.querySelector("[data-confirm-checked]"),ready=batchConfirmableItems(last.items,drafts).length;button.hidden=!batchMode||!ready;button.disabled=submitting||!ready;};
      updateBatchButton();
      app.querySelectorAll("[data-intake-filter]").forEach(b=>b.addEventListener("click",()=>{filter=b.dataset.intakeFilter;draw();}));
      app.querySelectorAll("[data-edit-classify]").forEach(b=>b.addEventListener("click",()=>{editing.add(Number(b.dataset.editClassify));draw();}));
      app.querySelectorAll("[data-classify]").forEach(form=>{
        const position=Number(form.dataset.classify),draft=drafts.get(position),industry=form.querySelector("[data-industry]"),custom=form.querySelector("[data-custom]");
        const item=last.items.find(i=>i.position===position),checkbox=form.querySelector("[data-checked]");
        const capture=()=>{syncCustomIndustry(industry,custom);draft.industry=industryValue(industry,custom);draft.profile=form.querySelector("[data-profile]").value;
          if(checkbox){checkbox.disabled=!classificationSubmittable(draft,{batch:true});if(checkbox.disabled)checkbox.checked=false;draft.checked=checkbox.checked;}
          if(!draft.reminded&&classificationDiffers(draft,item.classification.suggestion)){draft.reminded=true;showToast("你的选择与系统建议不同，确认后将采用你的选择。");}
          updateBatchButton();};
        form.addEventListener("change",capture);form.addEventListener("input",capture);
        form.querySelector("[data-cancel-edit]")?.addEventListener("click",()=>{editing.delete(position);drafts.delete(position);draw();});
        form.addEventListener("submit",async event=>{
          event.preventDefault();capture();if(submitting)return;
          if(!classificationSubmittable(draft))return showToast("请选择行业和视频结构；无法判断时可以选择暂不确定。");
          submitting=true;clearTimeout(timer);form.querySelector("button").disabled=true;
          try{await save(item,draft);editing.delete(position);drafts.delete(position);revision=null;showToast(`${confirmedClassificationLabel(draft)}，可以查看投稿详情。`);}
          catch(error){showToast(error.detail?.next_action||error.message);form.querySelector("button").disabled=false;}
          finally{submitting=false;revision=null;await refresh();}
        });
      });
      app.querySelector("[data-confirm-checked]").addEventListener("click",async event=>{
        if(submitting)return;
        const checked=batchConfirmableItems(last.items,drafts);
        if(!checked.length)return showToast("请先逐条检查并勾选分类。");
        submitting=true;clearTimeout(timer);event.currentTarget.disabled=true;let saved=0;
        try{for(const item of checked){await save(item,drafts.get(item.position));drafts.delete(item.position);saved++;}showToast(`已确认 ${saved} 条分类，等待指定审核人处理。`);}
        catch(error){showToast(`已确认 ${saved} 条；${error.detail?.next_action||error.message}`);}
        finally{submitting=false;revision=null;await refresh();}
      });
      app.querySelectorAll("[data-retry]").forEach(b=>b.addEventListener("click",async()=>{
        if(submitting)return;submitting=true;clearTimeout(timer);b.disabled=true;
        try{await api(`/api/tasks/${encodeURIComponent(b.dataset.retry)}/retry`,{method:"POST"});}
        catch(error){showToast(error.detail?.next_action||error.message);b.disabled=false;}
        finally{submitting=false;revision=null;await refresh();}
      }));
    };
    await refresh();
  }

  async function renderCaseDetail(caseId) {
    dispose(); skeletonPage("案例审核");
    const version=renderVersion;
    const pending=await api(`/api/review-commands/case/${encodeURIComponent(caseId)}`).catch(()=>({operations:[], unavailable:true}));
    try {
      const params=new URLSearchParams(location.search);
      const detail = await api(params.get("shared")==="1" ? `/api/case-library/${encodeURIComponent(caseId)}` : `/api/cases/${encodeURIComponent(caseId)}${params.get("attempt_id")?`?attempt_id=${encodeURIComponent(params.get("attempt_id"))}`:""}`);
      if(version!==renderVersion)return;
      const back=`<a class="list-back" href="${escapeHtml(caseReturnPath())}" data-route>‹ 返回案例列表</a>`;
      if(detail.visibility==="shared"){
        const duration=formatCaseDuration(detail.duration_seconds);
        app.innerHTML=shell("案例",`<main class="page page-standard brand-list-page shared-case-detail">${back}${pageHeading("",detail.title,"已获准共享的创作结构参考")}
          <section class="shared-case-surface"><div class="case-card-cover shared-case-cover">${detail.cover_url?`<img src="${escapeHtml(detail.cover_url)}" alt="" decoding="async">`:""}<span class="case-cover-placeholder" ${detail.cover_url?"hidden":""}><small>暂无封面</small></span></div>
          <div class="shared-case-copy"><p class="case-card-tags"><span>${escapeHtml(detail.industry || "行业待确认")}</span><span>视频类型暂未标注</span>${duration?`<span>${duration}</span>`:""}</p><h2>结构参考</h2><p>${escapeHtml(detail.structure_summary || "暂未补充结构参考。")}</p><p class="shared-case-rights">案例用于结构参考。原视频素材使用须另外确认授权。</p></div></section></main>`);
        bindCommonActions();bindCardCovers();return;
      }
      app.innerHTML = shell(detail.permissions?.can_review ? "案例审核" : "我的投稿", caseReviewContent(detail, statusPill,
        {operations:pending.operations, recoveryUnavailable:pending.unavailable}).replace('<a class="back-link" href="/cases" data-route>← 案例</a>', "").replace("</main>",`${publicationPanel(detail)}</main>`));
      app.querySelector("main")?.insertAdjacentHTML("afterbegin",back);
      mountRecovery(app,api,caseRecovery(detail,pending.operations),async result=>{
        if(result?.task) return navigate(`/tasks/${encodeURIComponent(result.task.task_id)}`);
        if(result?.decision==='approved') showToast(shareResultMessage(result));
        await renderCaseDetail(caseId);
        app.querySelector('.case-result-panel')?.focus({preventScroll:true});
      },{container:app.querySelector('[data-case-recovery-slot]')});
      app.querySelector('[data-refresh-case-result]')?.addEventListener('click',()=>renderCaseDetail(caseId));
      stopMediaPreview = bindCaseMediaPreview(app);
      bindCommonActions();
      bindPublication(detail,caseId);
      bindCaseReviewNavigation(app);
      bindEvidenceWorkspace(app,detail,{api,reload:()=>renderCaseDetail(caseId),toast:showToast});
      if(detail.excel_notes_available && detail.review?.attempt_id){
        const notes=document.createElement('section');notes.className='card excel-private-notes';notes.setAttribute('aria-label','投稿人补充说明');
        notes.textContent='正在核对当前投稿人的未核说明…';app.querySelector('main')?.append(notes);
        api(`/api/cases/${encodeURIComponent(caseId)}/attempts/${encodeURIComponent(detail.review.attempt_id)}/excel-notes`).then(value=>{
          if(version===renderVersion)notes.innerHTML=nativeNotesMarkup(value,escapeHtml);
        }).catch(()=>{if(version===renderVersion)notes.textContent='投稿补充说明暂时无法核对，请以当前原始媒体证据为准。';});
      }
      document.querySelector("[data-profile-annotation]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const decision = await openModal({
          title: "修改结构标签",
          description: "标签保存在独立补充记录中，不改变已批准案例或创作可用范围。请选择你观察到的结构类型。",
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
          title: "修改行业标签",
          description: "行业标签保存在独立补充记录中，不改变已入库案例。",
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
      let sharePreviewDirty = false;
      app.querySelector('#case-video-type')?.addEventListener('change',event=>{
        const field=app.querySelector('[data-other-type-field]');if(field)field.hidden=event.target.value!=='other';
      });
      const previewSave=app.querySelector('[data-save-share-preview]');
      const previewFeedback=app.querySelector('[data-share-preview-feedback]');
      const previewPanel=app.querySelector('.case-share-preview');
      const previewEditor=app.querySelector('.share-preview-editor');
      let previewApprovalDisabled=app.querySelector('[data-review-action="approve"]')?.disabled;
      app.querySelectorAll('#share-preview-title, #share-preview-summary').forEach(input=>input.addEventListener('input',()=>{
        sharePreviewDirty=true;previewSave.disabled=false;previewPanel.dataset.previewState='dirty';
        app.querySelector('[data-review-action="approve"]').disabled=true;
        previewFeedback.textContent='修改尚未核对，请保存后再批准。';
      }));
      app.querySelector('[data-cancel-share-preview]')?.addEventListener('click',()=>{
        if(!detail.share_preview)return;
        const display=detail.share_preview.preview.display;
        app.querySelector('#share-preview-title').value=display.title;
        app.querySelector('#share-preview-summary').value=display.structure_summary;
        sharePreviewDirty=false;previewSave.disabled=true;previewEditor.open=false;
        previewEditor.querySelector('summary').focus();
        previewPanel.dataset.previewState='ready';
        app.querySelector('[data-review-action="approve"]').disabled=previewApprovalDisabled;
        previewFeedback.textContent=detail.share_preview.blocker?.message || '已保留当前预览，未采用本次修改。';
      });
      previewSave?.addEventListener('click',async()=>{
        previewSave.disabled=true;
        try {
          const updated=await api(`/api/cases/${encodeURIComponent(caseId)}/share-preview`,{method:'POST',body:JSON.stringify({
            title:app.querySelector('#share-preview-title').value,structure_summary:app.querySelector('#share-preview-summary').value})});
          detail.share_preview=updated.share_preview;detail.approval_context=updated.approval_context;
          sharePreviewDirty=false;previewSave.disabled=true;previewEditor.open=false;
          previewEditor.querySelector('summary').focus();
          previewPanel.dataset.previewState='ready';
          app.querySelector('[data-share-preview-card]').innerHTML=sharePreviewCard(updated.share_preview);
          app.querySelector('#share-preview-title').value=updated.share_preview.preview.display.title;
          app.querySelector('#share-preview-summary').value=updated.share_preview.preview.display.structure_summary;
          const approve=app.querySelector('[data-review-action="approve"]');
          approve.disabled=!reviewWorkspace(detail)?.can_approve;
          previewApprovalDisabled=approve.disabled;
          approve.textContent=updated.share_preview.mode==='approve_and_share'?'收录并共享':'批准入库';
          previewFeedback.textContent=updated.share_preview.blocker?.message || '展示内容已更新，最终确认将采用当前预览。';
        } catch(error) {previewPanel.dataset.previewState='error';previewFeedback.textContent=error.message;}
        finally {previewSave.disabled=!sharePreviewDirty;}
      });
      document.querySelectorAll("[data-review-action]").forEach((button) => button.addEventListener("click", async () => {
        if (button.dataset.reviewAction === "reanalyze") {
          return navigate(`/cases/new?reanalyze_case=${encodeURIComponent(caseId)}`);
        }
        const action = button.dataset.reviewAction;
        let reason = "";
        let profileHint = null;
        let evidenceReview = null;
        let qualityDecision = null;
        let sharingDecision = null;
        let typeConfirmation = null;
        if (action === "approve") {
          if(sharePreviewDirty){showToast('请先核对修改后的展示预览。');return;}
          const workspace=reviewWorkspace(detail);
          if(workspace){
            if(!workspace.can_approve){showToast(workspace.message || "仍有待处理问题，请先保存并完成校验。");return;}
            const checks=[...app.querySelectorAll('[data-explicit-evidence]')];
            const missing=checks.find(e=>!e.checked);
            if(missing){showToast("请明确处理标出的疑点，有误时请先修订。");missing.focus();return;}
            evidenceReview={schema_version:"case-evidence-final-review-v2.0",confirmation_mode:"final_bulk_keep",
              scope_sha256:workspace.scope.scope_sha256,explicit_keep_ids:checks.map(e=>e.dataset.explicitEvidence)};
          } else if (detail.evidence_review?.required) {
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
          const recovery = detail.review?.approval_recovery_required === true;
          const summary=workspace?.scope?.summary;
          if(detail.video_type_context && !recovery){
            try{
              typeConfirmation=makeTypeConfirmation(detail.video_type_context,{typeId:app.querySelector('#case-video-type').value,
                otherNote:app.querySelector('#case-other-type').value,reason:app.querySelector('#case-type-reason').value});
              button.disabled=true;
              const updated=await api(`/api/cases/${encodeURIComponent(caseId)}/share-preview`,{method:'POST',body:JSON.stringify({
                title:detail.share_preview.preview.display.title,structure_summary:detail.share_preview.preview.display.structure_summary,
                type_confirmation:typeConfirmation})});
              detail.share_preview=updated.share_preview;detail.approval_context=updated.approval_context;
              app.querySelector('[data-share-preview-card]').innerHTML=sharePreviewCard(updated.share_preview);
            }catch(error){showToast(error.message);button.disabled=false;return;}
          }
          const sharing=shareConfirmation(detail.share_preview);
          if(detail.approval_context?.version==='human-review-command-v1.2' && !sharing){showToast('安全展示预览尚未核对，请恢复来源或重新分析。');return;}
          const decision = await openModal({
            title: recovery ? "完成上次批准？" : sharing?.title || "批准这个案例？",
            description: recovery
              ? "系统只会完成上次未保存完的批准，不会重复审核。批准不会改变原视频素材使用权。"
              : `${summary ? `保留原识别 ${summary.keep_original} 项，采用人工口播修正 ${summary.corrected_narration} 项，调整分镜 ${summary.adjusted_boundaries} 项，未处理问题 ${summary.blocked} 项。` : ""}${sharing?.description || "请确认你已核对案例来源、视频内容和分析结果，并认为本案例具有值得借鉴的创作参考价值。批准不会授予原视频素材使用权。"}`,
            confirmLabel: recovery ? "完成批准" : sharing?.confirmLabel || "确认符合收录标准并批准入库",
          });
          if (!decision.confirmed) {button.disabled=false;return;}
          qualityDecision = { ...detail.quality_context, decision: "suitable", origin: "human_final_confirmation" };
          sharingDecision = sharing?.decision || null;
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
          const result = await api(`/api/cases/${encodeURIComponent(caseId)}/review`, { method: "POST", body: JSON.stringify({ review_context: detail.approval_context.token, decision: action, reason, operator_profile_hint: profileHint, evidence_review: evidenceReview, quality_decision: qualityDecision, sharing_decision:sharingDecision, type_confirmation:typeConfirmation }) });
          if (action === "approve") { showToast(shareResultMessage(result)); return renderCaseDetail(caseId); }
          if (action === "reanalyze") { showToast("已退回重新分析"); return navigate(`/tasks/${result.task.task_id}`); }
          showToast("已记录为不收录"); navigate(caseReturnPath() === "/cases" ? "/cases?view=review" : caseReturnPath());
        } catch (error) {
          if (error.status >= 500) {
            showToast(error.detail?.code==='CASE_SHARE_PUBLICATION_PENDING'
              ? '案例已收录，共享暂未完成。可在审核结果中重试共享。'
              : "提交结果暂未确认，请查看已保存状态后继续。");
            return renderCaseDetail(caseId);
          }
          showToast([error.message, error.detail?.next_action].filter(Boolean).join(" "));
          document.querySelectorAll("[data-review-action]").forEach((item) => { item.disabled = false; });
        }
      }));
    } catch (error) { error.status===404 ? renderCaseRestricted() : renderLoadError("案例暂时无法读取", error); }
  }

  async function renderTaskDetail(taskId) {
    dispose(); skeletonPage("任务进度");
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
      const revision = payload.task.payload?.evidence_revision;
      app.innerHTML = shell("任务进度", `<main class="page task-detail-page">${pageHeading("任务进度", revision ? "修订校验" : "案例分析", revision ? "修改已经保存。校验通过后，返回原投稿继续审核。" : "进度来自实际分析步骤，离开页面后仍会继续。")}
        <div data-live-progress>${progressPanel(payload.task, { boundaryReview: payload.boundary_review })}</div>
        ${boundaryReviewPanel(payload.boundary_review)}</main>`);
      bindCommonActions();
      app.querySelector("[data-live-progress]").addEventListener("click", async (event) => {
        const button = event.target.closest("[data-retry-revision]");
        if (!button || button.disabled) return;
        button.disabled = true;
        try {
          await api(`/api/tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" });
          showToast("已继续原修订校验任务");
          return renderTaskDetail(taskId);
        } catch (error) {
          button.disabled = false;
          showToast([error.message, error.detail?.next_action].filter(Boolean).join(" "));
        }
      });
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

  return { renderCases, renderCaseNew, renderCaseDetail, renderTaskDetail, renderIntakeGroup, dispose };
}
