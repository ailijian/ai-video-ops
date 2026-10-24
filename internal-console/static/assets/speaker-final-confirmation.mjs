import {escapeHtml} from './case-components.js?v=flow-closure-2';
import {formatProfileValue,EvidenceDisclosure} from './profile-components.js?v=productized-stage2-3';
import {editableFactValue,parseEditedFactValue} from './customer-components.js?v=cbux1-b234-3';
import {speakerFieldLabel} from './speaker-components.js?v=flow-closure-2';
import {enhanceReviewDisclosures,bindReviewReturnLinks} from './customer-review-presentation.mjs?v=customer-review-summary-1';

const blockerText=value=>({critical_conflicts:'仍有关键事实或身份冲突，需要进一步核实。',
  universal_first_person_guardrail:'本人表达边界尚不完整，不能批准。'}[value]
  || (/^[a-z_]+$/.test(value)?`尚需核实：${speakerFieldLabel(value)===value?'本人资料与表达范围':speakerFieldLabel(value)}`:value));

export function speakerReviewMarkup(detail) {
  const complete=detail.status==='persona_review_required';
  const known=complete ? (detail.speaker_persona?.facts || []).filter(v=>v.state==='known')
    : (detail.fact_candidates || []).filter(v=>v.state==='known_candidate');
  const pending=complete ? [] : (detail.fact_candidates || []).filter(v=>v.state==='requires_review');
  const protectedFields=new Set(['role_scope_constraints','first_person_forbidden_claims']);
  const retained=known.filter(v=>protectedFields.has(v.field)),knownInformation=known.filter(v=>!protectedFields.has(v.field));
  const knownRows=items=>`<dl class="profile-rows">${items.map(v=>`<div class="profile-row"><dt>${escapeHtml(speakerFieldLabel(v.field))}</dt><dd>${formatProfileValue(v.value)}</dd></div>`).join('')}</dl>`;
  const cards=items=>items.map(v=>{
    const risk=!v.default_review_selection;
    return `<article class="customer-fact-card ${risk?'is-exception':''}" data-speaker-review-row="${escapeHtml(v.candidate_id)}">
      <div class="customer-fact-heading"><h4>${escapeHtml(speakerFieldLabel(v.field))}</h4><span>${risk?'需要重点核对':v.protective_scope?'待本次确认':'待统一确认'}</span></div>
      <div class="customer-fact-value">${formatProfileValue(v.value)}</div>
      ${v.protective_scope?'<p class="field-hint">有来源的保护性边界，将随最后一次确认保存；已有重要限制继续保留。</p>':''}
      ${risk?`<p class="field-hint">${escapeHtml(v.review_exception_reason || '请对照本人资料明确处理。')}</p>`:''}
      <div class="customer-fact-footer">${EvidenceDisclosure(v.source_excerpt)}</div>
      ${risk?'':'<details class="customer-person-adjust"><summary>调整</summary>'}
      <div class="field"><label>处理方式<select data-speaker-decision aria-label="处理${escapeHtml(speakerFieldLabel(v.field))}">
        <option value="" ${risk?'selected':''}>${risk?'请选择核对结果':'暂不处理'}</option>
        <option value="approve" ${risk?'':'selected'}>采用此信息</option><option value="edit">修改后采用</option><option value="reject">不采用</option>
      </select></label></div>${risk?'':'</details>'}
      <div class="field review-edit-panel" data-speaker-edit-panel hidden><label>修改后的信息<textarea data-speaker-edit rows="3" aria-label="修改${escapeHtml(speakerFieldLabel(v.field))}">${escapeHtml(editableFactValue(v.value))}</textarea></label></div>
    </article>`;
  }).join('');
  const risks=pending.filter(v=>!v.default_review_selection),ordinary=pending.filter(v=>v.default_review_selection && !v.protective_scope),protective=pending.filter(v=>v.default_review_selection && v.protective_scope);
  return `<section class="work-surface review-surface" id="speaker-review-information"><div class="review-surface-heading"><h2>本人资料</h2><p>请集中浏览，准确的普通信息会在最终确认时统一采用；需要更正时打开“调整”。</p></div>
    ${knownInformation.length?`<div class="customer-review-group">${knownRows(knownInformation)}</div>`:''}
    ${ordinary.length?`<div class="customer-review-group">${cards(ordinary)}</div>`:''}</section>
    ${retained.length || protective.length?`<section class="work-surface review-surface" id="speaker-review-boundaries"><div class="review-surface-heading"><h2>表达边界</h2><p>有来源、无冲突的保护性边界已纳入本次确认，无需逐项选择。</p></div>
      ${retained.length?`<div class="customer-review-group"><p class="field-hint">已确认限制 · 持续保留</p>${knownRows(retained)}</div>`:''}
      ${protective.length?`<div class="customer-review-group">${cards(protective)}</div>`:''}</section>`:''}
    ${risks.length?`<section class="work-surface review-surface" id="speaker-review-risks"><div class="review-surface-heading"><h2>重点核对 <span class="customer-section-count">${risks.length} 项</span></h2><p>以下身份、来源或表达范围需明确核对。未处理时不能批准。</p></div><div class="customer-review-group">${cards(risks)}</div></section>`:''}
    <section class="work-surface customer-submit-summary"><h2>本次确认</h2><div data-speaker-final-preview aria-live="polite"></div>
      <p class="customer-review-consequence">一次确认将保存本人的信息审核记录，并批准当前出镜人档案；两份记录分别保留。客户档案和已有重要限制继续按原规则生效。</p>
      <p class="field-hint">只能使用本人有依据的经历，不会把企业或他人的成绩自动归到本人。确认档案不会授予照片、视频或肖像素材使用权。</p>
      <div class="review-submit-bar"><button class="btn btn-primary" type="button" data-confirm-speaker disabled>正在核对确认范围…</button></div></section>`;
}

export function collectSpeakerDecisions(root,detail) {
  if(detail.status==='persona_review_required') return [];
  return (detail.fact_candidates || []).filter(v=>v.state==='requires_review').flatMap(v=>{
    const row=root.querySelector(`[data-speaker-review-row="${CSS.escape(v.candidate_id)}"]`);
    if(!row)throw new Error('人物核对内容尚未完整显示，请重新读取。');
    const decision=row.querySelector('[data-speaker-decision]').value;
    if(!decision)return [];
    return [{candidate_id:v.candidate_id,decision,...(decision==='edit'?{edited_value:parseEditedFactValue(v.value,row.querySelector('[data-speaker-edit]').value)}:{})}];
  });
}

export function bindSpeakerFinalConfirmation({root,detail,api,reload,toast,delay=180}) {
  const host=root.querySelector('[data-speaker-final-preview]'),button=root.querySelector('[data-confirm-speaker]');
  const path=`/api/customers/${encodeURIComponent(detail.business_id)}/speakers/${encodeURIComponent(detail.speaker_id)}`;
  let sequence=0,timer,current=null,busy=false;
  const alive=()=>root.isConnected!==false;
  const collect=()=>({review_context:detail.approval_context.token,decisions:collectSpeakerDecisions(root,detail)});
  const errorText=error=>[error.detail?.message || error.message,error.detail?.next_action].filter(Boolean).join(' ');
  function failed(error,submitted=false) {
    current=null;button.disabled=true;button.textContent=submitted?'请先核对提交状态':'请重新核对确认范围';
    host.innerHTML=`<p class="form-error visible" role="alert">${escapeHtml(errorText(error))}</p><button class="btn btn-secondary" type="button" data-read-speaker-status>${submitted?'查看当前状态与恢复入口':'重新读取确认范围'}</button>`;
    host.querySelector('[data-read-speaker-status]').addEventListener('click',()=>{
      if(!submitted)return refresh();
      // Explicitly re-read the saved operation; the local form is being replaced.
      window.__customerReviewDirty=false;
      return reload();
    });
  }
  async function refresh() {
    if(busy || !alive())return;
    clearTimeout(timer);const own=++sequence;current=null;button.disabled=true;
    button.textContent='正在核对确认范围…';
    host.innerHTML='<p class="field-hint" role="status">正在核对本次本人信息与表达边界…</p>';
    try {
      const fingerprint=JSON.stringify(collect());
      const value=await api(path+'/review-preview',{method:'POST',body:fingerprint});
      if(own!==sequence || !alive())return;
      if(value.schema_version!=='speaker-final-confirmation-v1.0' || value.mode!=='approve_speaker_profile'
          || !value.review_context?.token || !value.preview_sha256 || !value.projection || typeof value.can_submit!=='boolean')throw new Error('人物确认范围不完整，请重新读取。');
      current={value,fingerprint};
      host.innerHTML=`<p>本次核对 ${Object.keys(value.projection.facts).length} 项本人信息，${value.can_submit?'无待处理阻断。':'完成重点核对后才能批准。'}</p>
        ${value.blockers.length?`<ul class="field-hint">${value.blockers.map(v=>`<li>${escapeHtml(blockerText(v))}</li>`).join('')}</ul>`:''}
        <button class="btn btn-ghost" type="button" data-review-section-target="speaker-review-information">返回查看本人资料 ↑</button>`;
      bindReviewReturnLinks(host,root);
      button.textContent=value.can_submit?'确认资料并批准出镜人档案':'请先完成重点核对';button.disabled=!value.can_submit;
    } catch(error) {if(own===sequence && alive())failed(error);}
  }
  function changed() {
    if(busy || !alive())return;
    ++sequence;current=null;button.disabled=true;button.textContent='正在更新确认范围…';
    host.innerHTML='<p class="field-hint" role="status">信息已变化，正在重新核对本次确认范围…</p>';
    clearTimeout(timer);timer=setTimeout(refresh,delay);
  }
  root.querySelectorAll('[data-speaker-decision]').forEach(select=>select.addEventListener('change',()=>{
    const row=select.closest('[data-speaker-review-row]');row.querySelector('[data-speaker-edit-panel]').hidden=select.value!=='edit';
    window.__customerReviewDirty=true;changed();
  }));
  root.querySelectorAll('[data-speaker-edit]').forEach(input=>input.addEventListener('input',()=>{window.__customerReviewDirty=true;changed();}));
  button.addEventListener('click',async()=>{
    if(busy || !current || button.disabled || !alive())return;
    const selected=current;
    try {if(JSON.stringify(collect())!==selected.fingerprint){changed();return;}}catch(error){failed(error);return;}
    busy=true;button.disabled=true;button.textContent='正在确认出镜人档案…';
    const inputs=[...root.querySelectorAll('input,select,textarea')],states=inputs.map(v=>v.disabled);
    inputs.forEach(v=>{v.disabled=true;});
    try {
      const result=await api(path+'/confirm',{method:'POST',body:JSON.stringify({review_context:selected.value.review_context.token,
        preview_sha256:selected.value.preview_sha256,confirmation:selected.value.mode})});
      if(result.execution?.completion!=='speaker_approved')throw new Error('请核对当前状态与原操作结果。');
      window.__customerReviewDirty=false;toast('出镜人资料与档案已确认。');if(alive())await reload();
    } catch(error) {if(alive()){inputs.forEach((v,i)=>{v.disabled=states[i];});failed(error,true);}}
    finally {busy=false;}
  });
  enhanceReviewDisclosures(root);void refresh();
  return changed;
}
