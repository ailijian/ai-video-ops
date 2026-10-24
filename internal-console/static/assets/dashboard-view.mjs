/* DASH-1 uses the shared shell and brand tokens. No business status is inferred here. */
import { formatConsoleTime as dashboardTime } from "./ui-format.mjs?v=ui-1";
export { dashboardTime };
const sections = { attention: "需要处理", materials: "待核对资料", running: "进行中任务", recent: "最近工作" };
const statusNames = { queued:"排队中", running:"进行中", failed:"未完成", completed:"执行完成", awaiting_review:"等待人工处理", fact_review_required:"待核对", persona_review_required:"待批准", revalidation_required:"待复核", needs_more_info:"资料待处理", draft:"待完善", approved:"已批准", exported:"已导出", blocked:"需查看原因", analysis_pending:"待解析", needs_confirmation:"待分类核对" };

export function dashboardMarkup(data, { escapeHtml: e, icons }) {
  const section = data.list.section;
  const rows = (items, empty, recent = false) => items.length ? items.map(item => `
    <a class="dash-work-row" href="${e(item.action.url)}" aria-label="${e(item.name)}，${e(item.action.label)}。${e(item.reason)}" ${item.case_id ? `data-case-id="${e(item.case_id)}"` : ""} ${item.task_id ? `data-task-id="${e(item.task_id)}"` : ""} title="${e([item.case_id ? `Case ID: ${item.case_id}` : "", item.task_id ? `Task ID: ${item.task_id}` : ""].filter(Boolean).join(" · "))}" data-route>
      <span class="dash-row-mark ${item.kind === "task_recovery" ? "dash-row-mark-warning" : ""}">${icons[item.kind === "task_recovery" ? "alert" : item.kind.startsWith("case") ? "cases" : item.kind === "task" ? "tasks" : "customers"]}</span>
      <span class="dash-row-copy"><strong>${e(item.name)}</strong><span>${e(item.reason)}${recent && statusNames[item.status] && !item.reason.includes(statusNames[item.status]) ? ` · ${e(statusNames[item.status])}` : ""}</span>
        ${item.updated_at ? `<small><time datetime="${e(item.updated_at)}" title="${e(item.time_label || "记录时间")}">${e(dashboardTime(item.updated_at))}</time></small>` : ""}</span>
      <span class="dash-row-next"><span>${e(item.action.label)}</span>${icons.arrow}</span>
    </a>`).join("") : `<div class="dash-empty">${icons.inbox}<p>${e(empty)}</p></div>`;
  const metricCards = Object.entries(data.metrics).map(([key, metric]) => {
    const tag = metric.available ? "a" : "div";
    return `<${tag} class="dash-metric" ${metric.available ? `href="${e(metric.url)}" data-route` : 'aria-label="'+e(metric.label)+'暂时不可用"'}>
      <span class="dash-metric-label">${e(metric.label)}${metric.available ? icons.arrow : ""}</span>
      <strong data-metric="${key}">${metric.available ? Number(metric.value) : "—"}</strong>
      <small>${e(metric.available ? metric.note : "暂时无法可靠读取")}</small></${tag}>`;
  }).join("");
  const unavailable = Object.values(data.sources).filter(source => !source.available).map(source => source.label);
  const warning = unavailable.length ? `<div class="dash-source-notice" role="status">${icons.alert}<div><strong>部分信息暂时无法读取</strong><p>${e(unavailable.join("、"))}暂不可用。下方保留已读取的记录，相关总数暂不显示。</p><button class="btn btn-quiet" type="button" data-dashboard-refresh>重新读取</button></div></div>` : "";
  const attentionComplete = data.metrics.pending.available;
  const page = data.list;
  const listSection = section !== "overview";
  const attention = listSection ? page.items : data.attention;
  const empty = section === "running" ? "当前没有排队或运行中的任务。" : section === "recent" ? "还没有可继续的工作记录。" : section === "materials" ? "目前没有需要核对的资料。" : "目前没有需要处理的事项。";
  const all = `/workbench?section=${section === "overview" ? "attention" : section}`;
  const pages = listSection && page.total > page.page_size ? `<nav class="dash-pagination" aria-label="工作记录分页">
    ${page.page > 1 ? `<a class="btn btn-secondary" href="${all}&page=${page.page-1}" data-route>上一页</a>` : "<span></span>"}
    <span>第 ${page.page} / ${Math.ceil(page.total/page.page_size)} 页${page.complete ? "" : " · 部分记录"}</span>
    ${page.page*page.page_size < page.total ? `<a class="btn btn-secondary" href="${all}&page=${page.page+1}" data-route>下一页</a>` : "<span></span>"}</nav>` : "";
  const running = data.metrics.running;
  const recentComplete = ["customers","requests","tasks"].every(key => data.sources[key]?.available !== false);
  const recentEmpty = data.recent_omitted_attention ? "最近的优先事项已列在上方，可查看全部工作记录。" : data.metrics.customers.value > 0 ? "暂无可按时间展示的工作记录，可从客户或任务继续。" : "还没有工作记录，从添加第一个客户开始。";
  return `<main class="page dash-page">
    <header class="dash-welcome"><div><p class="dash-date">${e(data.period.today.replaceAll("-", "."))} · 今天</p><h1>欢迎回来</h1><p>管理客户、跟进创作，继续今天的工作。</p></div></header>
    <section class="dash-metrics" aria-label="运营概览">${metricCards}</section>
    ${warning}
    <div class="dash-layout">
      <section class="dash-panel dash-attention" aria-labelledby="dash-attention-heading">
        <div class="dash-panel-head"><div><h2 id="dash-attention-heading">${e(listSection ? sections[section] : "需要处理")}</h2><p>${section === "recent" ? "授权范围内的最近记录，按真实时间排序。" : section === "running" ? "后台正在执行，打开原任务查看进度。" : attentionComplete ? "先处理异常，再继续审核与资料核对。" : "已读取的可处理记录；总数暂不可用。"}</p></div>
          ${listSection ? `<a class="dash-text-link" href="/workbench" data-route>返回概览</a>` : `<a class="dash-text-link" href="/workbench?section=attention" data-route>查看全部${attentionComplete ? ` · ${Number(data.metrics.pending.value)}` : ""}</a>`}</div>
        ${rows(attention, data.partial && !page.complete ? "这部分记录暂时无法完整读取，请稍后重试。" : empty, section === "recent")}${pages}
      </section>
      <aside class="dash-shortcuts"><div class="dash-panel dash-shortcut-panel"><div class="dash-panel-head"><h2>快捷入口</h2></div>
        ${data.shortcuts.map(item => `<a class="dash-shortcut" href="${e(item.url)}" data-route><span class="dash-shortcut-icon">${icons[item.icon]}</span><span><strong>${e(item.title)}</strong><small>${e(item.description)}</small></span>${icons.arrow}</a>`).join("")}</div>
        <div class="dash-execution"><span class="dash-execution-icon">${icons.tasks}</span><div><strong>${running.available ? running.value ? `${Number(running.value)} 个任务正在处理` : "当前没有进行中的任务" : "任务状态暂不可用"}</strong><p>执行进度与失败恢复，随时从任务继续。</p><a class="dash-text-link" href="/tasks" data-route>查看任务记录 ${icons.arrow}</a></div></div>
      </aside>
      ${!listSection ? `<section class="dash-panel dash-recent" aria-labelledby="dash-recent-heading"><div class="dash-panel-head"><div><h2 id="dash-recent-heading">最近工作</h2><p>按最近更新时间继续，优先事项见上方。</p></div><a class="dash-text-link" href="/workbench?section=recent" data-route>查看全部</a></div>${rows(data.recent,recentComplete ? recentEmpty : "最近工作暂时无法完整读取，请稍后重试。", true)}</section>` : ""}
    </div></main>`;
}

export function dashboardSkeleton() {
  return `<main class="page dash-page" aria-busy="true" aria-label="工作台正在加载"><div class="dash-skeleton dash-skeleton-heading"></div><div class="dash-metrics">${Array.from({length:4},()=>'<div class="dash-metric"><div class="dash-skeleton"></div><div class="dash-skeleton dash-skeleton-number"></div><div class="dash-skeleton"></div></div>').join("")}</div><section class="dash-panel dash-loading"><span class="loading-indicator" aria-hidden="true"></span><p>正在读取运营信息…</p></section></main>`;
}
