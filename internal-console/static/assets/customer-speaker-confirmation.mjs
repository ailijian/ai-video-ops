import {enhanceReviewDisclosures} from './customer-review-presentation.mjs?v=customer-speaker-scope-1';
import {bindFinalCustomerConfirmation} from './customer-final-confirmation.mjs?v=customer-speaker-scope-1';
import {escapeHtml} from './case-components.js?v=flow-closure-2';
import {customerFieldLabel,parseEditedFactValue,editableFactValue} from './customer-components.js?v=flow-closure-2';

const LABELS={speaker_role_facts:'本人职责与经历',first_person_allowed_topics:'可以由本人讲述的内容',
  first_person_scope:'表达范围',role_scope_constraints:'表达与职责边界',first_person_forbidden_claims:'不可使用的第一人称表达',public_display_name:'姓名',public_role:'公开身份'};
export const speakerFieldLabel = field=>LABELS[field] || customerFieldLabel(field);
const display = value=>Array.isArray(value) ? `<ul>${value.map(v=>`<li>${escapeHtml(typeof v==='string'?v:JSON.stringify(v))}</li>`).join('')}</ul>` : `<p>${escapeHtml(typeof value==='string'?value:JSON.stringify(value))}</p>`;

export function preparedPeopleHTML(people) {
  return people.length ? people.map(person=>`<article class="customer-person-review" data-joint-person="${escapeHtml(person.candidate_id)}">
    <div class="customer-final-heading"><h3>${escapeHtml(person.name)}</h3><span data-person-scope-status>本次一起确认</span></div>
    <p class="field-hint">${escapeHtml(person.public_role)}</p>
    ${person.facts.map(fact=>`<div class="customer-person-fact" data-joint-fact="${escapeHtml(fact.candidate_id)}">
      <strong>${escapeHtml(speakerFieldLabel(fact.field))}</strong>${display(fact.value)}
      <details class="evidence-disclosure"><summary>查看依据</summary><p>${escapeHtml(fact.source_excerpt)}</p></details>
      ${fact.editable ? `<details class="customer-person-adjust"><summary>调整</summary><label>处理方式<select data-person-decision><option value="approve">采用此信息</option><option value="edit">修改后采用</option><option value="reject">不采用</option></select></label><label data-person-edit-panel hidden>修改内容<textarea data-person-edit>${escapeHtml(editableFactValue(fact.value))}</textarea></label></details>` : ''}
    </div>`).join('')}
    <p class="field-hint">仅能使用本人有依据的经历；企业或他人的经历不会自动归到这位出镜人。</p>
  </article>`).join('') : '<p class="field-hint">本次未选择出镜人，只会确认客户档案。</p>';
}

export function collectPersonDecisions(host,people) {
  return people.map(person=>({candidate_id:person.candidate_id,decisions:person.facts.map(fact=>{
    const row=host.querySelector(`[data-joint-person="${CSS.escape(person.candidate_id)}"] [data-joint-fact="${CSS.escape(fact.candidate_id)}"]`);
    if (!row) throw new Error('人物审核内容尚未完整显示，请重新核对。');
    const decision=row?.querySelector('[data-person-decision]')?.value || 'approve';
    return {candidate_id:fact.candidate_id,decision,...(decision==='edit'?{
      edited_value:parseEditedFactValue(fact.value,row.querySelector('[data-person-edit]').value)}:{})};
  })}));
}

export function jointFinalPreview(value,businessPreview,{businessOnly=false,deferredPeople=[]}={}) {
  const approving=value.mode==='approve_customer_and_speakers';
  // Deferred names describe the user's local exclusion, never an approved projection.
  const people=businessOnly ? deferredPeople : value.people || [];
  return businessPreview(value)+(people.length ? `<section class="customer-confirmation-people" aria-label="本次出镜人确认范围">
    <div class="customer-confirmation-person-heading"><strong>${businessOnly?'稍后确认的出镜人':'所选出镜人'} · ${people.length} 位</strong><span>${businessOnly?'本次不批准':approving?'本次一起确认':'尚未批准'}</span></div>
    <ul>${people.map(person=>`<li><strong>${escapeHtml(person.name)}</strong>${person.projection?.facts?.public_role ? `<span>${escapeHtml(person.projection.facts.public_role)}</span>` : ''}</li>`).join('')}</ul>
    <button type="button" class="btn btn-ghost" data-review-section-target="customer-review-person-review">返回查看出镜人资料 ↑</button>
    <p class="field-hint">${businessOnly?'出镜人资料保留，稍后继续核对和确认。':approving?'客户与出镜人分别保存审核记录和审批收据。':'本次不会批准人物；完整核对后再明确确认。'}确认资料不授予原始素材使用权。</p>
  </section>` : '');
}

export function updatePersonConfirmationScope(section,host,{businessOnly,empty=false}) {
  section.querySelector('[data-person-scope-title]').textContent=businessOnly ? '本次仅确认客户' : empty ? '本次未选择出镜人' : '本次将一起确认所选出镜人';
  section.querySelector('[data-person-scope-note]').textContent=businessOnly
    ? '出镜人资料保留，本次不会批准，可稍后继续。'
    : empty ? '本次只确认客户档案。' : '请核对下方人物资料；最终提交时，客户与人物分别保留审核记录和审批收据。';
  const toggle=section.querySelector('[data-business-only]');
  toggle.textContent=businessOnly ? '改为一起确认' : '出镜人稍后确认';
  toggle.hidden=empty && !businessOnly;
  for (const status of host.querySelectorAll('[data-person-scope-status]')) status.textContent=businessOnly ? '稍后确认 · 尚未批准' : '本次一起确认';
  // Keep existing input values in place when excluding/re-including a person.
  for (const input of host.querySelectorAll('[data-person-decision], [data-person-edit]')) input.disabled=businessOnly;
}

export function bindCustomerSpeakerConfirmation({root=document,detail,api,collect,render,reload,toast,pollDelay=1000}) {
  const summary=root.querySelector('#customer-review-summary');
  const section=document.createElement('section');section.className='work-surface customer-person-preparation';section.id='customer-review-person-review';
  section.innerHTML='<div class="surface-header"><h2>核对出镜人资料</h2></div><div class="customer-person-scope" role="group" aria-label="出镜人确认范围"><div role="status" aria-live="polite"><strong data-person-scope-title>本次将一起确认所选出镜人</strong><p id="person-confirmation-scope-note" data-person-scope-note>请核对下方人物资料；最终提交时，客户与人物分别保留审核记录和审批收据。</p></div><button type="button" class="btn btn-secondary" data-business-only aria-describedby="person-confirmation-scope-note">出镜人稍后确认</button></div><div data-prepared-people role="region" aria-label="待确认的出镜人资料"></div>';
  summary.before(section);
  enhanceReviewDisclosures(section);
  const host=section.querySelector('[data-prepared-people]');
  let people=[],key=null,ready=false,generation=0,modeOnly=false,timer;
  const updateScope=()=>updatePersonConfirmationScope(section,host,{businessOnly:modeOnly,empty:ready && !people.length});
  const selectedKey = body=>JSON.stringify(body.speaker_confirmations || []);
  function collectJoint() {
    const body=collect();
    if (!modeOnly && (!ready || key!==selectedKey(body))) throw new Error('正在整理出镜人资料；完整摘要准备好后再一起确认。');
    return {...body,joint_speaker_review:true,business_only:modeOnly,
      speaker_fact_decisions:modeOnly?[]:collectPersonDecisions(host,people)};
  }
  const changedFinal=bindFinalCustomerConfirmation({root,detail,api,collect:collectJoint,
    render:value=>jointFinalPreview(value,render,{businessOnly:modeOnly,deferredPeople:people}),
    getBusinessOnly:()=>modeOnly,reload,toast});
  async function prepare(retry=false,own=++generation) {
    clearTimeout(timer);ready=false;changedFinal();
    let body;
    try {body=collect();} catch(error) {host.textContent=error.message;return;}
    const desired=selectedKey(body);
    host.innerHTML='<p class="field-hint" role="status">正在从已保存资料整理出镜人的本人经历和表达范围…</p>';
    try {
      const status=await api(`/api/customers/${encodeURIComponent(detail.business_id)}/review-preparation`,{method:'POST',body:JSON.stringify({...body,retry_preparation:retry})});
      if (own!==generation || !section.isConnected) return;
      if (status.state==='pending') {
        timer=setTimeout(()=>prepare(false,own),pollDelay);return;
      }
      if (status.state!=='prepared') throw new Error('出镜人资料尚未整理完成。已保存原文保留，可以继续整理。');
      people=status.people;key=desired;ready=true;host.innerHTML=preparedPeopleHTML(people);enhanceReviewDisclosures(host);updateScope();
      host.querySelectorAll('[data-person-decision]').forEach(select=>select.addEventListener('change',()=>{
        const row=select.closest('[data-joint-fact]');row.querySelector('[data-person-edit-panel]').hidden=select.value!=='edit';
        window.__customerReviewDirty=true;changedFinal();
      }));
      host.querySelectorAll('[data-person-edit]').forEach(input=>input.addEventListener('input',()=>{window.__customerReviewDirty=true;changedFinal();}));
      changedFinal();
    } catch(error) {
      if (own!==generation || !section.isConnected) return;
      const recheck=error.status===401 || error.status===403 || ['CUSTOMER_CONFIRMATION_STALE','REVIEW_CONTEXT_STALE','INVALID_REVIEW_CONTEXT','CUSTOMER_CONFIRMATION_PENDING'].includes(error.detail?.code);
      host.innerHTML=`<p class="form-error visible" role="alert">${escapeHtml(error.message)}</p><button type="button" class="btn btn-secondary" data-retry-preparation>${recheck?'重新读取资料与恢复入口':'继续整理出镜人资料'}</button>`;
      host.querySelector('[data-retry-preparation]').addEventListener('click',()=>recheck?reload():prepare(true));
    }
  }
  section.querySelector('[data-business-only]').addEventListener('click',event=>{
    if (event.currentTarget.disabled) return;
    modeOnly=!modeOnly;updateScope();
    window.__customerReviewDirty=true;changed();
  });
  function changed() {
    changedFinal();
    let body;try {body=collect();}catch{return;}
    if (!modeOnly && key!==selectedKey(body)) {clearTimeout(timer);timer=setTimeout(()=>prepare(),180);}
  }
  void prepare();
  return changed;
}
