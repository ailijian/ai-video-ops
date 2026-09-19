import {
  escapeHtml,
} from "./case-components.js";


export function createContentOperationsViews({
  app,
  api,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  renderLoadError,
}) {
  function overviewCard({
    label,
    value,
    meta,
    badge = "",
    tone = "",
  }) {
    return `
      <article class="card operations-overview-card ${escapeHtml(
        tone,
      )}">
        <div class="operations-overview-head">
          <span>${escapeHtml(label)}</span>
          ${
            badge
              ? `
                <span class="operations-state-badge">
                  ${escapeHtml(badge)}
                </span>`
              : ""
          }
        </div>

        <strong class="operations-stat">
          ${escapeHtml(value)}
        </strong>

        <p>${escapeHtml(meta)}</p>
      </article>`;
  }

  function currentWork(items) {
    if (!items.length) {
      return `
        <div class="operations-empty-strip">
          <span
            class="operations-empty-dot"
            aria-hidden="true"
          ></span>

          <div>
            <strong>
              当前没有进行中的内容任务
            </strong>

            <span>
              已完成的交付都保留在下方，可以随时下载。
            </span>
          </div>
        </div>`;
    }

    return `
      <div class="operations-work-list">
        ${items
          .map(
            (item) => `
              <article class="card operations-work-card">
                <div class="operations-work-main">
                  <span class="operations-profile-badge">
                    ${
                      item.profile === "news"
                        ? "News"
                        : "Mix"
                    }
                  </span>

                  <div>
                    <strong>
                      ${escapeHtml(
                        item.stage_label ||
                          "进行中",
                      )}
                    </strong>

                    ${
                      item.detail
                        ? `
                          <p>
                            ${escapeHtml(
                              item.detail,
                            )}
                          </p>`
                        : `
                          <p>
                            当前任务仍在创作流程中。
                          </p>`
                    }
                  </div>
                </div>

                ${
                  item.continue_url
                    ? `
                      <a
                        class="btn btn-secondary btn-compact"
                        href="${escapeHtml(
                          item.continue_url,
                        )}"
                        data-route
                      >
                        继续处理
                      </a>`
                    : ""
                }
              </article>`,
          )
          .join("")}
      </div>`;
  }

  function deliveryRows(items) {
    if (!items.length) {
      return `
        <div class="operations-empty-strip">
          <span
            class="operations-empty-dot neutral"
            aria-hidden="true"
          ></span>

          <div>
            <strong>还没有正式交付</strong>
            <span>
              完成审核与导出后，交付会自动出现在这里。
            </span>
          </div>
        </div>`;
    }

    return `
      <div class="operations-delivery-list">
        ${items
          .map((item) => {
            const isNews =
              item.profile === "news";

            const quantity =
              isNews
                ? `1 个视频 · ${Number(
                    item.title_count || 0,
                  )} 个标题`
                : `${Number(
                    item.item_count || 0,
                  )} 条`;

            const note =
              isNews
                ? "已完成并记录展示历史"
                : "已完成并记录历史曝光";

            return `
              <article class="operations-delivery-row">
                <div class="operations-delivery-type">
                  <span class="operations-profile-badge">
                    ${isNews ? "News" : "Mix"}
                  </span>
                </div>

                <div class="operations-delivery-copy">
                  <strong>
                    ${escapeHtml(quantity)}
                  </strong>
                  <span>
                    ${escapeHtml(note)}
                  </span>
                </div>

                <div class="operations-delivery-action">
                  ${
                    item.download_ready &&
                    item.download_url
                      ? `
                        <a
                          class="btn btn-secondary btn-compact"
                          href="${escapeHtml(
                            item.download_url,
                          )}"
                        >
                          下载 Excel
                        </a>`
                      : `
                        <span class="operations-record-pill">
                          交付记录已保留
                        </span>`
                  }
                </div>
              </article>`;
          })
          .join("")}
      </div>`;
  }

  async function renderContentOperations(
    businessId,
  ) {
    skeletonPage(
      "内容运营",
    );

    try {
      const data = await api(
        `/api/customers/${encodeURIComponent(
          businessId,
        )}/content-operations`,
      );

      const customer =
        data.customer || {};

      const mix =
        data.delivery_summary
          ?.mix || {};

      const news =
        data.delivery_summary
          ?.news || {};

      const mixCapacity =
        data.capacity?.mix || {};

      const newsCapacity =
        data.capacity?.news || {};

      const workItems =
        data.current_work || [];

      const defaultSpeaker =
        customer.default_speaker;

      const mixRemaining =
        mixCapacity.remaining === null ||
        mixCapacity.remaining ===
          undefined
          ? "—"
          : `${Number(
              mixCapacity.remaining,
            )} 条`;

      const newsNext =
        newsCapacity.available
          ? "可创建"
          : "暂无";

      const createAction =
        data.actions?.create_url
          ? `
            <a
              class="btn btn-primary operations-create-button"
              href="${escapeHtml(
                data.actions.create_url,
              )}"
              data-route
            >
              开始新的创作
            </a>`
          : "";

      app.innerHTML = shell(
        "内容运营",
        `
          <main class="page content-operations-page">
            <div class="case-review-heading operations-topline">
              <a
                class="back-link"
                href="/customers/${encodeURIComponent(
                  businessId,
                )}"
                data-route
              >
                ← 返回客户详情
              </a>

              <span class="pill pill-approved">
                只读运营总览
              </span>
            </div>

            ${pageHeading(
              "内容运营",
              customer.display_name ||
                businessId,
              [
                customer.industry ||
                  "",
                defaultSpeaker
                  ? `${defaultSpeaker.display_name || ""} · ${defaultSpeaker.public_role || ""}`
                  : customer.speaker_selection_required
                    ? "多个已批准出镜人 · 可用性需要显式选择"
                    : "暂无已批准出镜人",
              ]
                .filter(Boolean)
                .join(" · "),
              createAction,
            )}

            <section class="section operations-overview-section">
              <div class="section-head operations-section-head">
                <div>
                  <h2>内容概览</h2>
                  <p>
                    已交付内容，以及还能继续做什么。
                  </p>
                </div>
              </div>

              <div class="operations-overview-grid">
                ${overviewCard({
                  label:
                    "Mix 已交付",
                  value:
                    `${Number(
                      mix.completed_item_count ||
                        0,
                    )} 条`,
                  meta:
                    `${Number(
                      mix.completed_batch_count ||
                        0,
                    )} 个完成批次`,
                  tone:
                    "delivered",
                })}

                ${overviewCard({
                  label:
                    "News 已交付",
                  value:
                    `${Number(
                      news.completed_video_count ||
                        0,
                    )} 个视频`,
                  meta:
                    `${Number(
                      news.completed_title_count ||
                        0,
                    )} 个信息标题`,
                  tone:
                    "delivered",
                })}

                ${overviewCard({
                  label:
                    "Mix 新内容",
                  value:
                    mixRemaining,
                  meta:
                    mixCapacity.message ||
                    "查看剩余高质量内容容量。",
                  badge:
                    mixCapacity.available
                      ? "可继续"
                      : "已用尽",
                  tone:
                    mixCapacity.available
                      ? "available"
                      : "quiet",
                })}

                ${overviewCard({
                  label:
                    "News 新内容",
                  value:
                    newsNext,
                  meta:
                    newsCapacity.message ||
                    "查看当前是否有新的可用 News 内容。",
                  badge:
                    newsCapacity.available
                      ? "可创建"
                      : "暂无新内容",
                  tone:
                    newsCapacity.available
                      ? "available"
                      : "quiet",
                })}
              </div>
            </section>

            <section class="section operations-section">
              <div class="section-head operations-section-head">
                <div>
                  <h2>当前工作</h2>
                  <p>
                    只展示真正仍在进行中的创作任务。
                  </p>
                </div>

                ${
                  workItems.length
                    ? `
                      <span class="operations-count-pill">
                        ${Number(
                          workItems.length,
                        )} 个进行中
                      </span>`
                    : ""
                }
              </div>

              ${currentWork(
                workItems,
              )}
            </section>

            <section class="section operations-section">
              <div class="section-head operations-section-head">
                <div>
                  <h2>最近交付</h2>
                  <p>
                    Mix 与 News 都可以从这里查看最近完成记录。
                  </p>
                </div>
              </div>

              ${deliveryRows(
                data.recent_deliveries ||
                  [],
              )}
            </section>

            <details class="operations-authority-details">
              <summary>
                数据来源说明
              </summary>

              <div>
                <strong>
                  这是运营投影，不是新的业务真源。
                </strong>

                <p>
                  页面不会创建新的生命周期、数据库状态或内容记录。
                  Mix、News、Capacity 与 Historical Exposure
                  仍以现有 canonical Authority 为准。
                </p>
              </div>
            </details>
          </main>`,
      );

      bindCommonActions();
    } catch (error) {
      renderLoadError(
        "内容运营总览暂时无法读取",
        error,
      );
    }
  }

  return {
    renderContentOperations,
  };
}
