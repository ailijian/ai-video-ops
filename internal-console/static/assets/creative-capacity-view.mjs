import { escapeHtml as esc } from './case-components.js?v=flow-closure-2';

const count = value => Number.isSafeInteger(value) && value >= 0 ? value : '待核对';
const reasons = {
  HISTORICAL_CORE_EXPLICIT: '核心信息已在历史内容中明确表达',
  PENDING_NATIVE_RESERVATION: '来源已被其他原生任务预留',
  NOVELTY_UNCERTAIN: '语义新颖性尚不明确',
  NO_ADDITIONAL_APPROVED_OPPORTUNITY_IN_CURRENT_PRICE_SCOPE: '当前价格主题范围内没有更多已批准机会',
  unsupported_no_price_offer_anchor: '缺少该结构要求的价格或优惠锚点',
  capacity_insufficient: '已有内容的信息点不足当前结构要求',
  ALREADY_EXPORTED_SAME_NEWS_PATTERN: '已有相同新闻结构的呈现记录',
  SOURCE_PENDING_NATIVE_REQUEST: '来源已被原生任务占用',
};
const label = code => reasons[code] || '原生资格尚未通过，请重新核对来源与适用范围';
export function capacityMarkup(value, backUrl) {
  if (value.schema_version !== 'creative-capacity-read-projection-v1.0' || value.authority?.authorizes_execution !== false) throw Error('容量说明版本需要重新核对。');
  const n=value.new_semantic_inventory, r=value.new_expression_inventory, g=value.target_gap;
  return `<main class="page capacity-read-page">
    <a href="${esc(backUrl)}" data-route>← 返回创作配置</a><h1>本次创作容量说明</h1>
    <p>依据当前已批准资料、历史表达和原生资格读取。这里不会开始创作，也不会释放已预留的来源。</p>
    <section class="card"><h2>新闻体 · 新语义主题</h2><p>本次目标 <strong>${count(g.news_novel_target)}</strong> 条，当前合格 <strong id="capacity-novel">${count(n.qualified_count)}</strong> 条，新主题缺额 <strong id="capacity-gap">${count(g.novel_shortfall)}</strong> 条。</p>
    <p>当前范围：已批准的价格或优惠主题，不能代表客户所有类型的创作能力。</p><ul>${g.diagnostic_reasons.map(reason=>`<li>${esc(label(reason.code))}${reason.count === null ? '' : `：${count(reason.count)} 项`}</li>`).join('') || '<li>当前目标范围未发现缺口。</li>'}</ul></section>
    <section class="card"><h2>新闻体 · 新表达</h2><p>当前可选择的合法改编来源 <strong id="capacity-repurpose">${count(r.qualified_source_count)}</strong> 条。不会自动补入新创作目标。</p>
    <ul>${r.sources.map(source=>`<li><strong>${esc(source.title)}</strong><p>${source.eligibility === 'eligible' ? '当前可改编' : esc(label(source.blocker_code))} · 已有新闻呈现 ${count(source.presentation_count)} 次</p></li>`).join('') || '<li>尚无可读取的合法历史来源。</li>'}</ul></section>
    <section class="card"><h2>创作结构与人物资格</h2><ul>${value.structure_qualification.map(type=>`<li><strong>${esc({news:'新闻体',persona:'人设型',story:'故事型',conversion:'高转化型'}[type.type_id] || type.type_id)}</strong>：${type.structure_status === 'qualified' ? '当前结构范围已核对' : '结构资格未通过'}${type.fact_speaker_status ? `；${type.fact_speaker_status === 'supported' ? '当前事实与人物门已核对' : '事实或人物资格仍阻断'}` : ''}。${type.type_id==='news' && type.structural_case_count !== null ? `结构参考 ${count(type.structural_case_count)} 个案例，不等于可制作视频数量。` : '可用主题数量仍须逐项原生规划，不能由类型或案例数量推算。'}</li>`).join('')}</ul></section>
    <p role="note">仅本次读取有效；资料、权限或批准范围变化后须重新核对。实际交付仍以生成、内容审核、发布确认和导出结果为准。</p>
    <button class="btn btn-primary" id="capacity-refresh" type="button">重新读取当前容量</button><p id="capacity-status" role="status"></p></main>`;
}

export function createCapacityViews({app,api,shell,bindCommonActions,skeletonPage,renderLoadError}) {
  let generation=0;
  async function renderCapacity() {
    const invocation=++generation, route=window.location.href;
    const isCurrent=()=>generation===invocation && window.location.href===route;
    const params=new URLSearchParams(window.location.search), business=params.get('business_id'), speaker=params.get('speaker_id');
    const target=params.has('novel_target') ? Number(params.get('novel_target')) : 10;
    const back='/create/config?business_id='+encodeURIComponent(business || '')+(speaker?'&speaker_id='+encodeURIComponent(speaker):'');
    skeletonPage('读取当前创作容量');
    try {
      if (!business || !speaker || !Number.isSafeInteger(target) || target<0 || target>40) throw Error('请从客户创作配置选择适用出镜人后进入容量说明。');
      const response=await api('/api/create/capacity-inventory',{method:'POST',body:JSON.stringify({business_id:business,speaker_id:speaker,novel_target:target})});
      if (!isCurrent()) return;
      const value=response.projection;
      if (value.business_id!==business || value.speaker_id!==speaker || value.target_gap?.news_novel_target!==target) throw Error('容量来源与当前客户或配置不一致。');
      app.innerHTML=shell('创作容量说明',capacityMarkup(value,back));bindCommonActions();
      document.getElementById('capacity-refresh').addEventListener('click',()=>renderCapacity());
    } catch(error) { if(isCurrent()) renderLoadError('容量说明暂不可用',error); }
  }
  return {renderCapacity};
}
