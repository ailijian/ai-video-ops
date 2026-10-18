// Human evidence editor. Draft DOM values have no Authority until a formal save.
export function reviewWorkspace(detail) {
  if (detail.review?.approval_recovery_required) return null; // Existing committed-transaction recovery.
  if (detail.evidence_workspace) return detail.evidence_workspace;
  if (detail.approval_context?.version === "human-review-command-v1.1")
    return {state:"unavailable",can_save:false,can_approve:false,scope:null,
      message:"当前审核范围无法建立，请恢复完整来源与依赖证据，或重新分析后再批准。"};
  return null; // Frozen old page/context; no new scope is inferred.
}

export function evidenceWorkspace(space, escape) {
  if (!space) return "";
  if (space.state === "unavailable") return `<section class="panel evidence-workspace"><h2>审核范围暂不可用</h2><p role="alert">当前审核范围无法建立，暂不能批准入库。请恢复完整来源与依赖证据，或重新分析后再审核。</p><button class="btn btn-secondary" data-refresh-evidence type="button">刷新审核状态</button></section>`;
  const summary = space.scope?.summary;
  const heading = `<header><div><p class="eyebrow">视频拆解审核</p><h2>对照原声与画面，纠正有误的内容</h2></div><span class="revision-state">${space.state === "validated" ? "修订已校验" : space.state === "original" ? "原始分析" : "修改已保存"}</span></header>`;
  if (!space.can_save) return `<section class="panel evidence-workspace">${heading}<p role="status">${escape(space.message)}</p>
    ${(space.saved_narration || []).map(s => `<p><small>已保存的修正</small><br>${escape(s.corrected_text)}</p>`).join("")}
    ${space.build_task_id ? `<a class="btn btn-secondary" href="/tasks/${encodeURIComponent(space.build_task_id)}" data-route>查看校验任务与恢复</a>` : ""}<button class="btn btn-text" data-refresh-evidence type="button">刷新校验状态</button></section>`;
  const narration = space.narration.map((s, i) => `<article class="evidence-segment"><div class="evidence-segment-heading"><h3>口播 ${Number(s.start).toFixed(1)}–${Number(s.end).toFixed(1)} 秒</h3><button type="button" class="btn btn-text" data-evidence-seek="${s.start}">定位原声</button></div>
    <p class="evidence-original"><small>原识别</small>${escape(s.original_text)}</p>
    ${s.effective_text!==s.original_text?`<p class="evidence-original evidence-diff"><small>当前采用的人工修正</small>${escape(s.effective_text)}</p>`:""}
    <details><summary>修正口播文字</summary><label for="narration-edit-${i}">核对原声后的文字</label><textarea id="narration-edit-${i}" data-narration-edit="${escape(s.segment_id)}" rows="3" maxlength="4000">${escape(s.effective_text)}</textarea><p class="field-hint">仅纠正原声识别；听不清时请重新分析，不补充原视频未表达的事实。</p><p class="evidence-diff" data-edit-diff="${escape(s.segment_id)}" role="status"></p></details></article>`).join("");
  const boundaries = space.boundaries.map((s, i) => `<article class="evidence-boundary"><div><h3>画面 ${i+1}</h3><span>${Number(s.start).toFixed(1)}–${Number(s.end).toFixed(1)} 秒</span></div>${s.locked ? '<small>视频起点固定</small>' : `<label for="boundary-edit-${i}">调整分镜位置<select id="boundary-edit-${i}" data-boundary-edit="${escape(s.frame_id)}">${space.frames.map(f=>`<option value="${escape(f.frame_id)}" ${f.frame_id===s.frame_id?"selected":""}>${Number(f.seconds).toFixed(1)} 秒 · ${escape(f.frame_id)}</option>`).join("")}</select></label>`}<button type="button" class="btn btn-text" data-boundary-preview="${escape(s.frame_id)}" data-evidence-seek="${s.start}">预览画面起点</button></article>`).join("");
  const risks = (space.scope?.items || []).filter(r => ["explicit", "blocked"].includes(r.mode));
  const riskPanel = risks.length ? `<section class="evidence-risks"><h3>需要明确处理 · ${risks.length} 项</h3>${risks.map(r=>`<div class="evidence-risk"><p><strong>${r.kind==="narration"?"口播识别疑点":"分镜疑点"}</strong> ${r.start==null?"":Number(r.start).toFixed(1)+" 秒"}</p><p>${r.mode==="blocked"?"来源、时间线或未知风险尚未解决，不能统一批准。":"请对照原视频；识别有误时保存修订，确认原结果准确时可明确保留。"}</p>${r.mode==="explicit"?`<label><input type="checkbox" data-explicit-evidence="${escape(r.item_id)}">已核对这一疑点，保留原结果</label>`:""}</div>`).join("")}</section>` : '<p class="evidence-clear">当前没有需要单独确认的疑点。正确内容将在最终批准时统一确认。</p>';
  return `<section class="panel evidence-workspace">${heading}<p>正确的拆解无需逐项勾选。有误时先保存修订，校验通过后再批准。</p><form data-evidence-edit-form><div class="evidence-editor-columns"><section><h3 class="evidence-column-title">口播</h3>${narration || '<p>当前未检测到口播。</p>'}</section><section><h3 class="evidence-column-title">分镜切点</h3>${boundaries}<p class="field-hint">仅可选择当前已识别的画面；没有合适位置时请重新分析。</p></section></div><div class="evidence-save-row"><button class="btn btn-secondary" type="submit" data-save-evidence disabled>保存修改并重新校验</button><p data-evidence-feedback role="status">尚无未保存修改</p></div></form>${riskPanel}<p class="evidence-final-summary">最终确认范围：保留原识别 ${summary.keep_original} 项 · 人工修正口播 ${summary.corrected_narration} 项 · 调整分镜 ${summary.adjusted_boundaries} 项</p></section>`;
}

export function evidenceEdits(space, root) {
  const narration = space.narration.flatMap(segment => {
    const input=[...root.querySelectorAll("[data-narration-edit]")].find(e=>e.dataset.narrationEdit===segment.segment_id);
    const text=input?.value.trim();
    if (!input || text===segment.effective_text) return [];
    const nearest=[...space.frames].sort((a,b)=>Math.abs(a.seconds-(segment.start+segment.end)/2)-Math.abs(b.seconds-(segment.start+segment.end)/2))[0];
    return [{segment_id:segment.segment_id,corrected_text:text,basis:"source_audio_listening",evidence_frame_refs:nearest?[nearest.frame_id]:[]}];
  });
  const boundaries = [...root.querySelectorAll("[data-boundary-edit]")].filter(e=>e.value!==e.dataset.boundaryEdit).map(e=>({boundary_frame_id:e.dataset.boundaryEdit,target_frame_id:e.value}));
  return {narration_edits:narration,boundary_edits:boundaries};
}

export function bindEvidenceWorkspace(root, detail, {api, reload, toast}) {
  const space=reviewWorkspace(detail);
  root.querySelector("[data-refresh-evidence]")?.addEventListener("click",reload);
  if (!space || space.state==="unavailable") return;
  const seek = seconds => {
    const video=root.querySelector("video");
    if (!video) return toast("请先打开合法原视频核对对应时间段。");
    video.currentTime=seconds;video.play().catch(()=>toast("请点击播放器开始播放。"));
    video.scrollIntoView({block:"center",behavior:"smooth"});
  };
  root.querySelectorAll("[data-evidence-seek]").forEach(button=>button.addEventListener("click",()=>seek(Number(button.dataset.evidenceSeek))));
  if (!space.can_save) return;
  const form=root.querySelector("[data-evidence-edit-form]");
  const feedback=root.querySelector("[data-evidence-feedback]");
  const submit=root.querySelector("[data-save-evidence]");
  const update=()=>{
    const edits=evidenceEdits(space,root),count=edits.narration_edits.length+edits.boundary_edits.length;
    submit.disabled=!count; feedback.textContent=count?`${count} 项修改尚未保存；保存不等于批准。`:"尚无未保存修改";
    root.querySelectorAll('[data-review-action="approve"]').forEach(b=>{b.disabled=!!count || !space.can_approve;});
    for(const segment of space.narration){
      const input=[...root.querySelectorAll('[data-narration-edit]')].find(e=>e.dataset.narrationEdit===segment.segment_id);
      const diff=[...root.querySelectorAll('[data-edit-diff]')].find(e=>e.dataset.editDiff===segment.segment_id);
      diff.textContent=input.value===segment.effective_text?"":`修订为：${input.value}`;
    }
  };
  form.addEventListener("input",update);
  root.querySelectorAll("[data-boundary-edit]").forEach(select=>select.addEventListener("change",()=>{
    const button=[...root.querySelectorAll('[data-boundary-preview]')].find(e=>e.dataset.boundaryPreview===select.dataset.boundaryEdit);
    button.dataset.evidenceSeek=String(space.frames.find(f=>f.frame_id===select.value).seconds);update();
  }));
  form.addEventListener("submit",async event=>{
    event.preventDefault();submit.disabled=true;
    try{
      const result=await api(`/api/cases/${encodeURIComponent(detail.case_id)}/review-revisions`,{method:"POST",body:JSON.stringify({
        review_context:detail.approval_context.token,attempt_id:detail.review.attempt_id,
        expected_candidate_sha256:space.candidate_sha256,expected_sources_sha256:space.sources_sha256,
        expected_revision_sha256:space.revision_sha256,...evidenceEdits(space,root)})});
      toast(result.message);await reload();
    }catch(error){feedback.textContent=[error.message,error.detail?.next_action].filter(Boolean).join(" ");submit.disabled=false;
      if(error.status>=500 || error.detail?.code==="CASE_REVISION_SAVED_AWAITING_TASK")await reload();}
  });
}
