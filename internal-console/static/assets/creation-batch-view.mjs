import { escapeHtml } from './list-ui.mjs?v=case-share-ux2';
import { createBatchReviewDraft, batchDeliveryScope } from './creation-batch-draft.mjs?v=batch-workspace-1';

const labels = { persona: '人设型', story: '故事型', conversion: '高转化型' };
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const display = value => count(value) === null ? '—' : String(value);

export function batchProgressSummary(projection) {
  const counts = projection.counts || {};
  const full = projection.control !== 'end' && projection.completion_proven === true && count(counts.target) > 0 &&
    counts.delivered === counts.target && counts.unknown === 0 && counts.failed === 0;
  const ended = projection.control === 'end';
  const status = full ? '整批交付已完成' : ended ? '本批已结束，保留已有成果' :
    projection.control === 'pause' ? '已暂停后续生成' : counts.unknown > 0 ? '有执行结果需要核对' :
    projection.status === 'generating' ? '正在逐次创作' :
    projection.status === 'awaiting_review' ? '生成已完成，等待人工审核' :
    projection.status === 'generation_finished_with_gaps' ? '生成告一段落，仍有数量差额' :
    projection.status === 'awaiting_publish_confirmation' ? '等待确认发布文案' :
    projection.status === 'preparing_publish_copy' ? '正在准备发布文案' :
    projection.status === 'preparing_delivery' ? '正在准备交付' :
    projection.status === 'ready_for_delivery' ? '可以汇总本批交付' :
    projection.status === 'needs_attention' ? '有项目需要处理' : '正在准备本批创作';
  return { full, ended, status, counts };
}

export function batchWorkflow(projection) {
  const { full, counts: c } = batchProgressSummary(projection);
  const legal = deliveryReadySlots(projection).length;
  const files = (projection.deliveries?.completed || []).some(v => v.is_current && v.files?.length);
  const publishing = (projection.groups || []).filter(g => g.approved > 0 || (g.slots || []).some(s => s.approved)).map(g => g.publish);
  const publishPending = publishing.some(p => p?.confirmed !== true);
  const blocked = projection.verification_deferred || c.unknown > 0 || c.unverified > 0 ||
    ['needs_attention', 'needs_recovery'].includes(projection.status);
  const reviewable = !projection.verification_deferred &&
    (projection.generation_quiescent === true || projection.control === 'end');
  let current = 0, action = null, label = '正在生成，请稍候', detail = '系统按安全容量逐次生成，完成后进入人工审核。';
  if (full) {
    current = 3; action = 'download'; label = '下载 Excel';
    detail = '本批正式交付已完成，可以下载分类 Excel。';
  } else if (blocked) {
    action = 'inspect'; label = '查看待处理项目';
    detail = '当前有结果或资格需要核对；不会自动重发未知调用，也不会跳过审核。';
    if (projection.verification_deferred) { action = null; label = '正在生成并核对状态'; }
  } else if (reviewable && (c.review_pending > 0 || projection.status === 'awaiting_review')) {
    current = 1; action = 'batch-review-content'; label = '开始内容审核';
    detail = `已生成 ${display(c.generated)} 条，待人工审核 ${display(c.review_pending ?? c.generated)} 条。请逐条阅读并明确决定。`;
  } else if (projection.publish_copy_enabled && (publishPending || ['preparing_publish_copy', 'awaiting_publish_confirmation'].includes(projection.status))) {
    current = 2;
    if (projection.status === 'awaiting_publish_confirmation' || publishing.some(p => p?.draft && p.confirmed !== true)) { action = 'batch-review-publish'; label = '确认发布内容'; }
    else label = '正在生成发布文案';
    detail = '内容审核通过后，仍须人工核对发布标题、正文和话题，再确认准确版本。';
  } else if (projection.publish_copy_enabled && (legal || files || ['preparing_delivery', 'ready_for_delivery'].includes(projection.status))) {
    current = 3; action = files ? 'download' : legal ? 'batch-delivery-preview' : null;
    label = files ? '下载 Excel' : legal ? '核对并生成 Excel' : '正在准备 Excel 交付';
    detail = files ? '已有部分交付可下载，剩余目标仍保留。' : legal ? `当前 ${legal} 条具备正式交付条件，请核对汇总范围后生成文件。` : '正在准备原生交付与分类汇总，完成后开放下载。';
  } else if (reviewable && c.generated > 0) {
    current = 1; action = 'batch-review-content'; label = '查看内容审核';
    detail = c.review_pending === 0 ? '已生成内容的审核已处理，当前没有可继续交付的批准内容。' : '已有生成结果可核对；数量差额保留，不会自动补量。';
  } else if (projection.control === 'pause' || projection.control === 'end') {
    action = projection.control === 'pause' ? 'batch-resume' : 'inspect';
    label = projection.control === 'pause' ? '继续本批生成' : '查看保留成果';
    detail = '已有成果和数量差额会保留；暂停或结束不等于全部完成。';
  }
  const names = ['生成', '内容审核', '发布确认', 'Excel下载'];
  const steps = names.map((name, index) => ({ name, state: index < current ? 'done' : index === current ? 'current' : 'waiting',
    status: index < current ? '已完成' : index === current ? (full ? '已完成' : files && current === 3 ? '部分可下载' : '当前步骤') : '待进行' }));
  if (current > 0 && c.missing_generation > 0) steps[0].status = `已告一段落 · 差 ${display(c.missing_generation)} 条`;
  if (!projection.publish_copy_enabled) steps[2].status = steps[3].status = '当前未开放';
  return { current, action, label, detail, steps };
}

export function nativeCreationUrl(group, businessId) {
  const query = new URLSearchParams({ request_id: group.request_id, business_id: businessId });
  const kind = group.source_kind || group.native?.mode;
  if (group.profile === 'mix') query.set('profile', 'mix');
  if (group.profile === 'news' && ['novel_content', 'cross_profile_repurpose'].includes(kind)) {
    query.set('profile', 'news'); query.set('news_mode', kind);
  }
  return '/create?' + query;
}

export function batchHistoryMarkup(value) {
  const esc = escapeHtml;
  if (!value || !Array.isArray(value.batches)) return '<section class="work-surface"><h2>我的创作批次</h2><p>批次记录暂时无法可靠读取，请稍后刷新。</p></section>';
  const stages = { launch: '快速起号期', trust: '信任积累期', steady: '稳定转化期' };
  return `<section class="work-surface batch-history"><h2>我的创作批次</h2>
    ${value.blocked?.length ? '<p>有批次记录需要核对原始来源；现有材料会保留。</p>' : ''}
    ${value.batches.length ? value.batches.map(b => `<article class="batch-history-item"><div><h3>${esc(b.mode === 'free' ? '自由组合' : stages[b.operating_stage] || '按阶段创作')}</h3>
      <p>已确认本批配置 · 目标 ${display(b.actual_target)} 条${b.control === 'end' ? ' · 已结束本批' : b.control === 'pause' ? ' · 已暂停后续工作' : ''}</p></div>
      <a class="btn btn-secondary" href="/create/batch?batch_id=${encodeURIComponent(b.batch_id)}" data-route>查看进度、审核与交付</a></article>`).join('') : '<p>本账号还没有确认过创作批次。</p>'}
    </section>`;
}


export function batchIdentity(projection, data = null) {
  const native = (projection.groups || []).map(g => g.native).filter(n => n && n.business_id === projection.business_id);
  let customer = native.find(n => n.business_display_name)?.business_display_name || '';
  let speaker = native.find(n => n.speaker_display_name)?.speaker_display_name || '';
  if (data?.customer_context?.business_id === projection.business_id && (data.customers || []).length <= 1 &&
      !(data.customers || []).some(c => c.business_id !== projection.business_id)) {
    customer ||= data.customers?.[0]?.display_name || data.customer_context.display_name || '';
    const ids = [...new Set(native.map(n => n.speaker_id).filter(Boolean))];
    if (ids.length === 1) speaker ||= data.customers?.[0]?.speakers?.find(s => s.speaker_id === ids[0])?.display_name || '';
  }
  return { customer, speaker };
}

export function availableBatchPhases(projection) {
  const flow = batchWorkflow(projection);
  const review = !projection.verification_deferred && (projection.generation_quiescent === true || projection.control === 'end');
  return [true, review || flow.current > 1,
    !!projection.publish_copy_enabled && (flow.current >= 2 || (projection.groups || []).some(g => g.publish?.draft)),
    !!projection.publish_copy_enabled && (flow.current >= 3 || deliveryReadySlots(projection).length > 0 || !!projection.deliveries?.completed?.length)];
}

const typeLabel = group => labels[group.style_id] || (group.source_kind === 'novel_content' || group.native?.mode === 'novel_content'
  ? '新闻体 · 新创作' : group.source_kind === 'cross_profile_repurpose' || group.native?.mode === 'cross_profile_repurpose'
    ? '新闻体 · 改编已有内容' : '新闻体 · 来源待核对');

export function batchContentRows(projection, preview = null, phase = 1) {
  const offered = new Map((preview?.items || []).map(item => [item.slot_id, item]));
  return (projection.groups || []).flatMap(group => (group.slots || []).map(slot => {
    const item = offered.get(slot.slot_id);
    const status = slot.unknown ? '结果待核对' : slot.verification_pending ? '核对中' : slot.delivered ? '已交付' :
      phase === 2 && slot.approved ? (group.publish?.confirmed ? '已确认发布' : item ? '待发布确认' : '准备发布文案') :
      slot.approved ? '已通过审核' : slot.rejected ? '未采用' : slot.generated ? '待内容审核' :
      slot.generation_failed ? '生成失败' : group.stage === 'not_admitted' ? '尚未开始' : '处理中';
    const title = item?.display?.title || item?.display?.publish_title || item?.display?.source_title ||
      (item?.display?.beats ? (item.display.beats[0]?.title || item.display.beats[0]?.headline || item.display.beats[0]?.text || item.display.beats[0]?.narration) : '');
    return { slot, group, item, status, type: typeLabel(group), title: title || typeLabel(group) };
  }));
}

export function batchDetailMarkup(projection, identity = batchIdentity(projection)) {
  const { counts: c, ended, full, status } = batchProgressSummary(projection), flow = batchWorkflow(projection), esc = escapeHtml;
  const allowed = availableBatchPhases(projection);
  const rows = (projection.groups || []).map(group => `<li><strong>${esc(typeLabel(group))}</strong> · 目标 ${display(group.target)} 条 · 已生成 ${display(group.generated)} 条
    ${group.unknown ? '<p>执行结果待核对，不会自动重发。</p>' : ''}
    ${group.admitted || group.native ? `<a href="${esc(nativeCreationUrl(group, projection.business_id))}">查看原始内容与恢复</a>` : ''}</li>`).join('');
  return `<main class="page batch-progress-page batch-workspace-page">
    <a class="back-link" href="/customers/${encodeURIComponent(projection.business_id)}/content" data-route>← 返回客户</a>
    <header class="batch-workspace-heading"><div><h1>本次创作 <span>${display(c.target)} 条</span></h1>
      <p id="batch-identity">${esc([identity.customer, identity.speaker].filter(Boolean).join(' · ') || '客户创作')}</p></div>
      <div class="batch-header-status"><span>${esc(status)}</span><button class="btn btn-secondary" id="batch-refresh">刷新</button></div></header>
    <nav class="batch-phase-nav" role="tablist" aria-label="创作交付步骤">${flow.steps.map((step, i) => `<button id="batch-phase-${i}" role="tab" data-batch-phase="${i}"
      aria-selected="${i === flow.current}" ${i === flow.current ? 'aria-current="step"' : ''} ${allowed[i] ? '' : 'disabled'}
      title="${allowed[i] ? step.name : '完成前面的必要步骤后开放'}"><span aria-hidden="true">${step.state === 'done' ? '✓' : i + 1}</span>${esc(step.name)}</button>`).join('')}</nav>
    <p id="batch-progress-message" role="status"></p>
    ${ended ? '<p class="batch-workspace-notice">本批已结束，保留已有成果和数量差额；本批结束不等于整批完成。</p>' : ''}
    ${c.unknown > 0 ? '<p class="batch-workspace-notice">有执行结果待核对。请处理对应内容，系统不会自动重发。</p>' : ''}
    ${c.missing_generation > 0 && projection.generation_quiescent ? `<p class="batch-workspace-notice">生成已告一段落，仍差 ${display(c.missing_generation)} 条；已有合法成果可以继续处理。</p>` : ''}
    <section id="batch-workspace" role="tabpanel" aria-labelledby="batch-phase-${flow.current}"></section>
    <details class="batch-more"><summary>更多 · 批次管理与记录</summary>
      <dl class="batch-detail-metrics"><div><dt>本批目标</dt><dd>${display(c.target)}</dd></div><div><dt>已生成</dt><dd>${projection.verification_deferred ? '核对中' : display(c.generated)}</dd></div>
      <div><dt>已批准</dt><dd>${projection.verification_deferred ? '核对中' : display(c.approved)}</dd></div><div><dt>已交付</dt><dd>${display(c.delivered)}</dd></div>
      <div><dt>已登记新增内容</dt><dd>${display(c.new_semantic_count)}</dd></div><div><dt>已登记重新表达</dt><dd>${display(c.repurpose_presentation_count)}</dd></div></dl>
      <p>生成、人工批准和交付分别计数。新增内容与改编呈现以原交付记录为准。</p>
      <div class="batch-management-actions">${!ended && !full && projection.generation_quiescent !== true ?
        projection.control === 'pause' ? '<button class="btn btn-secondary" id="batch-resume">继续后续生成</button>' : '<button class="btn btn-secondary" id="batch-pause">暂停后续生成</button>' : ''}
      ${!ended && !full ? '<button class="btn btn-secondary" id="batch-end">提前结束本批</button>' : ''}
      <button class="btn btn-secondary" id="batch-review-history">查看已提交操作</button></div>
      <div id="batch-history-panel"></div><ul id="batch-native-items">${rows}</ul></details></main>`;
}

export function deliveryReadySlots(projection) {
  return (projection.groups || []).flatMap(group => {
    const publish=group.publish, reference=publish?.draft?.ref, parent=publish?.delivery?.draft_ref;
    if (publish?.confirmed !== true || !reference || !parent || reference.path !== parent.path || reference.sha256 !== parent.sha256) return [];
    return (group.slots || []).filter(slot => slot.approved && slot.native_exported && !slot.unknown && !slot.verification_pending);
  });
}

function itemText(item) {
  const d = item.display, esc = escapeHtml;
  if (item.native_kind && d.beats) return `<div class="batch-news-beats">${d.beats.map((beat, i) => `<section><span class="eyebrow">信息段 ${i + 1}</span>
    ${beat.title || beat.headline ? `<h3>${esc(beat.title || beat.headline)}</h3>` : ''}<p class="batch-review-text">${esc(beat.narration || beat.text || beat.copy || '')}</p></section>`).join('')}</div>`;
  return `<h3>${esc(d.title || '')}</h3><p class="batch-review-text">${esc(d.narration || '')}</p>`;
}

export function humanReviewMarkup(preview, projection = null, { activeSlot = '', choices = [], pending = false } = {}) {
  const items = preview.items || [], index = Math.max(0, items.findIndex(item => item.slot_id === activeSlot)), item = items[index];
  if (!item) return '<p>当前没有待提交的合法审核内容。已有审核结果会保留。</p>';
  const esc = escapeHtml, d = item.display, publish = preview.scope === 'publish_copy_confirmation';
  const group = projection?.groups?.find(g => g.slots?.some(s => s.slot_id === item.slot_id));
  const style = d.style_id || group?.style_id, choice = choices[index];
  const content = publish ? `<h3>${esc(d.title || d.publish_title || '')}</h3>
    ${(d.production_headlines || []).length ? `<details><summary>视频制作短标题</summary>${d.production_headlines.map(h => `<p>${esc(h.text)}</p>`).join('')}</details>` : ''}
    <p class="batch-review-text"><strong>发布正文</strong><br>${esc(d.body || d.publish_body || '')}</p><p><strong>话题</strong> ${esc((d.topics || []).join(' '))}</p>` : itemText(item);
  return `<article class="batch-review-card"><p class="eyebrow">第 ${index + 1} 条 · ${esc(labels[style] || (item.native_kind === 'mix' ? 'Mix' : item.native_kind === 'cross_profile_repurpose' ? '新闻体 · 改编已有内容' : '新闻体 · 新创作'))}</p>
    ${d.source_title ? `<p class="batch-source-title">原内容：${esc(d.source_title)}</p>` : ''}<div id="batch-review-title" tabindex="-1">${content}</div>
    <div class="batch-item-decisions" role="group" aria-label="本条${publish ? '发布版本选择' : '审核选择'}">
    ${publish ? `<button class="btn btn-secondary" data-review-choice="confirm" aria-pressed="${choice === true}" ${pending ? 'disabled' : ''}>选择此发布版本</button>` :
      `<button class="btn btn-secondary" data-review-choice="approve" aria-pressed="${choice === 'approve'}" ${pending ? 'disabled' : ''}>通过</button>
       ${item.native_kind === 'mix' ? `<button class="btn btn-secondary" data-review-choice="reject" aria-pressed="${choice === 'reject'}" ${pending ? 'disabled' : ''}>不采用</button>` : ''}`}
    ${group ? `<a class="btn btn-secondary" href="${esc(nativeCreationUrl(group, projection.business_id))}">查看/修改</a>` : ''}</div>
    <p class="batch-choice-note">${choice ? '已作待提交选择，尚未生效。' : '尚未选择。请阅读内容后作出决定。'}${!publish && item.native_kind !== 'mix' ? '需要修改或分段处理时，请进入原内容流程。' : ''}</p></article>`;
}

function deliveryFilesMarkup(projection) {
  return (projection.deliveries?.completed || []).map(version => `<article class="batch-delivery-version"><h3>${version.is_current ? '当前交付' : '历史交付'} · ${display(version.delivered)} 条</h3>
    <p>${version.scope === 'complete_target' ? '整批范围' : '部分交付'} · 目标差额 ${display(version.shortfall)} 条</p>
    <div class="batch-file-links">${(version.files || []).map(f => `<a class="btn btn-secondary" href="/api/create/batches/${encodeURIComponent(projection.batch_id)}/deliveries/${encodeURIComponent(version.delivery_id)}/${encodeURIComponent(f.profile)}">下载${f.profile === 'news' ? '新闻' : 'Mix'} Excel</a>`).join('')}</div></article>`).join('');
}

export function batchWorkspaceMarkup(projection, ui) {
  const c = projection.counts, esc = escapeHtml, phase = ui.phase, preview = ui.preview;
  const rows = batchContentRows(projection, preview, phase), active = rows.find(row => row.slot.slot_id === ui.activeSlot) || rows[0];
  if (phase === 0) return `<div class="batch-workspace-bar"><h2>生成进度</h2><span>已生成 ${projection.verification_deferred ? '核对中' : display(c.generated)} / ${display(c.target)} 条</span></div>
    <div class="batch-generation-list">${rows.map((row, index) => `<article><strong>${index + 1}. ${esc(row.type)}</strong><span>${esc(row.status)}</span>
      ${row.slot.unknown || row.slot.generation_failed || row.group.stage === 'source_blocked' ? `<p>本项需要核对原始来源或执行结果。<a href="${esc(nativeCreationUrl(row.group, projection.business_id))}">查看并处理</a></p>` : ''}</article>`).join('')}</div>
    <p class="batch-choice-note">处理进度会自动更新，可以离开后返回。未知结果不会自动重发。</p>`;
  if (phase === 3) {
    const legal = deliveryReadySlots(projection), files = deliveryFilesMarkup(projection), pre = ui.deliveryPreview;
    return `<div class="batch-workspace-bar"><h2>Excel下载</h2><span>已交付 ${display(c.delivered)} / ${display(c.target)} 条</span></div>
      ${files || '<p>尚无已完成的分类文件。</p>'}
      ${projection.status === 'preparing_delivery' ? '<p role="status">正在准备 Excel，完成后会自动更新。无需重复提交。</p>' : ''}
      <div id="batch-excel-section">${ui.loading ? '<p role="status">正在核对可交付范围…</p>' : ui.error ? `<p role="alert">${esc(ui.error)}</p><button class="btn btn-secondary" data-workspace-retry>重新核对</button>` : pre ?
        `<div class="batch-delivery-scope"><h3>本次交付 ${display(pre.delivered ?? legal.length)} 条</h3><p>目标 ${display(c.target)} 条 · 差额 ${display(pre.shortfall)} 条</p>
        <ul>${(pre.files || []).map(f => `<li>${f.profile === 'news' ? '新闻体' : 'Mix'} Excel · ${display(f.rows)} 条</li>`).join('')}</ul>
        <p class="batch-choice-note">只包含已批准内容及已确认发布的准确版本。</p></div>` : !files ? '<p>完成内容审核、发布确认及原生交付准备后，在这里下载分类 Excel。</p>' : ''}</div>
      ${ui.pendingExport ? '<p class="batch-workspace-notice">有一次已提交的汇总操作尚待确认。重试会沿用原范围和身份。</p>' : ''}
      ${pre || ui.pendingExport ? `<footer class="batch-workspace-footer"><span>${ui.pendingExport ? '保留原汇总操作' : '范围已核对，等待明确确认'}</span><button class="btn btn-primary" data-workspace-submit ${ui.writing ? 'disabled' : ''}>${ui.writing ? '正在提交…' : ui.pendingExport ? '重试上次汇总' : '生成分类 Excel'}</button></footer>` : ''}`;
  }
  const publish = phase === 2, selected = (ui.choices || []).filter(Boolean).length;
  const label = publish ? '发布确认' : '内容审核';
  const queue = rows.map((row, index) => {
    const i = preview?.items.findIndex(item => item.slot_id === row.slot.slot_id) ?? -1;
    const choice = i >= 0 && ui.choices?.[i];
    const status = choice === true ? '待提交发布确认' : choice === 'approve' ? '拟通过 · 待提交' : choice === 'reject' ? '拟不采用 · 待提交' : row.status;
    return `<button data-review-slot="${esc(row.slot.slot_id)}" aria-pressed="${row === active}"><span>${index + 1}. ${esc(row.type)}</span><small>${esc(row.title)}</small><em>${esc(status)}</em></button>`;
  }).join('');
  let validation = '';
  if (selected && preview) { try { humanCommand(preview, ui.choices, projection, 'validate_only'); } catch (error) { validation = error.message; } }
  const body = ui.loading ? '<p role="status">正在读取当前内容…</p>' : ui.error ? `<p role="alert">${esc(ui.error)}</p><button class="btn btn-secondary" data-workspace-retry>重新读取内容</button>` :
    active?.item && preview ? humanReviewMarkup(preview, projection, {activeSlot:active.slot.slot_id,choices:ui.choices,pending:!!ui.pendingHuman || ui.writing}) :
      `<article class="batch-review-card"><h3>${esc(active?.type || label)}</h3><p>${esc(active?.status || '暂时没有可处理内容')}</p>
      <p>${publish ? '已确认的发布版本继续生效；新的待确认文案准备好后会显示在这里。' : '已有审核结果继续生效；未具备资格的内容不能在这里批准。'}</p>
      ${active ? `<a class="btn btn-secondary" href="${esc(nativeCreationUrl(active.group, projection.business_id))}">查看原始内容与记录</a>` : ''}</article>`;
  const activeIndex = Math.max(0, rows.indexOf(active));
  return `<div class="batch-workspace-bar"><h2>${label}</h2><span>${publish ? `待确认 ${preview?.items.length ?? '—'}` : `待审核 ${display(c.review_pending)}`} 条${!publish ? ` · 已审核 ${display((c.approved || 0) + (c.rejected || 0))} 条` : ''}</span></div>
    ${preview?.excluded?.length ? `<p class="batch-workspace-notice">有 ${preview.excluded.length} 项暂不能${publish ? '确认发布' : '审核'}，请在对应内容中处理。</p>` : ''}
    <div class="batch-review-workspace"><nav class="batch-review-queue" aria-label="内容列表">${queue}</nav>
      <div class="batch-active-content"><details class="batch-mobile-queue"><summary>切换内容（${rows.length} 条）</summary><nav aria-label="切换审核内容">${queue}</nav></details>
        ${body}<div class="batch-item-navigation"><button class="btn btn-secondary" data-review-offset="-1" ${activeIndex === 0 ? 'disabled' : ''}>上一条</button><span>${rows.length ? activeIndex + 1 : 0} / ${rows.length}</span><button class="btn btn-secondary" data-review-offset="1" ${activeIndex >= rows.length - 1 ? 'disabled' : ''}>下一条</button></div></div></div>
    <footer class="batch-workspace-footer"><div><strong>${ui.pendingHuman ? '有上次提交需要继续核对' : `已选择 ${selected} / ${preview?.items.length ?? 0} 条`}</strong>
      <small>${esc(validation || (ui.pendingHuman ? '沿用已提交的准确来源与决定' : '选择尚未生效，提交后由原生流程核验'))}</small></div>
      <button class="btn btn-primary" data-workspace-submit ${ui.writing || !ui.pendingHuman && (!selected || !!validation || ui.loading || !!ui.error) ? 'disabled' : ''}>${ui.writing ? '正在提交…' : ui.pendingHuman ? '继续上次提交' : publish ? '确认发布内容' : '提交审核结果'}</button></footer>`;
}

export function humanCommand(preview, selections, projection, operationId) {
  const selected = preview.items.flatMap((item, index) => {
    const decision = selections[index];
    if (!decision) return [];
    const { display: _display, ...source } = item;
    if (preview.scope === 'publish_copy_confirmation') {
      if (decision !== true) throw Error('请明确确认发布版本。');
      return [{ ...source, action: 'confirm' }];
    }
    if (!['approve', 'reject'].includes(decision) || item.native_kind !== 'mix' && decision === 'reject') throw Error('请使用对应内容的原生审核入口处理此决定。');
    return [{ ...source, decision }];
  });
  if (!selected.length) throw Error('请至少明确选择一条内容。');
  const chosen = new Set(selected.map(i => i.slot_id));
  for (const group of projection.groups) {
    const offered = preview.items.filter(i => (group.slots || []).some(s => s.slot_id === i.slot_id));
    if (offered.some(i => chosen.has(i.slot_id)) && offered.some(i => !chosen.has(i.slot_id))) throw Error('请为同一内容组内每条已生成内容作出明确决定。');
  }
  return { scope: preview.scope, items: selected, source_sha256: preview.source_sha256, operation_id: operationId };
}

export function createBatchControls(api, batchId, operationId = () => 'batch_control_' + crypto.randomUUID().replaceAll('-', '')) {
  let busy = false, pending = null;
  return async action => {
    if (!['pause', 'resume', 'end'].includes(action)) throw Error('未知批次操作');
    if (busy) return null;
    busy = true;
    if (!pending || pending.action !== action) pending = { action, operation_id: operationId() };
    try {
      const result = await api(`/api/create/batches/${encodeURIComponent(batchId)}/control`, {
        method: 'POST', body: JSON.stringify(pending),
      });
      pending = null;
      return result;
    } finally { busy = false; }
  };
}

export async function continueHumanCommand(post, body, isCurrent, onProgress = () => {}) {
  let response, previousDeferred = Infinity;
  for (let pass = 0; pass < 12 && isCurrent(); pass += 1) {
    response = await post('human-command', body);
    if (!isCurrent() || response.result.all_native_completed || !response.result.continuation_needed) break;
    const deferred = response.result.results.filter(value => value.deferred).length;
    if (!deferred || deferred >= previousDeferred) break;
    previousDeferred = deferred; onProgress(deferred);
  }
  return response;
}


export function createCreationBatchViews({ app, api, shell, bindCommonActions, skeletonPage, renderLoadError }) {
  let generation = 0, shownBatch = null;
  const controlsByBatch = new Map();
  async function renderBatch({ follow = false, notice = '' } = {}) {
    const readStarted = Date.now();
    const version = ++generation, route = window.location.href;
    const current = () => version === generation && window.location.href === route;
    const batchId = new URLSearchParams(window.location.search).get('batch_id');
    if (!batchId) {
      app.innerHTML = shell('本批创作', '<main class="page"><h1>请选择已有创作批次</h1><a href="/customers" data-route>返回客户列表</a></main>');
      bindCommonActions(); return;
    }
    if (shownBatch !== batchId) skeletonPage('读取本批创作');
    const scroll = shownBatch === batchId ? window.scrollY : 0;
    try {
      const response = await api(`/api/create/batches/${encodeURIComponent(batchId)}`);
      if (!current()) return;
      const projection = response.state;
      if (projection?.batch_id !== batchId) throw Error('本批创作身份无法对应，请重新进入。');
      const flow = batchWorkflow(projection), allowed = availableBatchPhases(projection);
      const draft = createBatchReviewDraft(sessionStorage, batchId), position = draft.position();
      const phase = !follow && Number.isInteger(position?.phase) && allowed[position.phase] &&
        !(position.phase === position.current && flow.current !== position.current) ? position.phase : flow.current;
      const safeRead = key => { try { return JSON.parse(sessionStorage.getItem(key) || 'null'); } catch { return null; } };
      const safeWrite = (key, value) => { try { if (value) sessionStorage.setItem(key, JSON.stringify(value)); else sessionStorage.removeItem(key); } catch { /* Native idempotency still protects the request. */ } };
      const pendingKey = `creation-batch-human:${batchId}`, exportKey = `creation-batch-export:${batchId}`;
      const ui = { phase, activeSlot:position?.activeSlot || '', preview:null, choices:[], loading:false, error:'', writing:false,
        pendingHuman:safeRead(pendingKey),pendingExport:safeRead(exportKey),deliveryPreview:null };
      if (ui.pendingHuman) ui.phase = ui.pendingHuman.scope === 'publish_copy_confirmation' && allowed[2] ? 2 : allowed[1] ? 1 : phase;
      app.innerHTML = shell('本批创作', batchDetailMarkup(projection)); bindCommonActions(); shownBatch = batchId;
      const workspace = document.getElementById('batch-workspace');
      const message = text => { if (current()) document.getElementById('batch-progress-message').textContent = text; };
      const post = (suffix, body) => api(`/api/create/batches/${encodeURIComponent(batchId)}/${suffix}`, {method:'POST',body:JSON.stringify(body)});
      if (!controlsByBatch.has(batchId)) controlsByBatch.set(batchId, createBatchControls(api, batchId));
      let loadVersion = 0;
      function draw() {
        if (!current()) return;
        const rows = batchContentRows(projection, ui.preview, ui.phase);
        if (!rows.some(row => row.slot.slot_id === ui.activeSlot)) ui.activeSlot = ui.preview?.items[0]?.slot_id || rows[0]?.slot.slot_id || '';
        workspace.setAttribute('aria-labelledby', `batch-phase-${ui.phase}`);
        workspace.innerHTML = batchWorkspaceMarkup(projection, ui);
        document.querySelectorAll('[data-batch-phase]').forEach(button => { button.setAttribute('aria-selected', String(Number(button.dataset.batchPhase) === ui.phase)); });
        draft.position({phase:ui.phase,current:flow.current,activeSlot:ui.activeSlot});
      }
      async function loadWorkspace() {
        const readVersion = ++loadVersion, phase = ui.phase;
        ui.error = ''; ui.preview = null; ui.choices = []; ui.deliveryPreview = null;
        if (phase === 0) { ui.loading = false; draw(); return; }
        ui.loading = true; draw();
        const fresh = () => current() && readVersion === loadVersion && phase === ui.phase;
        try {
          if (phase === 1 || phase === 2) {
            const scope = phase === 1 ? 'native_content_review' : 'publish_copy_confirmation';
            const response = await api(`/api/create/batches/${encodeURIComponent(batchId)}/human-options?scope=${scope}`);
            if (!fresh()) return;
            const preview = response.preview, ids = new Set((projection.groups || []).flatMap(g => (g.slots || []).map(s => s.slot_id)));
            if (preview?.batch_id !== batchId || preview.scope !== scope || !Array.isArray(preview.items) ||
                !/^[a-f0-9]{64}$/.test(preview.source_sha256 || '') || new Set(preview.items.map(i => i.slot_id)).size !== preview.items.length || preview.items.some(i => !ids.has(i.slot_id))) {
              throw Error('审核内容的批次或版本无法对应，请重新读取。');
            }
            const saved = draft.restore(preview);
            ui.preview = preview; ui.choices = saved.choices;
            if (saved.activeSlot && !saved.invalidated) ui.activeSlot = saved.activeSlot;
            if ((saved.invalidated || !saved.activeSlot) && preview.items.length && !preview.items.some(item => item.slot_id === ui.activeSlot)) ui.activeSlot = preview.items[0].slot_id;
            if (saved.invalidated) {
              draft.clear(scope);
              message('内容版本或审核范围已变化，未提交选择已清除，请重新核对；已提交结果仍保留。');
            }
          } else {
            const legal = deliveryReadySlots(projection);
            const already = (projection.deliveries?.completed || []).some(v => v.is_current && v.slot_ids?.length === legal.length && legal.every(s => v.slot_ids.includes(s.slot_id)));
            if (legal.length && !already && !ui.pendingExport && projection.status !== 'preparing_delivery') {
              const scope = batchDeliveryScope(projection, legal);
              const response = await post('delivery-preview', scope);
              if (!fresh()) return;
              const pre = response.preview;
              if (!/^[a-f0-9]{64}$/.test(pre?.source_sha256 || '') || pre.scope !== scope.scope ||
                  JSON.stringify(pre.slot_ids) !== JSON.stringify(scope.slot_ids) || pre.delivered !== legal.length ||
                  pre.target !== projection.counts.target || pre.shortfall !== pre.target - pre.delivered) {
                throw Error('交付范围版本无法对应，请重新核对。');
              }
              ui.deliveryPreview = response.preview;
            }
          }
        } catch (error) { if (fresh()) ui.error = error.message || '当前内容无法读取，请重新核对。'; }
        finally { if (fresh()) { ui.loading = false; draw(); } }
      }
      async function submitHuman(body) {
        if (ui.writing || !current()) return;
        ui.writing = true; ui.pendingHuman = body; safeWrite(pendingKey, body); draw(); message('正在提交本次明确决定…');
        try {
          const response = await continueHumanCommand(post, body, current, remaining => message(`正在继续原提交，尚有 ${remaining} 组；已完成决定保留。`));
          if (!current()) return;
          if (response.result.all_native_completed) {
            safeWrite(pendingKey, null); draft.clear(body.scope);
            message(body.scope === 'publish_copy_confirmation'
              ? '本次发布确认已保存，正在核对交付准备状态…'
              : '本次审核结果已保存，正在核对发布准备状态…');
            await renderBatch({follow:true,notice:'本次提交已由原生流程核验，已完成结果会保留。'});
          } else message('部分决定需要处理。可明确继续上次提交，或查看对应内容；不会替换原决定。');
        } catch (error) {
          if (!current()) return;
          if (['CREATION_BATCH_REVIEW_PREFLIGHT_STALE','CREATION_BATCH_REVIEW_SOURCE_CHANGED','CREATION_BATCH_NATIVE_REVIEW_INCOMPLETE','CREATION_BATCH_REVIEW_SCOPE_INVALID'].includes(error.detail?.code)) {
            safeWrite(pendingKey,null); draft.clear(body.scope);
            await renderBatch({notice:error.message || '来源或版本已变化，请重新审核；已有结果保留。'}); return;
          }
          message(error.message || '提交结果尚待确认，请保留原决定并继续上次提交。');
        } finally { if (current()) { ui.writing = false; draw(); } }
      }
      async function submitDelivery() {
        if (ui.writing || !current() || !ui.deliveryPreview && !ui.pendingExport) return;
        const body = ui.pendingExport || {...batchDeliveryScope(projection,deliveryReadySlots(projection)),source_sha256:ui.deliveryPreview.source_sha256,
          operation_id:'delivery_' + crypto.randomUUID().replaceAll('-','')};
        safeWrite(exportKey,body); ui.pendingExport = body; ui.writing = true; draw();
        try {
          await post('delivery-export',body);
          if (current()) { safeWrite(exportKey,null); await renderBatch({follow:true,notice:'汇总任务已接收，完成后提供分类 Excel 下载。'}); }
        } catch (error) {
          if (!current()) return;
          if (['COMPOSITE_PREFLIGHT_STALE','CREATION_BATCH_DELIVERY_PREFLIGHT_STALE'].includes(error.detail?.code)) {
            safeWrite(exportKey,null);
            await renderBatch({follow:true,notice:'交付范围或版本已变化，请重新核对并明确确认生成。'});
          } else message(error.message || '汇总结果尚待确认，请沿用原操作重试。');
        }
        finally { if (current()) { ui.writing = false; draw(); } }
      }
      workspace.addEventListener('click', event => {
        const target = event.target.closest('button');
        if (!target || ui.writing || !current()) return;
        if (target.hasAttribute('data-workspace-retry')) { loadWorkspace(); return; }
        if (target.hasAttribute('data-workspace-submit')) {
          if (ui.phase === 3) { submitDelivery(); return; }
          if (ui.pendingHuman) { submitHuman(ui.pendingHuman); return; }
          try { submitHuman(humanCommand(ui.preview,ui.choices,projection,'human_'+crypto.randomUUID().replaceAll('-',''))); }
          catch (error) { message(error.message); }
          return;
        }
        const rows = batchContentRows(projection,ui.preview,ui.phase);
        if (target.hasAttribute('data-review-slot') || target.hasAttribute('data-review-offset')) {
          if (target.hasAttribute('data-review-slot')) ui.activeSlot = target.dataset.reviewSlot;
          else { const index = rows.findIndex(row => row.slot.slot_id === ui.activeSlot); ui.activeSlot = rows[index + Number(target.dataset.reviewOffset)]?.slot.slot_id || ui.activeSlot; }
          if (ui.preview) draft.save(ui.preview,ui.choices,ui.activeSlot);
          draw(); document.getElementById('batch-review-title')?.focus(); return;
        }
        if (target.hasAttribute('data-review-choice') && ui.preview && !ui.pendingHuman) {
          const index = ui.preview.items.findIndex(item => item.slot_id === ui.activeSlot);
          if (index < 0) return;
          const value = target.dataset.reviewChoice === 'confirm' ? true : target.dataset.reviewChoice;
          ui.choices[index] = ui.choices[index] === value ? '' : value;
          draft.save(ui.preview,ui.choices,ui.activeSlot); draw();
          workspace.querySelector(`[data-review-choice="${target.dataset.reviewChoice}"]`)?.focus();
        }
      });
      document.querySelectorAll('[data-batch-phase]').forEach(button => button.addEventListener('click', () => {
        if (ui.writing || !current() || !allowed[Number(button.dataset.batchPhase)]) return;
        ui.phase = Number(button.dataset.batchPhase); loadWorkspace();
      }));
      document.getElementById('batch-refresh').addEventListener('click', () => { if (!ui.writing && current()) renderBatch(); });
      for (const action of ['pause','resume','end']) document.getElementById('batch-'+action)?.addEventListener('click',async()=>{
        if (ui.writing || !current() || action === 'end' && !window.confirm('仅停止尚未派发的工作，已有成果、在途或未知项及差额保留。结束不等于全部完成，确认提前结束？')) return;
        ui.writing = true;
        try { await controlsByBatch.get(batchId)(action); if(current()) await renderBatch({follow:true}); }
        catch(error) { if(current()) message(error.message || '操作尚待核对，请保留已有记录。'); }
        finally { ui.writing = false; }
      });
      document.getElementById('batch-review-history').addEventListener('click',async()=>{
        if(ui.writing || !current()) return;
        try {
          const response=await api(`/api/create/batches/${encodeURIComponent(batchId)}/human-commands`);if(!current())return;
          const panel=document.getElementById('batch-history-panel'),records=response.history.commands;
          panel.innerHTML=records.map((r,i)=>`<p>${r.scope==='native_content_review'?'内容审核':'发布确认'} · ${display(r.items.length)}条 <button class="btn btn-secondary" data-recover-command="${i}">继续原提交</button></p>`).join('') || '<p>暂无已提交操作。</p>';
          if(response.history.blocked.length)panel.insertAdjacentHTML('beforeend','<p>有原操作需进一步恢复，请查看对应内容。</p>');
          panel.querySelectorAll('[data-recover-command]').forEach(button=>button.addEventListener('click',()=>{
            if(ui.writing || !current() || !window.confirm('只继续这次已经提交的来源与决定，确认继续？'))return;
            const {scope,items,operation_id,source_sha256}=records[Number(button.dataset.recoverCommand)];
            submitHuman({scope,items,operation_id,source_sha256});
          }));
        } catch(error) { if(current())message(error.message || '原操作记录暂不可读。'); }
      });
      draw(); message(notice);
      if(scroll && !follow) window.scrollTo(0,scroll);
      if (!batchIdentity(projection).customer) {
        api(`/api/create/options?business_id=${encodeURIComponent(projection.business_id)}`).then(data=>{
          if(current()) { const identity=batchIdentity(projection,data);document.getElementById('batch-identity').textContent=[identity.customer,identity.speaker].filter(Boolean).join(' · ') || '客户创作'; }
        }).catch(()=>{});
      }
      await loadWorkspace();
      const taskActive = task => ['queued','running'].includes(task?.status);
      if (['in_progress','generating','preparing_publish_copy','preparing_delivery'].includes(projection.status) ||
          taskActive(projection.delivery_task) || (projection.groups || []).some(group => (group.tasks || []).some(taskActive))) {
        // Slow Native reads already consumed the polling interval. Do not add
        // another four idle seconds; keep one completed read per polling turn.
        const delay=Math.max(500,4000-Math.max(0,Date.now()-readStarted));
        const poll=()=>{
          if(!current() || ui.writing || ui.pendingHuman || ui.choices.some(Boolean))return;
          if(ui.loading){setTimeout(poll,500);return;}
          renderBatch();
        };
        setTimeout(poll,delay);
      }
    } catch(error) { if(current())renderLoadError('暂时无法读取本批创作',error); }
  }
  return { renderBatch };
}
