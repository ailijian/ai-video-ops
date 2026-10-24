import {bindReviewReturnLinks} from './customer-review-presentation.mjs?v=customer-review-summary-1';
import { escapeHtml } from './case-components.js?v=flow-closure-2';

export function bindFinalCustomerConfirmation({root, detail, api, collect, render, reload, toast, getBusinessOnly = () => false, delay = 180}) {
  const host = root.querySelector('[data-customer-final-preview]');
  const button = root.querySelector('#submit-fact-review');
  let sequence = 0, timer, current = null, busy = false;
  const errorText = error => [error.detail?.message || error.message, error.detail?.next_action].filter(Boolean).join(' ');
  const invalid = message => {
    current = null; button.disabled = true; button.textContent = '核对确认范围后确认';
    const consequence = root.querySelector('[data-review-consequence]');
    if (consequence) consequence.textContent = '确认范围尚未核对完成，请重新读取后再提交。';
    host.innerHTML = `<p class="form-error visible" role="alert">${escapeHtml(message)}</p><button type="button" class="btn btn-secondary" data-reload-final-preview>重新读取确认范围</button>`;
    host.querySelector('[data-reload-final-preview]')?.addEventListener('click', refresh);
  };
  async function refresh() {
    if (busy) return;
    clearTimeout(timer);
    const version = ++sequence;
    current = null; button.disabled = true; button.textContent = '正在核对确认范围…';
    host.innerHTML = '<p class="field-hint" role="status">正在核对本次将生效的信息与限制…</p>';
    try {
      const payload = collect();
      const fingerprint = JSON.stringify(payload);
      const value = await api(`/api/customers/${encodeURIComponent(detail.business_id)}/review-preview`, {
        method:'POST', body:fingerprint,
      });
      if (version !== sequence) return;
      if (!['approve_business_profile','save_review_progress','approve_customer_and_speakers'].includes(value.mode) || !value.review_context?.token || !value.preview_sha256 || !value.projection) {
        throw new Error('确认范围不完整，请重新读取后再确认。');
      }
      current = {value, fingerprint};
      host.innerHTML = render(value);
      bindReviewReturnLinks(host, root);
      button.textContent = value.mode === 'approve_customer_and_speakers' ? '确认客户与所选出镜人档案' : value.mode === 'approve_business_profile' ? (getBusinessOnly() ? '仅确认客户档案' : '确认资料并批准客户档案') : '保存核对进度';
      button.disabled = value.can_submit === false;
      const consequence = root.querySelector('[data-review-consequence]');
      if (consequence) consequence.textContent = value.mode === 'approve_customer_and_speakers'
        ? `本次将确认客户及 ${value.people.length} 位所选出镜人，分别保留审核记录与审批收据。`
        : value.mode === 'approve_business_profile'
        ? (getBusinessOnly() ? '本次仅确认客户档案；出镜人稍后确认，本次不会批准。' : '本次确认将批准本次客户档案；出镜人仍需独立审核。')
        : '本次只保存核对进度，不会批准客户档案。';
    } catch (error) {
      if (version === sequence) invalid(errorText(error));
    }
  }
  function changed() {
    if (busy) return;
    ++sequence; current = null; button.disabled = true;
    button.textContent = '正在更新确认范围…';
    const consequence = root.querySelector('[data-review-consequence]');
    if (consequence) consequence.textContent = '确认范围已变化，正在重新核对；请等待更新后再提交。';
    host.innerHTML = '<p class="field-hint" role="status">信息已变化，正在重新核对确认范围…</p>';
    clearTimeout(timer); timer = setTimeout(refresh, delay);
  }
  button.addEventListener('click', async () => {
    if (busy || !current || button.disabled) return;
    const selected = current;
    try {
      if (JSON.stringify(collect()) !== selected.fingerprint) {changed(); return;}
    } catch (error) {invalid(errorText(error)); return;}
    busy = true;
    const inputs = [...root.querySelectorAll('.customer-review-page input, .customer-review-page select, .customer-review-page textarea, [data-review-choice], [data-business-only]')];
    const states = inputs.map(v => v.disabled);
    inputs.forEach(v => {v.disabled = true;});
    button.disabled = true;
    button.textContent = selected.value.mode === 'approve_customer_and_speakers' ? '正在确认客户与出镜人…' : selected.value.mode === 'approve_business_profile' ? '正在确认客户档案…' : '正在保存核对进度…';
    try {
      const result = await api(`/api/customers/${encodeURIComponent(detail.business_id)}/confirm`, {method:'POST',body:JSON.stringify({
        review_context:selected.value.review_context.token, preview_sha256:selected.value.preview_sha256,
        confirmation:selected.value.mode,
      })});
      window.__customerReviewDirty = false;
      toast(result.execution.completion === 'customer_and_speakers_approved' ? '客户与所选出镜人已确认。' : result.execution.completion === 'business_approved'
        ? (result.execution.speaker_confirmation?.retry_required ? '客户档案已批准，出镜人资料仍需补充或重试。' : '客户档案已批准，出镜人仍需独立审核。') : '核对进度已保存，客户档案尚未批准。');
      await reload();
    } catch (error) {
      inputs.forEach((v,i) => {v.disabled = states[i];});
      current = null;
      host.innerHTML = `<p class="form-error visible" role="alert">${escapeHtml(errorText(error))}</p><button type="button" class="btn btn-secondary" data-read-confirmation-status>查看当前状态与恢复入口</button>`;
      host.querySelector('[data-read-confirmation-status]')?.addEventListener('click', () => reload());
      button.textContent = '请先核对提交状态';
    } finally {busy = false;}
  });
  void refresh();
  return changed;
}
