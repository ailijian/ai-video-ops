import { parseEditedFactValue } from "./customer-components.js?v=flow-closure-2";
import { escapeHtml } from "./case-components.js?v=flow-closure-2";

export function amendmentPanel(detail, kind, labelFor) {
  const facts = (kind === "business" ? detail.business_persona?.facts : detail.speaker_persona?.facts) || [];
  const fields = new Map(facts.filter(v => v.value != null).map(v => [v.field, v.value]));
  for (const item of detail.fact_candidates || []) if (item.value != null && !fields.has(item.field)) fields.set(item.field, item.value);
  for (const field of fields.keys()) if (!detail.amendable_fields?.includes(field)) fields.delete(field);
  if (!fields.size || !detail.approval_context) return "";
  const id=kind === "business" ? "customer-correction" : "speaker-correction";
  return `<details class="work-surface profile-correction-card" data-review-amendment>
    <summary class="profile-correction-summary">
      <span class="profile-correction-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/></svg></span>
      <span class="profile-correction-heading"><strong>更正${kind === "business" ? "客户" : "出镜人"}资料</strong><span>更新有变化的信息，保留原资料与审核记录</span></span>
      <span class="profile-correction-toggle" data-disclosure-affordance><span class="correction-closed">展开</span><span class="correction-open">收起</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></span>
    </summary>
    <div class="profile-correction-body">
      <p class="profile-correction-note" id="${id}-note">只提交需要更正的内容与依据。更正后仍需核对和档案批准，已保存的重要限制继续生效。</p>
      <form class="profile-correction-form" data-amendment-form aria-describedby="${id}-note">
        <div class="field"><label for="${id}-field">需要更正的信息</label><select id="${id}-field" data-amend-field>${[...fields].map(([field])=>`<option value="${escapeHtml(field)}">${escapeHtml(labelFor(field))}</option>`).join("")}</select></div>
        <div class="field"><label for="${id}-value">更正后的内容</label><textarea id="${id}-value" data-amend-value rows="3" required></textarea><span class="field-hint">修改选中项的内容，其余信息保留。</span></div>
        <div class="field"><label for="${id}-evidence">来源依据与更正说明</label><textarea id="${id}-evidence" data-amend-evidence rows="3" required maxlength="2000" placeholder="引用可以核实的原文，并简要说明哪里有变化。"></textarea></div>
        <div class="profile-correction-actions"><span>提交后进入核对，不会直接改写已批准档案。</span><button class="btn btn-secondary" type="submit">提交更正，进入核对</button></div>
        <p class="form-error" role="alert"></p>
      </form>
    </div>
  </details>`;
}

export function bindAmendment(root, detail, kind, {api, reload}) {
  const form = root.querySelector("[data-amendment-form]");
  if (!form) return;
  const facts = (kind === "business" ? detail.business_persona?.facts : detail.speaker_persona?.facts) || [];
  const valueFor = field => facts.find(v=>v.field===field)?.value ?? detail.fact_candidates?.find(v=>v.field===field)?.value;
  const select = form.querySelector("[data-amend-field]");
  const textarea = form.querySelector("[data-amend-value]");
  const fill = () => { const value=valueFor(select.value); textarea.value=Array.isArray(value)?value.join("\n"):String(value ?? ""); };
  select.addEventListener("change",fill); fill();
  form.addEventListener("submit",async event=>{
    event.preventDefault(); if(!form.reportValidity()) return;
    const button=form.querySelector("button"); button.disabled=true;
    try {
      const evidence=form.querySelector("[data-amend-evidence]").value.trim();
      const prefix=`/api/customers/${encodeURIComponent(detail.business_id)}`;
      const path=kind==="speaker"?`${prefix}/speakers/${encodeURIComponent(detail.speaker_id)}`:prefix;
      await api(`${path}/review-amendments`,{method:"POST",body:JSON.stringify({
        review_context:detail.approval_context.token,action:"correct",reason:evidence,
        changes:[{field:select.value,value:parseEditedFactValue(valueFor(select.value),textarea.value),evidence}]})});
      await reload();
    } catch(error) { const box=form.querySelector(".form-error");box.textContent=error.detail?.next_action||error.message;box.classList.add("visible");button.disabled=false; }
  });
}

export function bindingReviewPanel(detail) {
  return `<main class="page page-form"><a class="back-link" href="/customers/${encodeURIComponent(detail.business_id)}#speakers" data-route>← 返回客户</a>
    <h1>客户资料已更新，请复核待确认的出镜人资料</h1><section class="work-surface">
    <p>这位出镜人尚有未完成的审核，不能使用已批准档案的关联复核。原资料和人工决定保留。</p>
    <a href="/customers/${encodeURIComponent(detail.business_id)}#profile" data-route>查看当前客户资料</a>
    <form data-binding-review><label class="publication-check"><input type="checkbox" required>已对照当前客户资料核对，原本人事实与表达范围仍适用</label>
    <div class="field"><label>复核说明<textarea rows="3" required data-binding-reason></textarea></label></div>
    <button class="btn btn-primary" type="submit">建立新的复核记录</button><p class="form-error" role="alert"></p></form>
    <p>新记录仍需完成事实核对与档案批准。本人事实已变化时，请通过下方更正入口提交针对性证据。</p></section></main>`;
}

export function mountRecovery(root, api, operations, reload, {container = null} = {}) {
  if (!operations?.length) return;
  const host=container || root.querySelector("main") || root;
  host.insertAdjacentHTML("afterbegin",`<section class="${container ? 'case-result-recovery' : 'work-surface review-recovery'}">${container ? '' : `<h2>上次审核提交尚未完成</h2>
    <p>可以继续原操作。系统会核对原对象及权限，保留已保存决定，不重复创建档案或任务。</p>
    `}${operations.map((v,i)=>`<button class="btn ${container ? 'btn-primary' : 'btn-secondary'}" data-resume-review="${i}">${v.label || '继续完成原操作'}${operations.length>1?` ${i+1}`:""}</button>${v.can_discard?`<button class="btn btn-ghost" data-cancel-review="${i}">取消这次未保存的提交</button>`:""}`).join("")}<p class="form-error" role="alert"></p></section>`);
  const section=host.firstElementChild;
  host.querySelectorAll("[data-cancel-review]").forEach(button=>button.addEventListener("click",async()=>{
    button.disabled=true;const item=operations[Number(button.dataset.cancelReview)];
    const path=item.request_path.includes("/api/cases/")?`case/${item.request_path.split("/")[3]}`:
      item.request_path.includes("/speakers/")?`speaker/${item.request_path.split("/")[5]}`:`business/${item.request_path.split("/")[3]}`;
    try {await api(`/api/review-commands/${path}/${item.operation_id}/cancel`,{method:"POST"});await reload();}
    catch(error){const box=section.querySelector(".form-error");box.textContent=[error.detail?.message||error.message,error.detail?.next_action].filter(Boolean).join(' ');box.classList.add("visible");button.disabled=false;}
  }));
  host.querySelectorAll("[data-resume-review]").forEach(button=>button.addEventListener("click",async()=>{
    if(button.disabled) return;
    const item=operations[Number(button.dataset.resumeReview)];
    const label=button.textContent;const buttons=section.querySelectorAll('button');
    buttons.forEach(v=>{v.disabled=true;});button.textContent=item.busyLabel || '正在继续…';section.setAttribute('aria-busy','true');
    const box=section.querySelector('.form-error');box.textContent='';box.classList.remove('visible');
    try {const result=await api(item.request_path,{method:"POST",body:JSON.stringify(item.payload)}); await reload(result);}
    catch(error){box.textContent=[error.detail?.message||error.message,error.detail?.next_action].filter(Boolean).join(' ');box.classList.add("visible");buttons.forEach(v=>{v.disabled=false;});button.textContent=label;button.focus();}
    finally {section.removeAttribute('aria-busy');}
  }));
}
