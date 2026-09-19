export function createNewsDeliveryViews({
  api,
  showToast,
  escapeHtml,
}) {
  function watchTask(task, refresh, completedMessage) {
    showToast("任务已进入后台队列，可以离开页面后再返回。");
    async function poll() {
      try {
        const response = await api(
          `/api/tasks/${encodeURIComponent(task.task_id)}`,
        );
        if (["completed", "failed"].includes(response.task.status)) {
          await refresh();
          showToast(
            response.task.status === "completed"
              ? completedMessage
              : response.task.error_message || "后台任务没有完成。",
          );
          return;
        }
      } catch {
        // A later poll or the shared task list can recover the durable task.
      }
      window.setTimeout(poll, 1200);
    }
    poll();
  }
  function newKey() {
    if (globalThis.crypto?.randomUUID) {
      return globalThis.crypto.randomUUID();
    }
    return [
      "news",
      Date.now(),
      Math.random().toString(36).slice(2, 14),
    ].join("_");
  }

  function roleLabel(role) {
    const labels = {
      price_offer_first_semantic_anchor: "首屏价格 / Offer",
      price_scope_information: "价格范围",
      included_value_context: "包含价值",
      trust_context: "信任信息",
      service_context: "服务信息",
    };
    return labels[role] || role || "信息槽";
  }

  function progress(state) {
    const order = {
      RESOLVE_NEWS_PLAN: 0,
      HUMAN_REVIEW: 1,
      EXPORT_NEWS_EXCEL: 2,
      NEWS_EXCEL_EXPORTED: 3,
    };
    const current = order[state.next_action] ?? 0;
    const steps = [
      "标题方案",
      "人工审核",
      "Excel 导出",
    ];

    return `
      <div class="delivery-progress news-delivery-progress">
        ${steps
          .map(
            (label, index) => `
              <div class="delivery-step ${
                index < current
                  ? "done"
                  : index === current
                    ? "current"
                    : ""
              }">
                <span>${index < current ? "✓" : index + 1}</span>
                <strong>${escapeHtml(label)}</strong>
              </div>`,
          )
          .join("")}
      </div>`;
  }

  function sourceCard(state) {
    return `
      <section class="card review-section">
        <span class="capacity-kicker">
          News 来源内容
        </span>

        <h2>${escapeHtml(
          String(
            state.source_content?.title ||
              "已选择历史内容",
          ),
        )}</h2>

        <div class="review-row">
          <span>历史核心表达</span>
          <p>${escapeHtml(
            String(
              state.source_content?.central_claim ||
                "",
            ),
          )}</p>
        </div>

        <div class="capacity-authority-note">
          <strong>Cross-profile Repurpose</strong>
          <span>
            这次只改变展示形态，不创建新的语义内容；
            导出后写入 Presentation History，
            Semantic Ledger entry count 不增加。
          </span>
        </div>
      </section>`;
  }

  function renderReview(state) {
    const slots =
      state.plan?.slots || [];

    return `
      ${sourceCard(state)}

      <section class="card review-section">
        <span class="capacity-kicker">
          推荐 ${Number(
            state.plan?.slot_count || 0,
          )} 个 News 信息标题
        </span>

        <h2>逐条审核标题</h2>

        <p>
          每一条都选择：
          <strong>通过</strong>、
          <strong>修改后通过</strong>
          或 <strong>淘汰</strong>。
          原始推荐标题永久保留，修改只形成 Human Revision。
          最终仍需保留 4–8 条。
        </p>

        <div class="news-slot-review-list">
          ${slots
            .map(
              (slot, index) => `
                <article
                  class="delivery-script-card news-slot-card"
                  data-news-review-item
                  data-slot-id="${escapeHtml(
                    String(slot.slot_id || ""),
                  )}"
                >
                  <div class="delivery-script-head">
                    <div>
                      <strong>
                        ${index + 1}.
                        ${escapeHtml(
                          roleLabel(
                            slot.semantic_role,
                          ),
                        )}
                      </strong>
                    </div>

                    <span class="badge ${
                      slot.price_or_offer_anchor
                        ? "approved"
                        : "review"
                    }">
                      ${
                        slot.price_or_offer_anchor
                          ? "首屏锚点"
                          : "可审核"
                      }
                    </span>
                  </div>

                  <div class="review-row">
                    <span>系统推荐标题</span>
                    <p>
                      ${escapeHtml(
                        String(
                          slot.proposed_text || "",
                        ),
                      )}
                    </p>
                  </div>

                  <details class="full-breakdown">
                    <summary>
                      查看审核依据
                      <span>来源事实</span>
                    </summary>

                    <div class="breakdown-body">
                      <h3>来源 Known Fact</h3>
                      <p class="narration-text">
                        ${escapeHtml(
                          String(
                            slot.source_known_fact || "",
                          ),
                        )}
                      </p>

                      <h3>Authority Field</h3>
                      <p class="narration-text">
                        ${escapeHtml(
                          String(
                            slot.source_field || "",
                          ),
                        )}
                      </p>
                    </div>
                  </details>

                  <div class="unified-review-decisions">
                    <label class="unified-review-choice">
                      <input
                        type="radio"
                        name="decision-${escapeHtml(
                          String(slot.slot_id || ""),
                        )}"
                        value="approved"
                        data-news-decision
                      >
                      <span>
                        <strong>通过</strong>
                        <small>按系统推荐标题导出</small>
                      </span>
                    </label>

                    <label class="unified-review-choice">
                      <input
                        type="radio"
                        name="decision-${escapeHtml(
                          String(slot.slot_id || ""),
                        )}"
                        value="revised"
                        data-news-decision
                      >
                      <span>
                        <strong>修改后通过</strong>
                        <small>只改表达，不改变来源事实</small>
                      </span>
                    </label>

                    <label class="unified-review-choice ${
                      slot.price_or_offer_anchor
                        ? "disabled"
                        : ""
                    }">
                      <input
                        type="radio"
                        name="decision-${escapeHtml(
                          String(slot.slot_id || ""),
                        )}"
                        value="rejected"
                        data-news-decision
                        ${
                          slot.price_or_offer_anchor
                            ? "disabled"
                            : ""
                        }
                      >
                      <span>
                        <strong>
                          ${
                            slot.price_or_offer_anchor
                              ? "首屏不可淘汰"
                              : "淘汰"
                          }
                        </strong>
                        <small>
                          不进入 Excel / Presentation History
                        </small>
                      </span>
                    </label>
                  </div>

                  <div
                    class="unified-revision-editor"
                    data-news-revision-editor
                    hidden
                  >
                    <div class="field">
                      <label>修改后的标题</label>
                      <input
                        type="text"
                        data-news-revised-text
                        value="${escapeHtml(
                          String(
                            slot.proposed_text || "",
                          ),
                        )}"
                      >
                    </div>

                    <p class="field-hint">
                      不能新增数字事实，不能删除
                      “通常 / 约 / 左右 / 免费”等限定词，
                      也不能把标题强化成更绝对的营销承诺。
                    </p>
                  </div>

                  <div class="field">
                    <label>审核备注（可选）</label>
                    <input
                      type="text"
                      data-news-review-note
                      placeholder="例如：表达更自然；信息重复；本轮淘汰"
                    >
                  </div>
                </article>`,
            )
            .join("")}
        </div>

        <div class="delivery-action-row">
          <button
            type="button"
            class="btn btn-secondary"
            data-news-approve-all
          >
            全部标记通过
          </button>

          <button
            type="button"
            class="btn btn-primary"
            data-news-submit-review
          >
            提交人工审核
          </button>
        </div>
      </section>`;
  }
  function renderBody(state) {
    if (
      state.next_action ===
      "RESOLVE_NEWS_PLAN"
    ) {
      return `
        ${sourceCard(state)}

        <section class="card review-section">
          <h2>生成 News 标题方案</h2>

          <p>
            系统将从 Strong Historical Content
            中确定性恢复 4–8 个独立信息单元。
            不随机、不 Padding、不调用远程模型。
          </p>

          <button
            type="button"
            class="btn btn-primary btn-wide"
            data-news-resolve-plan
          >
            生成标题方案
          </button>
        </section>`;
    }

    if (
      state.next_action ===
      "HUMAN_REVIEW"
    ) {
      return renderReview(state);
    }

    if (
      state.next_action ===
      "EXPORT_NEWS_EXCEL"
    ) {
      return `
        ${sourceCard(state)}

        <section class="card capacity-result ready">
          <span class="capacity-kicker">
            人工审核已通过
          </span>

          <h2>
            ${Number(
              state.review
                ?.approved_slot_count || 0,
            )}
            个标题可以正式导出
          </h2>

          <p>
            Excel 将按最终通过数量动态生成
            标题1～标题N；不会固定补成 6 列或 8 列。
          </p>

          <button
            type="button"
            class="btn btn-primary btn-wide"
            data-news-export
          >
            导出 News Excel
          </button>
        </section>`;
    }

    if (
      state.next_action ===
      "NEWS_EXCEL_EXPORTED"
    ) {
      const name =
        state.export?.output_name ||
        "News新闻体.xlsx";

      return `
        <section class="card capacity-result ready delivery-success">
          <span class="capacity-kicker">
            News 本轮停止点已达到
          </span>

          <h2>正式 Excel 已导出</h2>

          <div class="delivery-export-meta">
            <div>
              <span>视频类型</span>
              <strong>News 新闻体</strong>
            </div>

            <div>
              <span>标题数量</span>
              <strong>
                ${Number(
                  state.export
                    ?.slot_count || 0,
                )} 个
              </strong>
            </div>

            <div>
              <span>语义新增</span>
              <strong>0</strong>
            </div>

            <div>
              <span>Presentation History</span>
              <strong>已闭合</strong>
            </div>

            <div class="wide">
              <span>文件名</span>
              <strong>${escapeHtml(name)}</strong>
            </div>
          </div>

          <a
            class="btn btn-primary btn-wide"
            href="/api/create/news/${encodeURIComponent(
              state.request_id,
            )}/excel"
          >
            下载 ${escapeHtml(name)}
          </a>
        </section>`;
    }

    return "";
  }

  function bindState(
    host,
    state,
    refresh,
  ) {
    const resolve =
      host.querySelector(
        "[data-news-resolve-plan]",
      );

    if (resolve) {
      resolve.addEventListener(
        "click",
        async () => {
          resolve.disabled = true;
          resolve.textContent =
            "正在生成标题方案…";

          try {
            const response = await api(
              `/api/create/news/${encodeURIComponent(
                state.request_id,
              )}/resolve-plan`,
              {
                method: "POST",
              },
            );

            watchTask(
              response.task,
              refresh,
              "News Plan 任务已结束，已重新读取当前业务状态。",
            );
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            );

            if (resolve.isConnected) {
              resolve.disabled = false;
              resolve.textContent =
                "生成标题方案";
            }
          }
        },
      );
    }

    host
      .querySelectorAll(
        "[data-news-review-item]",
      )
      .forEach((card) => {
        const editor =
          card.querySelector(
            "[data-news-revision-editor]",
          );

        card
          .querySelectorAll(
            "[data-news-decision]",
          )
          .forEach((input) => {
            input.addEventListener(
              "change",
              () => {
                if (editor) {
                  editor.hidden =
                    input.value !== "revised";
                }
              },
            );
          });
      });

    const approveAll =
      host.querySelector(
        "[data-news-approve-all]",
      );

    if (approveAll) {
      approveAll.addEventListener(
        "click",
        () => {
          host
            .querySelectorAll(
              "[data-news-review-item]",
            )
            .forEach((card) => {
              const approved =
                card.querySelector(
                  'input[data-news-decision][value="approved"]',
                );
              const editor =
                card.querySelector(
                  "[data-news-revision-editor]",
                );

              if (approved) {
                approved.checked = true;
              }
              if (editor) {
                editor.hidden = true;
              }
            });
        },
      );
    }

    const submit =
      host.querySelector(
        "[data-news-submit-review]",
      );

    if (submit) {
      submit.addEventListener(
        "click",
        async () => {
          const cards = Array.from(
            host.querySelectorAll(
              "[data-news-review-item]",
            ),
          );

          const items = [];
          let approvedCount = 0;

          for (const card of cards) {
            const decision =
              card.querySelector(
                "input[data-news-decision]:checked",
              )?.value;

            if (!decision) {
              showToast(
                "请逐条选择“通过 / 修改后通过 / 淘汰”。",
              );
              return;
            }

            const item = {
              slot_id:
                card.dataset.slotId,
              decision,
              note:
                card.querySelector(
                  "[data-news-review-note]",
                )?.value?.trim() || "",
            };

            if (decision === "approved") {
              approvedCount += 1;
            }

            if (decision === "revised") {
              const revisedText =
                card.querySelector(
                  "[data-news-revised-text]",
                )?.value?.trim() || "";

              if (!revisedText) {
                showToast(
                  "修改后通过的标题不能为空。",
                );
                return;
              }

              approvedCount += 1;
              item.revised_text =
                revisedText;
            }

            items.push(item);
          }

          if (
            approvedCount < 4 ||
            approvedCount > 8
          ) {
            showToast(
              "最终需要保留 4–8 个标题。",
            );
            return;
          }

          submit.disabled = true;
          submit.textContent =
            "正在提交审核…";

          try {
            await api(
              `/api/create/news/${encodeURIComponent(
                state.request_id,
              )}/review`,
              {
                method: "POST",
                body: JSON.stringify({
                  items,
                }),
              },
            );

            showToast(
              "News Human Review 已通过。",
            );

            await refresh();
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            );

            if (submit.isConnected) {
              submit.disabled = false;
              submit.textContent =
                "提交人工审核";
            }
          }
        },
      );
    }

    const exportButton =
      host.querySelector(
        "[data-news-export]",
      );

    if (exportButton) {
      exportButton.addEventListener(
        "click",
        async () => {
          exportButton.disabled = true;
          exportButton.textContent =
            "正在导出并闭合历史…";

          try {
            const response = await api(
              `/api/create/news/${encodeURIComponent(
                state.request_id,
              )}/export`,
              {
                method: "POST",
              },
            );

            watchTask(
              response.task,
              refresh,
              "News Export 任务已结束，已重新读取 Receipt 与历史闭合状态。",
            );
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            );

            if (
              exportButton.isConnected
            ) {
              exportButton.disabled = false;
              exportButton.textContent =
                "导出 News Excel";
            }
          }
        },
      );
    }
  }

  async function restore(
    requestId,
    hostOverride = null,
  ) {
    const host =
      hostOverride ||
      document.querySelector(
        "#capacity-preview-result",
      );

    if (!host || !requestId) {
      return;
    }

    host.innerHTML = `
      <section class="card review-section">
        <h2>正在恢复 News 内容交付…</h2>
      </section>`;

    try {
      const response = await api(
        `/api/create/news/${encodeURIComponent(
          requestId,
        )}/delivery`,
      );

      const state = response.state;

      host.innerHTML = `
        <div class="content-delivery-stack">
          <section class="card review-section">
            <div class="delivery-script-head">
              <div>
                <span class="capacity-kicker">
                  News 内容交付
                </span>

                <h2>
                  ${
                    state.stop_point_reached
                      ? "Excel 已导出"
                      : "继续当前 News 创作"
                  }
                </h2>
              </div>

              <code>
                ${escapeHtml(
                  String(
                    state.request_id ||
                      "",
                  ),
                )}
              </code>
            </div>

            ${progress(state)}
          </section>

          ${renderBody(state)}
        </div>`;

      bindState(
        host,
        state,
        () =>
          restore(
            requestId,
            host,
          ),
      );

      return state;
    } catch (error) {
      host.innerHTML = `
        <section class="card capacity-result blocked">
          <span class="capacity-kicker">
            News Delivery 状态恢复失败
          </span>

          <h2>当前没有继续执行</h2>

          <p>
            ${escapeHtml(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            )}
          </p>
        </section>`;

      showToast(
        error.detail?.next_action ||
          error.detail?.message ||
          error.message,
      );

      return null;
    }
  }

  function renderPreview(
    host,
    preview,
    {
      onRequestCreated,
    } = {},
  ) {
    const sources =
      preview.eligible_sources ||
      [];

    if (
      preview.available !== true ||
      !sources.length
    ) {
      const completed =
        preview.completed_deliveries ||
        [];

      host.innerHTML = `
        <section class="card capacity-result ready news-empty-state">
          <span class="capacity-kicker">
            ${
              completed.length
                ? "当前没有新的可用内容"
                : "当前暂无可用的 News 内容"
            }
          </span>

          <h2>
            ${
              completed.length
                ? "已有 News 已完成"
                : "还没有适合创建 News 的历史内容"
            }
          </h2>

          <p>
            ${
              completed.length
                ? "当前没有新的历史内容可以转成 News。已完成的内容不会重复创建，避免重复交付；后续有新的符合条件内容时，会自动出现在这里。"
                : "News 会从已经导出的历史内容中选择适合的价格或优惠信息来生成。等有符合条件的内容后，这里会自动出现。"
            }
          </p>

          ${
            completed.length
              ? `
                <div class="news-completed-list">
                  <strong>最近已完成</strong>

                  ${completed
                    .map(
                      (item) => `
                        <div class="news-completed-item">
                          <div>
                            <span>
                              ${Number(
                                item.slot_count || 0,
                              )}
                              个标题
                            </span>

                            <strong>
                              ${escapeHtml(
                                String(
                                  item.output_name ||
                                    item.request_id ||
                                    "",
                                ),
                              )}
                            </strong>
                          </div>

                          <a
                            class="btn btn-secondary"
                            href="/api/create/news/${encodeURIComponent(
                              item.request_id,
                            )}/excel"
                          >
                            下载
                          </a>
                        </div>`,
                    )
                    .join("")}
                </div>`
              : ""
          }
        </section>`;
      return;
    }

    host.innerHTML = `
      <section class="card capacity-result ready">
        <span class="capacity-kicker">
          News V1 · 已验证 Price / Offer 路径
        </span>

        <h2>
          找到 ${sources.length}
          条可复用的历史内容
        </h2>

        <p>
          请选择一条 Strong Historical Content。
          系统会根据真实事实容量推荐 4–8 个标题，
          不把 Profile 切换当作新语义内容。
        </p>

        <div class="news-source-list">
          ${sources
            .map(
              (source, index) => `
                <label class="news-source-card">
                  <input
                    type="radio"
                    name="news-source-content"
                    value="${escapeHtml(
                      String(
                        source.source_content_id ||
                          "",
                      ),
                    )}"
                    ${
                      index === 0
                        ? "checked"
                        : ""
                    }
                  >

                  <div>
                    <div class="delivery-script-head">
                      <strong>
                        ${escapeHtml(
                          String(
                            source.source_title ||
                              source.source_content_id ||
                              "",
                          ),
                        )}
                      </strong>

                      <span class="badge approved">
                        推荐
                        ${Number(
                          source.recommended_slot_count ||
                            0,
                        )}
                        个标题
                      </span>
                    </div>

                    <p>
                      ${escapeHtml(
                        String(
                          source.source_central_claim ||
                            "",
                        ),
                      )}
                    </p>
                  </div>
                </label>`,
            )
            .join("")}
        </div>

        ${
          (preview.completed_deliveries || []).length
            ? `
              <div class="news-completed-list compact">
                <strong>最近已完成</strong>
                ${(preview.completed_deliveries || [])
                  .slice(0, 3)
                  .map(
                    (item) => `
                      <div class="news-completed-item">
                        <div>
                          <span>
                            ${Number(
                              item.slot_count || 0,
                            )}
                            个标题
                          </span>

                          <strong>
                            ${escapeHtml(
                              String(
                                item.output_name ||
                                  item.request_id ||
                                  "",
                              ),
                            )}
                          </strong>
                        </div>

                        <a
                          class="btn btn-secondary"
                          href="/api/create/news/${encodeURIComponent(
                            item.request_id,
                          )}/excel"
                        >
                          下载
                        </a>
                      </div>`,
                  )
                  .join("")}
              </div>`
            : ""
        }

        <div class="capacity-authority-note">
          <strong>当前不是 Novel Content Generation</strong>
          <span>
            本轮只改变已有 Strong Content 的 News 呈现方式；
            不调用远程模型，不新增 Semantic Ledger entry。
          </span>
        </div>

        <button
          type="button"
          class="btn btn-primary btn-wide"
          data-news-create-request
        >
          建立 News 内容任务
        </button>
      </section>`;

    const button =
      host.querySelector(
        "[data-news-create-request]",
      );

    button?.addEventListener(
      "click",
      async () => {
        const selected =
          host.querySelector(
            'input[name="news-source-content"]:checked',
          )?.value;

        if (!selected) {
          showToast(
            "请选择一条历史内容。",
          );
          return;
        }

        button.disabled = true;
        button.textContent =
          "正在建立 News 内容任务…";

        try {
          const response = await api(
            "/api/create/news/request",
            {
              method: "POST",
              body: JSON.stringify({
                business_id:
                  preview.business_id,
                speaker_id:
                  preview.speaker_id,
                source_content_id:
                  selected,
                idempotency_key:
                  newKey(),
              }),
            },
          );

          const requestId =
            response.result
              .request
              .request_id;

          showToast(
            response.result.recovered
              ? "已恢复现有 News 内容任务。"
              : "News 内容任务已建立。",
          );

          if (
            typeof onRequestCreated ===
            "function"
          ) {
            await onRequestCreated(
              requestId,
            );
          } else {
            await restore(
              requestId,
              host,
            );
          }
        } catch (error) {
          showToast(
            error.detail?.next_action ||
              error.detail?.message ||
              error.message,
          );

          if (button.isConnected) {
            button.disabled = false;
            button.textContent =
              "建立 News 内容任务";
          }
        }
      },
    );
  }

  return {
    renderPreview,
    restore,
  };
}
