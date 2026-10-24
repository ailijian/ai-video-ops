// A display projection only. Every resume still posts the original immutable
// intent to the existing authorization and recovery owners.
export function caseRecovery(detail, operations = []) {
  const attempt = detail.review?.attempt_id;
  return operations.filter(item => !item.progress || item.progress.attempt_id === attempt).map(item => {
    const stage = item.progress?.stage;
    if(detail.review?.approved && stage==='type_pending')return {...item,label:'继续类型与共享',busyLabel:'正在继续原操作…'};
    const stateMatches = item.progress?.sharing_state === detail.sharing_state;
    if (detail.review?.approved && stateMatches && stage === 'publication_pending' && detail.sharing_state === 'approved_only') {
      return {...item, label:'重试共享', busyLabel:'正在重试共享…'};
    }
    if (detail.review?.approved && stateMatches && stage === 'result_pending') {
      return {...item, label:'同步操作结果', busyLabel:'正在同步结果…'};
    }
    if (stage === 'recheck_required' || (detail.review?.approved && item.progress && !stateMatches)) {
      return {...item, label:'核对原操作状态', busyLabel:'正在核对…'};
    }
    return {...item, label:'继续原审核操作', busyLabel:'正在继续…'};
  });
}

export function caseResultPanel(detail, operations, escape, unavailable = false) {
  if (!detail.review?.approved) return '';
  const state = detail.sharing_state;
  const retry = operations.some(item => item.label === '重试共享');
  const sync = operations.some(item => item.label === '同步操作结果');
  const recheck = operations.some(item => item.label === '核对原操作状态');
  let title = detail.sharing_label || '案例已收录';
  let description = detail.sharing_next_action || '正式审核决定已保存。';
  if (state === 'approved_shared') {
    title = '案例已收录并共享';
    description = sync ? '安全展示内容已可见，仅需同步本次操作结果，不会再次发布。' : '平台用户可在共享案例库查看获准展示的内容。';
  } else if (state === 'approved_withdrawn') {
    title = '案例已收录，共享已撤回';
    description = sync ? '共享案例库已停止展示。同步仅保存原操作结果，不会重新公开案例。' : '共享案例库已停止展示，原收录及共享记录保留。';
  } else if (retry) {
    title = '案例已收录，共享暂未完成';
    description = '审核结果已保存，无需再次批准。重试只继续共享步骤。';
  } else if (sync) {
    description = '收录决定已保存，仅需同步本次操作结果，不会重新批准。';
  } else if (recheck) {
    description = '收录决定已保存，原展示确认需要重新核对。系统会检查当前权限和来源，不会自动公开变化后的内容。';
  }
  if (unavailable) description += ' 操作状态暂时无法读取，请刷新页面后再试。';
  const shared = state === 'approved_shared';
  const typeRequired=Boolean(detail.video_type_context?.source?.parent_decision_sha256 || operations.some(item=>item.progress?.stage==='type_pending'));
  const typeDone=Boolean(detail.video_type_context?.current);
  return `<section class="case-result-panel ${shared ? 'is-shared' : ''}" aria-labelledby="case-result-title" tabindex="-1">
    <div class="case-result-heading"><span class="case-result-symbol" aria-hidden="true">${shared ? '✓' : '·'}</span>
      <div><p class="case-result-eyebrow">审核结果</p><h2 id="case-result-title">${escape(title)}</h2></div></div>
    <p class="case-result-description">${escape(description)}</p>
    <ol class="case-result-steps${typeRequired?' has-type':''}" aria-label="案例处理进度"><li class="is-complete">正式收录<span>已完成</span></li>
      ${typeRequired?`<li${typeDone?' class="is-complete"':''}>视频类型<span>${typeDone?(detail.video_type_context.current.record.confirmed_type_id==null?'已明确暂缓':'已确认'):'待核对'}</span></li>`:''}
      <li${shared ? ' class="is-complete"' : ''}>安全共享<span>${shared ? '已完成' : state === 'approved_withdrawn' ? '已撤回' : state === 'approved_reconfirm' || recheck ? '需重新核对' : '尚未完成'}</span></li></ol>
    <div data-case-recovery-slot></div>
    ${unavailable ? '<button class="btn btn-secondary" type="button" data-refresh-case-result>刷新操作状态</button>' : ''}
    <p class="case-result-note">原视频素材使用仍需独立授权。</p></section>`;
}
