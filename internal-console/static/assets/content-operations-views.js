import { escapeHtml } from "./case-components.js?v=productized-stage1-5";

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
    skeletonPage("内容管理");
    try {
      const data = await api(`/api/customers/${encodeURIComponent(businessId)}/content-operations`);
      const customer = data.customer || {};
      const createAction = data.actions?.create_url
        ? `<a class="btn btn-primary" href="${escapeHtml(data.actions.create_url)}" data-route>开始创作</a>`
        : "";
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
          ${ContentOperationsPanel(data)}
        </main>`,
      );
      bindCommonActions();
    } catch (error) {
      renderLoadError("内容管理暂时无法读取", error);
    }
  }

  return { renderContentOperations };
}
