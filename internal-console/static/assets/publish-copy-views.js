import { startTaskPolling } from './task-progress.js';
import { safeCreationMessage, CreationHeader, CreationStepper } from './creation-components.js?v=news-review-ui-2';

// One editor on the existing delivery page, shared by all three Native modes.
export async function mountPublishCopy(host, requestId, { api, showToast, escapeHtml }) {
  let capability;
  try { capability = await api('/api/publish-copy/capability'); } catch { return; }
  if (!capability.enabled || !host.isConnected) return;
  const originalDownloads = new Set([
    `/api/create/${encodeURIComponent(requestId)}/exported-excel`,
    `/api/create/novel-news/${encodeURIComponent(requestId)}/excel`,
    `/api/create/news/${encodeURIComponent(requestId)}/excel`,
  ]);
  for (const link of host.querySelectorAll?.('a[href]') || []) {
    if (originalDownloads.has(link.getAttribute('href'))) link.textContent = '下载制作稿（原模板）';
  }
  const panel = document.createElement('section');
  panel.className = 'work-surface creation-section publish-copy-panel';
  host.append(panel);
  const esc = (value) => escapeHtml(String(value ?? ''));
  const url = `/api/create/${encodeURIComponent(requestId)}/publish-copy`;
  let state;
  let editing = false;
  let stopPolling = null;
  const observedTerminalTasks = new Set();
  const notify = (error) => showToast(safeCreationMessage(error.detail?.next_action || error.detail?.message || error.message,
    '发布信息尚未完成，请核对来源与当前权限，原制作稿会保留。'));

  async function refresh() {
    if (!panel.isConnected) return;
    try {
      state = (await api(url)).state;
      // Native state may have been read before a worker finished while the
      // response's Task projection was read afterwards. Observe completion,
      // then obtain one fresh canonical snapshot; never repeat the operation.
      const terminal = state.tasks?.filter(task => ['completed','failed'].includes(task.status) &&
        !observedTerminalTasks.has(task.task_id)) || [];
      if (terminal.length) {
        terminal.forEach(task => observedTerminalTasks.add(task.task_id));
        if (!state.task_snapshot_before_native) state = (await api(url)).state;
      }
      editing = false;
      panel.dataset.dirty = 'false';
      render();
      pollActiveTask();
    } catch (error) {
      panel.innerHTML = `${CreationHeader({title:'发布信息暂时无法继续', description:'请核对当前资料、创作参考与权限。原制作稿及旧交付会保留。', eyebrow:'发布与交付'})}<div class="creation-actions"><button type="button" class="btn btn-secondary" data-pc-refresh>刷新查看</button></div>`;
      panel.querySelector('[data-pc-refresh]').onclick = refresh;
    }
  }

  function pollActiveTask() {
    stopPolling?.(); stopPolling = null;
    const active = state.tasks?.find((task) => ['queued', 'running'].includes(task.status));
    if (active) stopPolling = startTaskPolling({ api, taskId: active.task_id, onUpdate: () => {},
      onDone: () => refresh(), onError: () => {} });
  }

  function render() {
    const running = state.tasks?.some((task) => ['queued', 'running'].includes(task.status));
    const exportTask = state.tasks?.find(task => task.payload?.operation === 'publish_copy_export' &&
      task.payload.publish_copy?.expected_draft_ref?.sha256 === state.draft?.ref?.sha256);
    const exportPending = exportTask?.status === 'failed' && state.confirmed &&
      state.delivery?.draft_ref?.sha256 !== state.draft?.ref?.sha256;
    const labels = { not_started: '制作稿已审核，可以准备发布信息。', not_dispatched: '发布信息待生成，可继续原操作。',
      validated_result_unpublished: '模型响应已保存，可继续恢复结果。', dispatched_outcome_unknown: '本次模型调用结果未能确认。系统不会自动重复生成。重新尝试可能产生额外费用。',
      confirmed_failure: '返回内容未通过来源检查，可以修改或明确重新尝试。', stale: '制作内容或来源已变化，原发布稿不能用于新的正式交付。',
      draft_ready: state.confirmed ? '发布信息已确认，可以导出新版 Excel。' : '请核对发布信息；确认后才会进入正式交付。' };
    const items = state.draft?.payload?.items || [];
    const remaining = state.production.filter(value => !items.some(item => item.target_id === value.target_id));
    const needsRetry = ['dispatched_outcome_unknown', 'confirmed_failure', 'stale'].includes(state.state);
    const locked = state.confirmed && !editing;
    const delivered = state.state === 'draft_ready' && state.confirmed &&
      state.delivery?.draft_ref?.sha256 === state.draft?.ref?.sha256;
    const step = needsRetry || !items.length || remaining.length ? 0 : editing ? 1 : delivered ? 3 : state.confirmed ? 2 : 1;
    const badge = running ? '处理中' : exportPending ? '待继续' : needsRetry ? '需要处理' :
      editing ? '修改中' : delivered ? '已交付' : state.confirmed ? '待导出' : items.length && !remaining.length ? '待确认' : '待生成';
    panel.innerHTML = `<div class="publish-copy-header">
      ${CreationHeader({title:'发布信息', eyebrow:'发布与交付'})}
      <div class="publish-copy-header-tools"><span class="pill ${delivered && !running && !editing ? 'pill-approved' : 'pill-review'}" data-pc-status>${badge}</span>
      <button type="button" class="btn btn-quiet" data-pc-refresh>刷新进度</button></div></div>
      <p class="publish-copy-status" role="status" aria-live="polite">${esc(running ? '正在后台处理，离开或刷新后仍可继续。' : editing ? '正在修改发布信息。修改后需重新确认；原已确认版本和文件保留。' : exportPending ? '导出尚未完成，可继续原操作。' : delivered ? '新版文件已准备好，可以下载。发布信息已锁定，需要修改时请点击“修改发布信息”。' : locked ? '发布信息已确认并锁定，可以导出新版 Excel。' : labels[state.state] || '请核对原操作。')}</p>
      <div data-pc-progress>${CreationStepper({steps:['生成发布信息','核对并确认','导出交付'], currentIndex:step})}</div>
      <div class="content-review-list publish-copy-list">
      ${items.map((item, index) => {
        const original = state.production.find((value) => value.target_id === item.target_id);
        const id = `pc-${esc(requestId)}-${index}`;
        return `<article class="content-review-item publish-copy-item" data-pc-item="${index}">
          <div class="content-review-heading"><span>${index + 1}</span><div><h3>第 ${index + 1} 条发布信息</h3></div></div>
          <div class="publish-copy-item-body">
          <details class="creation-evidence"><summary>查看已审核制作稿</summary><p class="publish-copy-source">${esc(original?.units?.length ? original.units.map((u, n) => `${n + 1}. ${u.text}`).join('\n') : `${original?.title}\n${original?.narration}`)}</p></details>
          ${state.mode !== 'mix' ? `<fieldset class="publish-copy-headlines"><legend>实际交付的制作短标题</legend><p class="field-hint">单条视频合并在一个单元格内，最多 6 条。保留价格、主体及适用条件。</p>
            ${item.production_headlines.map((headline, hi) => `<div class="publish-copy-headline" data-pc-headline="${hi}">
              <div class="field"><label for="${id}-headline-${hi}">短标题 ${hi + 1}</label><textarea id="${id}-headline-${hi}" data-pc-headline-text rows="2">${esc(headline.text)}</textarea></div>
              <details class="creation-evidence"><summary>核对来源对应</summary>${original.units.map((u, ui) => `<label class="publish-copy-source-option"><input type="checkbox" data-pc-unit="${esc(u.unit_id)}" ${headline.source_unit_ids.includes(u.unit_id) ? 'checked' : ''}><span>第 ${ui + 1} 段：${esc(u.text)}</span></label>`).join('')}</details>
              <button type="button" class="btn btn-quiet" data-pc-remove="${hi}" aria-label="移除短标题 ${hi + 1}" ${locked ? 'hidden' : ''} ${running ? 'disabled' : ''}>移除此标题</button></div>`).join('')}
            <button type="button" class="btn btn-secondary" data-pc-add ${locked ? 'hidden' : ''} ${running || item.production_headlines.length >= 6 ? 'disabled' : ''}>添加短标题</button></fieldset>` : ''}
          <div class="publish-copy-fields">
            <div class="field"><label for="${id}-title">发布标题</label><input id="${id}-title" type="text" data-pc-title value="${esc(item.publish_title)}"></div>
            <div class="field"><label for="${id}-body">发布正文</label><textarea id="${id}-body" data-pc-body rows="6">${esc(item.publish_body)}</textarea></div>
            <div class="field"><label for="${id}-topics">话题</label><input id="${id}-topics" type="text" data-pc-topics value="${esc(item.topics.map(t => '#' + t.replace(/^#/, '')).join(' '))}" aria-describedby="${id}-topics-help"><small id="${id}-topics-help" class="field-hint">多个话题用空格分隔。通常选择 3–5 个相关话题，来源不足时不凑数。</small></div>
          </div>
          <button type="button" class="btn btn-quiet publish-copy-regenerate" data-pc-regenerate="${esc(item.target_id)}" ${locked ? 'hidden' : ''} ${running ? 'disabled' : ''}>仅重新生成这条</button></div></article>`;
      }).join('')}
      </div>
      <div class="creation-action-bar publish-copy-actions">
      ${!items.length && ['not_started','not_dispatched','validated_result_unpublished'].includes(state.state) ? `<button type="button" class="btn btn-primary" data-pc-generate ${running ? 'disabled' : ''}>${state.state === 'not_dispatched' || state.state === 'validated_result_unpublished' ? '继续完成原操作' : '生成发布信息'}</button>` : ''}
      ${items.length && remaining.length && !needsRetry ? `<button type="button" class="btn btn-primary" data-pc-remaining ${running ? 'disabled' : ''}>生成剩余发布信息（${remaining.length} 条）</button>` : ''}
      ${locked && !needsRetry ? `<button type="button" class="btn btn-secondary" data-pc-edit ${running ? 'disabled' : ''}>修改发布信息</button>` : ''}
      ${editing ? '<button type="button" class="btn btn-secondary" data-pc-cancel>取消修改</button>' : ''}
      ${items.length && state.state !== 'stale' ? `<button type="button" class="btn btn-secondary" data-pc-save ${locked ? 'hidden' : ''} ${running ? 'disabled' : ''}>保存修改</button><button type="button" class="btn btn-primary" data-pc-confirm ${needsRetry || locked || remaining.length ? 'hidden' : ''} ${running ? 'disabled' : ''}>确认发布信息</button>` : ''}
      ${state.confirmed ? `<button type="button" class="btn btn-primary" data-pc-export ${editing || needsRetry || delivered ? 'hidden' : ''} ${running ? 'disabled' : ''}>${exportPending ? '继续完成原导出' : '导出新版 Excel'}</button>` : ''}
      ${state.delivery ? `<a class="btn ${delivered && !editing ? 'btn-primary' : 'btn-secondary'}" data-pc-download href="${url}/excel/${encodeURIComponent(state.delivery.delivery_id)}">${delivered && !editing ? '下载已确认版本' : '下载上次已确认版本'}</a>` : ''}
      </div>
      ${needsRetry ? `<div class="publish-copy-recovery"><label class="publish-copy-consent"><input type="checkbox" data-pc-retry-consent ${running ? 'disabled' : ''}><span>我确认重新尝试；原调用可能已执行，再次调用可能产生额外费用。</span></label><button type="button" class="btn btn-primary" data-pc-retry disabled>重新尝试生成</button></div>` : ''}
      <p class="field-hint publish-copy-governance">原制作稿保留，上方可下载。发布信息确认不代表平台发布，也不新增素材使用权。</p>`;
    panel.querySelector('[data-pc-refresh]').onclick = refresh;
    panel.querySelector('[data-pc-retry-consent]')?.addEventListener('change', e => { panel.querySelector('[data-pc-retry]').disabled = running || !e.target.checked; });
    bindAction('[data-pc-edit]', () => { editing = true; render(); });
    bindAction('[data-pc-cancel]', refresh);
    bindAction('[data-pc-generate]', () => generate(false));
    bindAction('[data-pc-retry]', () => generate(true));
    bindAction('[data-pc-remaining]', async () => {
      if (panel.dataset.dirty === 'true') await save();
      await generate(true, remaining.slice(0,5).map(item => item.target_id));
    });
    bindAction('[data-pc-save]', async () => { await save(); showToast('修改已保存，请核对后确认发布信息。'); });
    bindAction('[data-pc-confirm]', async () => { const draftRef = await save({reload:false}); await api(url + '/confirm', { method: 'POST', body: JSON.stringify({ draft_ref: draftRef }) }); await refresh(); });
    bindAction('[data-pc-export]', async () => track(await api(url + '/export', { method: 'POST' })));
    panel.querySelectorAll('[data-pc-regenerate]').forEach(button => button.onclick = async () => {
      if (panel.dataset.dirty === 'true') { showToast('请先保存当前修改，再重新生成。'); return; }
      if (!globalThis.confirm('将重新生成这一条发布信息，可能产生额外模型费用。原制作稿会保留。')) return;
      button.disabled = true; try { await generate(true, [button.dataset.pcRegenerate]); } catch (error) { notify(error); button.disabled = false; }
    });
    panel.querySelectorAll('[data-pc-remove]').forEach(button => button.onclick = () => {
      const payload = collect(); const index = Number(button.closest('[data-pc-item]').dataset.pcItem);
      payload.items[index].production_headlines.splice(Number(button.dataset.pcRemove), 1);
      state.draft.payload = payload; render();
      markDirty();
    });
    panel.querySelectorAll('[data-pc-add]').forEach(button => button.onclick = () => {
      const payload = collect(); const index = Number(button.closest('[data-pc-item]').dataset.pcItem);
      payload.items[index].production_headlines.push({ order: payload.items[index].production_headlines.length + 1, text: '', source_unit_ids: [], mapping_kind: 'condense' });
      state.draft.payload = payload; render();
      markDirty();
    });
    panel.querySelectorAll('textarea,input:not([data-pc-retry-consent])').forEach(input => {
      input.disabled = running || locked && input.type === 'checkbox';
      if (input.type !== 'checkbox') input.readOnly = locked;
      input.addEventListener('input', markDirty);
      input.addEventListener('change', markDirty);
    });
  }
  function markDirty() {
    panel.dataset.dirty = 'true';
    const needsRetry = ['dispatched_outcome_unknown', 'confirmed_failure', 'stale'].includes(state.state);
    const status = panel.querySelector('[role="status"]');
    if (status) status.textContent = needsRetry ? '当前生成或来源状态尚未解决，修改不能作为已确认交付。' : '修改尚未确认，请保存或确认实际交付内容。';
    const exportButton = panel.querySelector('[data-pc-export]');
    if (exportButton) { exportButton.disabled = true; exportButton.hidden = true; }
    for (const selector of ['[data-pc-save]', '[data-pc-confirm]']) {
      const button = panel.querySelector(selector);
      if (button && (selector !== '[data-pc-confirm]' || !needsRetry && state.production.length === state.draft.payload.items.length)) button.hidden = false;
    }
    const badge = panel.querySelector('[data-pc-status]');
    if (badge) { badge.textContent = needsRetry ? '需要处理' : '修改待确认'; badge.className = 'pill pill-review'; }
    const progress = panel.querySelector('[data-pc-progress]');
    if (progress) progress.innerHTML = CreationStepper({steps:['生成发布信息','核对并确认','导出交付'], currentIndex:needsRetry ? 0 : 1});
    const download = panel.querySelector('[data-pc-download]');
    if (download) { download.textContent = '下载上次已确认版本'; download.className = 'btn btn-secondary'; }
  }
  function bindAction(selector, action) {
    panel.querySelector(selector)?.addEventListener('click', async event => {
      const button = event.currentTarget;
      const label = button.textContent;
      const status = panel.querySelector('[role="status"]');
      const message = status?.textContent;
      button.disabled = true;
      if (!['[data-pc-edit]', '[data-pc-cancel]'].includes(selector)) {
        button.textContent = '正在处理…';
        if (status) status.textContent = '正在核对并提交，请稍候。原内容和文件会保留。';
      }
      try { await action(); } catch (error) {
        notify(error);
        if (button.isConnected) { button.disabled = false; button.textContent = label; }
        if (status?.isConnected) status.textContent = message;
      }
    });
  }
  function collect() {
    const payload = structuredClone(state.draft.payload);
    panel.querySelectorAll('[data-pc-item]').forEach(row => {
      const item = payload.items[Number(row.dataset.pcItem)];
      item.publish_title = row.querySelector('[data-pc-title]').value;
      item.publish_body = row.querySelector('[data-pc-body]').value;
      item.topics = row.querySelector('[data-pc-topics]').value.split(/\s+/).map(t => t.replace(/^#/, '')).filter(Boolean);
      if (state.mode !== 'mix') item.production_headlines = Array.from(row.querySelectorAll('[data-pc-headline]')).map((h, hi) => {
        const ids = Array.from(h.querySelectorAll('[data-pc-unit]:checked')).map(el => el.dataset.pcUnit);
        const text = h.querySelector('[data-pc-headline-text]').value;
        const original = state.draft.payload.items[Number(row.dataset.pcItem)].production_headlines[hi];
        const unchanged = original && text === original.text && JSON.stringify(ids) === JSON.stringify(original.source_unit_ids);
        return { order: hi + 1, text, source_unit_ids: ids, mapping_kind: unchanged ? original.mapping_kind : ids.length > 1 ? 'merge' : 'condense' };
      });
    });
    return payload;
  }
  async function save({reload = true} = {}) {
    const payload = collect();
    const result = await api(url + '/edit', { method: 'POST', body: JSON.stringify({ draft_ref: state.draft.ref, payload }) });
    if (result.result.sha256 !== state.draft.ref.sha256) state.confirmed = false;
    // The Native writer already validated this exact payload. Retain its ref
    // even if the subsequent confirmation response is lost; explicit recovery
    // must continue the saved version instead of resubmitting an older ref.
    state.draft = { ref: result.result, payload };
    if (reload) await refresh(); return result.result;
  }
  async function track(result) {
    if (result.task && ['queued', 'running'].includes(result.task.status)) {
      state.tasks = [result.task, ...(state.tasks || []).filter(task => task.task_id !== result.task.task_id)];
      render(); pollActiveTask(); return;
    }
    await refresh();
  }
  async function generate(retry, targetIds) {
    await track(await api(url + '/generate', { method: 'POST', body: JSON.stringify({
      ...(targetIds ? { target_ids: targetIds } : {}), ...(retry ? { expected_parent: state.attempt_ref,
        retry_confirmation: 'explicit_retry_possible_additional_cost' } : {}),
    }) }));
  }
  await refresh();
}
