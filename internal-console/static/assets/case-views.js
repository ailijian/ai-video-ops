import { boundaryReviewPanel, caseCard, caseReviewContent, escapeHtml, progressPanel } from "./case-components.js?v=smart-intake-1";
import { bindCaseMediaPreview } from "./case-media-preview.mjs?v=case-media-fit-1";
import { caseTaskResumeDestination } from "./case-submit-state.mjs?v=mobile-reliability-2";
import { startTaskPolling } from "./task-progress.js?v=mobile-reliability-1";
import { detectCaseSourceInput, extractCaseSourceUrls } from "./case-source-detection.mjs?v=case-batch-1";
import { uploadCaseFile, validateCaseFile } from "./case-file-upload.mjs?v=source-upload-ui-2";
import { intakeCounts, intakeItemState, intakeStage, UNCERTAIN_INDUSTRY, classificationDraft, classificationSubmittable, classificationDiffers, batchConfirmableItems, confirmedClassificationLabel } from "./case-batch-submit.mjs?v=smart-intake-1.1-r1";
import { CASE_INDUSTRIES, industryOptions, industryValue, syncCustomIndustry } from "./case-industry.mjs?v=industry-2";

export function caseAcquisitionWarning(acquisition, { hasFile = false, unavailable = false } = {}) {
  if (hasFile || (acquisition?.mode === "qiyun" && acquisition.configured)) return "";
  if (acquisition?.mode === "qiyun") return "奇云付费解析尚未连接。请上传视频，或联系管理员检查配置。";
  if (acquisition?.mode === "legacy_downloader") return "当前使用原有下载方式，未启用奇云付费解析。获取失败时可上传本地视频。";
  if (acquisition?.mode === "upload_only") return "当前无法自动获取视频，请上传本地视频。";
  return unavailable ? "暂时无法确认视频获取方式，请刷新页面后再提交。" : "";
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
      const [data, groups] = await Promise.all([api("/api/cases"), api("/api/case-intake/groups")]);
      const cases = data.cases;
      const content = cases.length ? `<div class="filter-row" role="group" aria-label="案例状态筛选">
          <button class="filter-chip active" data-filter="all" type="button">全部 ${cases.length}</button>
          <button class="filter-chip" data-filter="awaiting_review" type="button">待审核 ${cases.filter((item) => item.status === "awaiting_review").length}</button>
          <button class="filter-chip" data-filter="approved" type="button">已入库 ${cases.filter((item) => item.status === "approved").length}</button>
        </div><div class="case-list">${cases.map((item) => caseCard(item, statusPill)).join("")}</div>` :
        `<section class="state-panel empty-state"><h2>还没有案例</h2><p>添加一个抖音视频，分析完成后即可审核。</p></section>`;
      app.innerHTML = shell("案例", `<main class="page page-standard case-library-page">${pageHeading("", "案例", "浏览和审核团队已经分析的视频案例。", '<a class="btn btn-primary" href="/cases/new" data-route>+ 添加案例</a>')}${(groups.groups || []).length ? `<section class="intake-recent-groups" aria-label="最近解析批次">${groups.groups.slice(0, 5).map(g => `<a class="btn btn-secondary" href="/case-intake/${g.group_id}" data-route>恢复本批解析 · ${escapeHtml(new Date(g.created_at).toLocaleString("zh-CN"))}</a>`).join("")}</section>` : ""}${content}</main>`);
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
    let busy=false, retryTask=null, reviewCase=null, requestId=crypto.randomUUID(), requestText=null;
    let uploaded=null, uploadedFile=null, uploadedText=null;
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
      const detail=await api(`/api/cases/${encodeURIComponent(reviewCase)}`);
      if(!form.isConnected)return;
      input.value=detail.source_url||"";
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
          await api(`/api/cases/${encodeURIComponent(reviewCase)}/review`,{method:"POST",body:JSON.stringify({decision:"reanalyze",reason:decision.reason,...(file?{source_upload_id:uploaded.upload_id}:{})})});
        }else if(retryTask){
          if(file)await api("/api/cases/analyze",{method:"POST",body:JSON.stringify({url:uploaded.canonical_url,source_upload_id:uploaded.upload_id,reanalyze:true})});
          else await api(`/api/tasks/${encodeURIComponent(retryTask.task_id)}/retry`,{method:"POST"});
        }
        result.innerHTML="<p>正在读取链接并建立可恢复的解析记录…</p>";
        const group=await api("/api/case-intake/groups",{method:"POST",body:JSON.stringify({
          text:file?uploaded.canonical_url:text,client_request_id:requestId,...(file&&!retryTask&&!reviewCase?{source_upload_id:uploaded.upload_id}:{})})});
        if(form.isConnected)navigate(`/case-intake/${encodeURIComponent(group.group_id)}`);
      }catch(error){
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
      const [detail,classification]=await Promise.all([api(`/api/cases/${encodeURIComponent(singleCaseId)}`),api(`/api/cases/${encodeURIComponent(singleCaseId)}/classification`)]);
      return {group_id:null,items:[{position:0,state:"linked",case_id:singleCaseId,source_url:detail.source_url,case:detail,classification}]};
    };
    const save=async(item,draft)=>api(`/api/cases/${encodeURIComponent(item.case_id)}/classification`,{
      method:"POST",body:JSON.stringify({industry:draft.industry===UNCERTAIN_INDUSTRY?null:draft.industry,profile:draft.profile,
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
        if(state==="input_duplicate")body+="<p>当前输入中重复的视频，已合并处理，不会重复获取或分析。</p>";
        else if(state==="approved")body+=`<p>该视频已经添加过</p><a class="btn btn-secondary" href="/cases/${item.case_id}" data-route>查看已有案例</a>`;
        else if(rec&&state!=="failed"){
          if(state==="confirmed")body+=`<div class="intake-confirmed"><p><strong>${confirmedClassificationLabel(human)}</strong></p><p>${escapeHtml(human.industry||"行业暂不确定")} · ${profileLabels[human.profile]}</p><small>操作人 ${escapeHtml(String(human.confirmed_by_phone).replace(/^(\d{3})\d+(\d{4})$/,"$1****$2"))} · ${escapeHtml(new Date(human.confirmed_at).toLocaleString("zh-CN"))}</small></div>`;
          else body+=`<div class="intake-recommendation"><p><strong>系统推荐</strong> ${escapeHtml(rec.industry||"行业暂不确定")} · ${profileLabels[rec.observed_source_profile]||"暂不确定"}</p><p>${escapeHtml(rec.profile_reason)}</p></div>`;
          body+=`<details class="intake-evidence"><summary>查看推荐依据与来源</summary><p>系统建议：${escapeHtml(rec.industry||"行业暂不确定")} · ${profileLabels[rec.observed_source_profile]||"暂不确定"}</p><p>${escapeHtml(rec.industry_reason)}</p><p>${escapeHtml(rec.profile_reason)}</p>${rec.shot_refs?.length?`<p>对应画面：${escapeHtml(rec.shot_refs.join("、"))}</p>`:""}<p>${escapeHtml(item.source_url||"")}</p></details>`;
          if(item.classification.can_confirm&&(state!=="confirmed"||editing.has(item.position)))body+=`<form data-classify="${item.position}" class="intake-classify-form"><div class="intake-selects">
            <div class="field"><label for="intake-industry-${item.position}">所属行业</label><select id="intake-industry-${item.position}" data-industry>${industryOptions(draft.industry,{uncertainValue:UNCERTAIN_INDUSTRY})}</select><input data-custom maxlength="30" aria-label="自定义行业名称" value="${escapeHtml(CASE_INDUSTRIES.includes(draft.industry)||draft.industry===UNCERTAIN_INDUSTRY?"":draft.industry)}" ${draft.industry&&draft.industry!==UNCERTAIN_INDUSTRY&&!CASE_INDUSTRIES.includes(draft.industry)?"":"hidden disabled"}></div>
            <div class="field"><label for="intake-profile-${item.position}">视频结构</label><select id="intake-profile-${item.position}" data-profile><option value="">请选择</option>${Object.entries(profileLabels).map(([v,label])=>`<option value="${v}" ${draft.profile===v?"selected":""}>${label}</option>`).join("")}</select></div></div>
            ${batchMode&&state==="needs_confirmation"?`<label class="intake-check"><input type="checkbox" data-checked ${draft.checked?"checked":""} ${classificationSubmittable(draft,{batch:true})?"":"disabled"}>已逐条检查，加入批量确认</label>`:""}
            <button class="btn ${state==="confirmed"?"btn-secondary":"btn-primary"}" type="submit">${state==="confirmed"?"保存分类修改":"确认分类"}</button>${state==="confirmed"?'<button class="btn btn-text" type="button" data-cancel-edit>取消修改</button>':""}</form>`;
          if(state==="confirmed")body+=`<div class="intake-card-actions"><a class="btn btn-primary" href="/cases/${item.case_id}" data-route>继续案例审核</a>${!editing.has(item.position)&&item.classification.can_confirm?`<button class="btn btn-text" type="button" data-edit-classify="${item.position}">修改分类</button>`:""}</div>`;
          else if(!item.classification.can_confirm)body+=`<a class="btn btn-secondary" href="/cases/${item.case_id}" data-route>继续案例审核</a>`;
        }else if(state==="failed"){
          body+=`<p class="warning">${escapeHtml(item.message||item.task?.error_message||"解析未完成，请检查来源后重试。")}</p>`;
          if(item.task)body+=`<div class="intake-card-actions"><button class="btn btn-secondary" type="button" data-retry="${item.task.task_id}">${item.task.error_code==="SOURCE_ACQUISITION_FAILED"?"重试获取":"重试失败阶段"}</button><a class="btn btn-secondary" href="/cases/new?retry_task=${encodeURIComponent(item.task.task_id)}" data-route>上传本地视频</a><a class="inline-link" href="/tasks/${encodeURIComponent(item.task.task_id)}" data-route>查看任务详情</a></div>`;
          else body+=`<a class="btn btn-secondary" href="/cases/new?source=${encodeURIComponent(item.canonical_url||item.source_url||"")}" data-route>检查链接 / 上传本地视频</a>`;
        }else body+='<p class="field-hint">状态来自后台任务；按队列顺序处理，不会同时启动多个高负载模型任务。</p>';
        return `<article class="panel intake-result-card" data-intake-state="${state}"><div class="intake-card-heading">${item.case?.cover_url?`<img class="intake-cover" src="${escapeHtml(item.case.cover_url)}" alt="视频来源封面" loading="lazy">`:'<div class="intake-cover-placeholder" aria-label="没有可用封面">视频</div>'}<div><h2>${escapeHtml(title)}</h2><p>${item.case_id?"抖音":"来源待核对"} · ${duration}</p><span class="status-pill">${intakeStage(item)}</span></div></div>${body}</article>`;
      }).join("");
      app.innerHTML=shell("案例解析",`<main class="page page-standard intake-results-page">${pageHeading("",counts.analyzing?"案例解析中":counts.needs_confirmation?"请确认系统推荐的分类":counts.confirmed?(counts.total===1?confirmedClassificationLabel(last.items.find(item=>intakeItemState(item)==="confirmed").classification.human):"分类已确认"):"案例解析结果",counts.analyzing?"正在分析视频内容":counts.needs_confirmation?"分类确认后，继续逐条审核案例。":counts.confirmed?"分类结果已保存，继续完成案例审核。":"查看解析结果，失败项目可单独重试。")}
        ${intakeSteps(counts.analyzing?1:2)}<section class="intake-overview panel"><div class="intake-counts">${[["本批总数",counts.total],["分析中",counts.analyzing],["待确认",counts.needs_confirmation],["已确认",counts.confirmed],["失败",counts.failed],["已入库",counts.approved],...(counts.completed?[["任务已结束",counts.completed]]:[])].map(([label,n])=>`<div><strong>${n}</strong><span>${label}</span></div>`).join("")}</div><p>可以离开当前页面，解析任务会继续进行。</p>${counts.duplicates?`<p>另有 ${counts.duplicates} 条输入内重复链接，已合并处理。</p>`:""}</section>
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
          try{await save(item,draft);editing.delete(position);drafts.delete(position);revision=null;showToast(`${confirmedClassificationLabel(draft)}，可以继续案例审核。`);}
          catch(error){showToast(error.detail?.next_action||error.message);form.querySelector("button").disabled=false;}
          finally{submitting=false;revision=null;await refresh();}
        });
      });
      app.querySelector("[data-confirm-checked]").addEventListener("click",async event=>{
        if(submitting)return;
        const checked=batchConfirmableItems(last.items,drafts);
        if(!checked.length)return showToast("请先逐条检查并勾选分类。");
        submitting=true;clearTimeout(timer);event.currentTarget.disabled=true;let saved=0;
        try{for(const item of checked){await save(item,drafts.get(item.position));drafts.delete(item.position);saved++;}showToast(`已确认 ${saved} 条分类，可以继续逐条审核案例。`);}
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
    try {
      const detail = await api(`/api/cases/${encodeURIComponent(caseId)}`);
      app.innerHTML = shell("案例审核", caseReviewContent(detail, statusPill));
      stopMediaPreview = bindCaseMediaPreview(app);
      bindCommonActions();
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
          if (action === "approve") { showToast("已加入正式案例库"); return renderCaseDetail(caseId); }
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

  return { renderCases, renderCaseNew, renderCaseDetail, renderTaskDetail, renderIntakeGroup, dispose };
}
