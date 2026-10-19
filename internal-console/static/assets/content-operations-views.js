import { escapeHtml } from "./case-components.js?v=flow-closure-2";

const INTERNAL_LANGUAGE = /(?:authority|canonical|artifact|request id|content ledger|semantic ledger|historical exposure|presentation history|projection|[A-Z][A-Z0-9_]{3,})/;

function safeOperationsText(value, fallback) {
  const text = String(value || "").trim();
  if (!text || INTERNAL_LANGUAGE.test(text)) return fallback;
  return text;
}

function profileLabel(profile) {
  return profile === "news" ? "新闻体" : "素材混剪";
}

function summaryItem({ label, value, note, status = "" }) {
  return `
    <div class="content-summary-item">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value)}</dd>
      <small>${escapeHtml(note)}</small>
      ${status ? `<span class="content-summary-status">${escapeHtml(status)}</span>` : ""}
    </div>`;
}

function currentWork(items) {
  if (!items.length) {
    return `
      <div class="content-management-empty">
        <span class="content-management-dot" aria-hidden="true"></span>
        <div>
          <strong>当前没有进行中的创作</strong>
          <span>完成后的内容会保留在最近交付中。</span>
        </div>
      </div>`;
  }

  return `
    <div class="content-work-list">
      ${items.map((item) => `
        <article class="content-work-row">
          <span class="content-type-label">${profileLabel(item.profile)}</span>
          <div>
            <strong>${escapeHtml(safeOperationsText(item.stage_label, "内容处理中"))}</strong>
            <p>${escapeHtml(safeOperationsText(item.detail, "本次创作仍在处理中。"))}</p>
          </div>
          ${item.continue_url ? `
            <a class="btn btn-secondary btn-compact" href="${escapeHtml(item.continue_url)}" data-route>继续处理</a>` : ""}
        </article>`).join("")}
    </div>`;
}

function deliveryRows(items) {
  if (!items.length) {
    return `
      <div class="content-management-empty neutral">
        <span class="content-management-dot" aria-hidden="true"></span>
        <div>
          <strong>还没有正式交付</strong>
          <span>完成审核与导出后，交付会自动出现在这里。</span>
        </div>
      </div>`;
  }

  return `
    <div class="content-delivery-list">
      ${items.map((item) => {
        const news = item.profile === "news";
        const quantity = news
          ? `1 个视频 · ${Number(item.title_count || 0)} 个标题`
          : `${Number(item.item_count || 0)} 条内容`;
        return `
          <article class="content-delivery-row">
            <span class="content-type-label">${profileLabel(item.profile)}</span>
            <div>
              <strong>${escapeHtml(quantity)}</strong>
              <p>已完成交付</p>
            </div>
            <div class="content-delivery-action">
              ${item.download_ready && item.download_url
                ? `<a class="btn btn-secondary btn-compact" href="${escapeHtml(item.download_url)}">下载 Excel</a>`
                : `<span class="content-delivery-status">交付记录已保留</span>`}
            </div>
          </article>`;
      }).join("")}
    </div>`;
}

export function ContentOperationsPanel(data = {}) {
  const mix = data.delivery_summary?.mix || {};
  const news = data.delivery_summary?.news || {};
  const mixCapacity = data.capacity?.mix || {};
  const newsCapacity = data.capacity?.news || {};
  const mixRemaining = mixCapacity.remaining === null || mixCapacity.remaining === undefined
    ? "—"
    : `${Number(mixCapacity.remaining)} 条`;
  const mixNote = mixCapacity.remaining === null || mixCapacity.remaining === undefined
    ? "选择出镜人后查看当前内容空间"
    : mixCapacity.available
      ? "当前仍有值得继续做的新内容"
      : "当前方向已经覆盖";
  const newsAvailable = Boolean(newsCapacity.available);

  return `
    <div class="content-management" data-content-management>
      <section class="work-surface content-management-section content-management-overview">
        <div class="section-head content-management-heading">
          <div>
            <h2>内容概览</h2>
            <p>查看已交付内容，以及当前还能继续做什么。</p>
          </div>
        </div>
        <dl class="content-summary-grid">
          ${summaryItem({
            label: "素材混剪已交付",
            value: `${Number(mix.completed_item_count || 0)} 条`,
            note: `${Number(mix.completed_batch_count || 0)} 次完成交付`,
          })}
          ${summaryItem({
            label: "新闻体已交付",
            value: `${Number(news.completed_video_count || 0)} 个视频`,
            note: `${Number(news.completed_title_count || 0)} 个标题`,
          })}
          ${summaryItem({
            label: "素材混剪可创作",
            value: mixRemaining,
            note: mixNote,
            status: mixCapacity.available ? "可继续" : "暂无",
          })}
          ${summaryItem({
            label: "新闻体可用内容",
            value: newsAvailable ? "可以继续" : "暂无",
            note: newsAvailable
              ? "已有内容可以重新组织为新闻体"
              : "暂无适合重新呈现的已确认内容",
            status: newsAvailable ? "可继续" : "暂无",
          })}
        </dl>
      </section>

      <section class="work-surface content-management-section">
        <div class="section-head content-management-heading">
          <div>
            <h2>进行中的创作</h2>
            <p>只显示仍需要继续处理的内容。</p>
          </div>
          ${(data.current_work || []).length
            ? `<span class="content-count-pill">${Number(data.current_work.length)} 个进行中</span>`
            : ""}
        </div>
        ${currentWork(data.current_work || [])}
      </section>

      <section class="work-surface content-management-section">
        <div class="section-head content-management-heading">
          <div>
            <h2>最近交付</h2>
            <p>查看最近完成的内容，并在文件可用时下载。</p>
          </div>
        </div>
        ${deliveryRows(data.recent_deliveries || [])}
      </section>
    </div>`;
}

export function CreationRecordsPanel(data = {}) {
  const rows = data.records || [];
  return `<section class="work-surface content-management-section"><div class="section-head content-management-heading"><div><h2>作品与创作记录</h2><p>按原始创作请求记录，包含未完成、待审核、已结束及已导出内容。</p></div><span class="content-count-pill">${data.total ?? "—"} 条记录</span></div>${rows.length
    ? `<div class="content-work-list">${rows.map(row => `<article class="content-work-row"><span class="content-type-label">${profileLabel(row.profile)}</span><div><strong>${escapeHtml(row.label)}</strong><p>${escapeHtml(row.updated_at ? row.updated_at.slice(0,10) : "更新时间暂无")}</p></div><a class="btn btn-secondary btn-compact" href="${escapeHtml(row.url)}" data-route>查看原创作</a></article>`).join("")}</div>`
    : '<div class="content-management-empty neutral"><div><strong>还没有创作记录</strong><span>从该客户开始创作后，请求和后续成果会保留在这里。</span></div></div>'}</section>`;
}

export function createContentOperationsViews({
  app,
  api,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  renderLoadError,
}) {
  async function renderContentOperations(businessId) {
    const route = window.location.href;
    skeletonPage("内容管理");
    try {
      const page = Math.max(1, Number(new URLSearchParams(window.location.search).get("page")) || 1);
      const [records, data] = await Promise.all([
        api(`/api/customers/${encodeURIComponent(businessId)}/creation-records?page=${page}`),
        api(`/api/customers/${encodeURIComponent(businessId)}/content-operations`).catch(() => null),
      ]);
      if (window.location.href !== route) return;
      const customer = records.customer || {};
      const createAction = `<a class="btn btn-primary" href="/create?business_id=${encodeURIComponent(businessId)}" data-route>查看创作条件</a>`;
      const description = [customer.display_name || businessId, customer.industry || ""]
        .filter(Boolean)
        .join(" · ");

      app.innerHTML = shell(
        "内容管理",
        `<main class="page page-standard content-management-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers/${encodeURIComponent(businessId)}#content" data-route>← 返回客户</a>
          </div>
          ${pageHeading("", "内容管理", description, createAction)}
          ${CreationRecordsPanel(records)}
          <nav class="customer-list-pagination" aria-label="创作记录分页">${page > 1 ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}/content?page=${page-1}" data-route>上一页</a>` : ""}<span>第 ${page} 页</span>${page * records.page_size < records.total ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}/content?page=${page+1}" data-route>下一页</a>` : ""}</nav>
          ${data ? ContentOperationsPanel(data) : '<p class="field-hint">内容概览暂时无法可靠读取；已有创作记录仍可查看。</p>'}
        </main>`,
      );
      bindCommonActions();
    } catch (error) {
      if (window.location.href !== route) return;
      renderLoadError("内容管理暂时无法读取", error);
    }
  }

  return { renderContentOperations };
}
