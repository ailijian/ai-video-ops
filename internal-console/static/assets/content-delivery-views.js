import { startTaskPolling } from "./task-progress.js";

export function createContentDeliveryViews({
  api,
  showToast,
  escapeHtml,
}) {
  function watchTask(task, refresh, completedMessage) {
    showToast("任务已进入后台队列，可以离开页面后再返回。");
    startTaskPolling({
      api,
      taskId: task.task_id,
      onUpdate: () => {},
      onDone: async (current) => {
        await refresh();
        showToast(
          current.status === "completed"
            ? completedMessage
            : current.error_message || "后台任务没有完成。",
        );
      },
      onError: () => {},
    });
  }
  const actionLabel = {
    CREATE_CONTENT_PLAN: "生成内容规划",
    GENERATE_SCRIPTS: "生成脚本",
    HUMAN_REVIEW: "人工审核",
    EXPORT_EXCEL: "导出 Excel",
    EXCEL_EXPORTED: "Excel 已导出",
  };

  function flagText(flag) {
    const value = String(flag || "");

    if (
      value ===
      "cross_concept_material_overlap_requires_human_review"
    ) {
      return "与同批其他稿存在信息重叠，请重点判断是否值得分别发布";
    }

    if (
      value ===
      "claim_candidates_require_human_review"
    ) {
      return "关键主张需要人工确认";
    }

    if (
      value.startsWith(
        "claim_language_requires_human_review",
      )
    ) {
      return "对比式表达需要人工确认";
    }

    if (
      value.startsWith(
        "grounding_requires_human_review",
      )
    ) {
      return "关键表达需要核对事实依据";
    }

    return value;
  }

  function progress(state) {
    const current = state.next_action;

    const steps = [
      ["CREATE_CONTENT_PLAN", "内容规划"],
      ["GENERATE_SCRIPTS", "脚本生成"],
      ["HUMAN_REVIEW", "人工审核"],
      ["EXPORT_EXCEL", "Excel 导出"],
    ];

    const order = {
      CREATE_CONTENT_PLAN: 0,
      GENERATE_SCRIPTS: 1,
      HUMAN_REVIEW: 2,
      EXPORT_EXCEL: 3,
      REVIEW_COMPLETE_NO_EXPORT: 3,
      EXCEL_EXPORTED: 4,
    };

    const currentIndex =
      order[current] ?? 0;

    return `
      <div class="delivery-progress">
        ${steps
          .map(
            ([key, label], index) => `
              <div class="delivery-step ${
                index < currentIndex
                  ? "done"
                  : index === currentIndex
                    ? "current"
                    : ""
              }">
                <span>${index < currentIndex ? "✓" : index + 1}</span>
                <strong>${escapeHtml(label)}</strong>
              </div>`,
          )
          .join("")}
      </div>`;
  }

  function conceptCards(state) {
    const concepts =
      state.content_plan?.selected_concepts ||
      [];

    if (!concepts.length) {
      return "";
    }

    return `
      <section class="card review-section">
        <h2>本轮最终选题</h2>
        <p>
          内容规划已锁定。
          脚本生成只能扩写这些选题，
          不能重新选题或新增事实。
        </p>

        <div class="delivery-script-list">
          ${concepts
            .map(
              (concept) => `
                <article class="delivery-script-card">
                  <div class="delivery-script-head">
                    <strong>${escapeHtml(
                      String(
                        concept.concept_id ||
                          "Concept",
                      ),
                    )}</strong>
                    <span class="badge approved">
                      ${escapeHtml(
                        String(
                          concept.effective_gate_decision ||
                            "selected",
                        ),
                      )}
                    </span>
                  </div>

                  <h3>
                    ${escapeHtml(
                      String(
                        concept.primary_topic ||
                          concept.content_job ||
                          "",
                      ),
                    )}
                  </h3>

                  <div class="review-row">
                    <span>用户问题</span>
                    <p>${escapeHtml(
                      String(
                        concept.audience_need ||
                          "",
                      ),
                    )}</p>
                  </div>

                  <div class="review-row">
                    <span>核心表达</span>
                    <p>${escapeHtml(
                      String(
                        concept.central_claim ||
                          "",
                      ),
                    )}</p>
                  </div>
                </article>`,
            )
            .join("")}
        </div>
      </section>`;
  }

  function reviewCards(state) {
    const contents =
      state.generation?.contents || [];

    return `
      <section class="card review-section">
        <h2>审核生成稿</h2>

        <p>
          每一条都需要选择：
          <strong>通过</strong>、
          <strong>修改后通过</strong>
          或 <strong>淘汰</strong>。
          Generated Candidate 会永久保留；
          人工修改只形成 Reviewed Revision，
          不会覆盖模型原稿。
        </p>

        <div class="delivery-script-list">
          ${contents
            .map(
              (item, index) => `
                <article
                  class="delivery-script-card unified-review-card"
                  data-review-item
                  data-content-id="${escapeHtml(
                    String(
                      item.content_id || "",
                    ),
                  )}"
                >
                  <div class="delivery-script-head">
                    <strong>
                      ${index + 1}.
                      ${escapeHtml(
                        String(
                          item.concept_ref || "",
                        ),
                      )}
                    </strong>
                    <span class="badge review">
                      待人工确认
                    </span>
                  </div>

                  <div class="review-row">
                    <span>模型原始标题</span>
                    <p>${escapeHtml(
                      String(
                        item.title || "",
                      ),
                    )}</p>
                  </div>

                  <div class="review-row">
                    <span>模型原始口播</span>
                    <p>${escapeHtml(
                      String(
                        item.narration || "",
                      ),
                    )}</p>
                  </div>

                  <details class="full-breakdown">
                    <summary>
                      查看 Authority 信息
                      <span>
                        Central Claim / Review Flags
                      </span>
                    </summary>

                    <div class="breakdown-body">
                      <h3>Central Claim（Revision 不可修改）</h3>
                      <p class="narration-text">
                        ${escapeHtml(
                          String(
                            item.central_claim || "",
                          ),
                        )}
                      </p>

                      <h3>需要关注</h3>
                      <div class="delivery-flags">
                        ${
                          (
                            item.potential_review_flags ||
                            []
                          ).length
                            ? (
                                item.potential_review_flags ||
                                []
                              )
                                .map(
                                  (flag) => `
                                    <span class="delivery-flag">
                                      ${escapeHtml(
                                        flagText(flag),
                                      )}
                                    </span>`,
                                )
                                .join("")
                            : `
                              <span class="delivery-flag quiet">
                                无额外 Review Flag
                              </span>`
                        }
                      </div>
                    </div>
                  </details>

                  <div class="unified-review-decisions">
                    <label class="unified-review-choice">
                      <input
                        type="radio"
                        name="review-${escapeHtml(
                          String(
                            item.content_id || "",
                          ),
                        )}"
                        value="approved"
                        data-review-decision
                      >
                      <span>
                        <strong>通过</strong>
                        <small>原稿直接进入 Approved Projection</small>
                      </span>
                    </label>

                    <label class="unified-review-choice">
                      <input
                        type="radio"
                        name="review-${escapeHtml(
                          String(
                            item.content_id || "",
                          ),
                        )}"
                        value="revised"
                        data-review-decision
                      >
                      <span>
                        <strong>修改后通过</strong>
                        <small>只允许编辑标题与口播，不新增事实</small>
                      </span>
                    </label>

                    <label class="unified-review-choice">
                      <input
                        type="radio"
                        name="review-${escapeHtml(
                          String(
                            item.content_id || "",
                          ),
                        )}"
                        value="rejected"
                        data-review-decision
                      >
                      <span>
                        <strong>淘汰</strong>
                        <small>不进入 Excel，也不进入 Historical Exposure</small>
                      </span>
                    </label>
                  </div>

                  <div
                    class="unified-revision-editor"
                    data-revision-editor
                    hidden
                  >
                    <div class="field">
                      <label>修改后的标题</label>
                      <input
                        type="text"
                        data-revised-title
                        value="${escapeHtml(
                          String(
                            item.title || "",
                          ),
                        )}"
                      >
                    </div>

                    <div class="field">
                      <label>修改后的口播</label>
                      <textarea
                        rows="6"
                        data-revised-narration
                      >${escapeHtml(
                        String(
                          item.narration || "",
                        ),
                      )}</textarea>
                    </div>

                    <p class="field-hint">
                      Revision V1 是编辑性改写：
                      Central Claim 不变、不能新增数字事实、
                      不能加入“保证 / 一定 / 最低价”等强化承诺。
                      如果要加入新事实，应回到 Customer Truth。
                    </p>
                  </div>

                  <div class="field">
                    <label>审核备注（可选）</label>
                    <input
                      type="text"
                      data-review-note
                      placeholder="例如：表达更自然；与同批内容重复；暂不值得发布"
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
            data-approve-all
          >
            全部标记通过
          </button>

          <button
            type="button"
            class="btn btn-primary"
            data-submit-review
          >
            提交人工审核
          </button>
        </div>

        <p class="field-hint">
          可以部分批准。
          例如生成 5 条，最终
          3 条原稿通过 + 1 条修改后通过 + 1 条淘汰，
          正式 Excel 只导出 4 条。
        </p>
      </section>`;
  }
  function renderBody(state) {
    const next =
      state.next_action ||
      "CREATE_CONTENT_PLAN";

    let body = "";

    if (next === "CREATE_CONTENT_PLAN") {
      body = `
        <section class="card review-section">
          <h2>准备生成 Content Plan</h2>
          <p>
            Source Plan 已完成。
            下一步会基于 Approved Persona、
            Content History 和 Source Plan
            生成候选选题，并通过 V1.1.1
            质量门筛选最终可生成内容。
          </p>

          <button
            type="button"
            class="btn btn-primary btn-wide"
            data-resolve-content-plan
          >
            生成并筛选 Content Plan
          </button>
        </section>`;
    }

    if (next === "GENERATE_SCRIPTS") {
      body = `
        ${conceptCards(state)}

        <section class="card review-section">
          <h2>Content Plan 已通过</h2>
          <p>
            本轮共有
            <strong>${Number(
              state.content_plan
                ?.selected_quantity || 0,
            )}</strong>
            个高质量选题。
            下一步才会真正调用 Script Generator。
          </p>

          <button
            type="button"
            class="btn btn-primary btn-wide"
            data-generate-scripts
          >
            根据最终选题生成脚本
          </button>
        </section>`;
    }

    if (next === "HUMAN_REVIEW") {
      body = `
        ${conceptCards(state)}
        ${reviewCards(state)}
      `;
    }

    if (
      next === "REVIEW_COMPLETE_NO_EXPORT"
    ) {
      body = `
        <section class="card capacity-result ready">
          <span class="capacity-kicker">
            Human Review 已完成
          </span>

          <h2>本批次没有可导出的内容</h2>

          <p>
            本批次所有 Generated Candidate 均已淘汰。
            它们不会进入 Excel，也不会写入 Historical Exposure。
            原始生成稿与审核记录仍会保留。
          </p>
        </section>`;
    }

    if (next === "EXPORT_EXCEL") {
      const excelAlreadyReady =
        state.export?.completed === true;

      body = `
        <section class="card capacity-result ready">
          <span class="capacity-kicker">
            人工审核已通过
          </span>

          <h2>
            ${
              excelAlreadyReady
                ? "Excel 已生成，正在等待内容历史闭合"
                : `${Number(
                    state.review
                      ?.approved_item_count || 0,
                  )} 条内容可以正式导出`
            }
          </h2>

          <div class="delivery-export-meta">
            <div>
              <span>客户</span>
              <strong>${escapeHtml(
                String(
                  state.business_display_name ||
                    state.business_id ||
                    "",
                ),
              )}</strong>
            </div>

            <div>
              <span>出镜人</span>
              <strong>${escapeHtml(
                String(
                  state.speaker_display_name ||
                    state.speaker_id ||
                    "",
                ),
              )}</strong>
            </div>

            <div>
              <span>视频类型</span>
              <strong>${escapeHtml(
                String(
                  state.profile_label ||
                    state.profile ||
                    "",
                ),
              )}</strong>
            </div>

            <div>
              <span>导出文件</span>
              <strong>${escapeHtml(
                String(
                  state.export?.output_name ||
                    "",
                ),
              )}</strong>
            </div>
          </div>

          <p>
            ${
              excelAlreadyReady
                ? "Excel 文件已经通过校验。本次操作只会完成内容历史闭合，不会重复导出或重新调用模型。"
                : "导出只读取已人工批准的稿件；内部审核字段不会写入运营 Excel。导出成功后，系统会同步闭合内容历史。"
            }
          </p>

          <button
            type="button"
            class="btn btn-primary btn-wide"
            data-export-excel
          >
            ${
              excelAlreadyReady
                ? "完成导出记录"
                : "导出正式 Excel"
            }
          </button>
        </section>`;
    }

    if (next === "EXCEL_EXPORTED") {
      const name =
        state.export?.output_name ||
        "approved_mix_scripts.xlsx";

      body = `
        <section class="card capacity-result ready delivery-success">
          <span class="capacity-kicker">
            本轮停止点已达到
          </span>

          <h2>正式 Excel 已导出</h2>

          <div class="delivery-export-meta">
            <div>
              <span>客户</span>
              <strong>${escapeHtml(
                String(
                  state.business_display_name ||
                    state.business_id ||
                    "",
                ),
              )}</strong>
            </div>

            <div>
              <span>出镜人</span>
              <strong>${escapeHtml(
                String(
                  state.speaker_display_name ||
                    state.speaker_id ||
                    "",
                ),
              )}</strong>
            </div>

            <div>
              <span>视频类型</span>
              <strong>${escapeHtml(
                String(
                  state.profile_label ||
                    state.profile ||
                    "",
                ),
              )}</strong>
            </div>

            <div>
              <span>导出条数</span>
              <strong>
                ${Number(
                  state.export
                    ?.exported_row_count || 0,
                )} 条
              </strong>
            </div>

            <div class="wide">
              <span>文件名</span>
              <strong>${escapeHtml(name)}</strong>
            </div>

            <div>
              <span>内容历史</span>
              <strong>
                ${
                  state.export_closure
                    ?.completed
                    ? "已闭合"
                    : "待闭合"
                }
              </strong>
            </div>
          </div>

          <a
            class="btn btn-primary btn-wide"
            href="/api/create/${encodeURIComponent(
              state.request_id,
            )}/exported-excel"
          >
            下载 ${escapeHtml(name)}
          </a>
        </section>`;
    }

    return body;
  }

  function bind(
    host,
    state,
    refresh,
  ) {
    const planButton =
      host.querySelector(
        "[data-resolve-content-plan]",
      );

    if (planButton) {
      planButton.addEventListener(
        "click",
        async () => {
          planButton.disabled = true;
          planButton.textContent =
            "正在生成并筛选 Content Plan…";

          try {
            const response = await api(
              `/api/create/${encodeURIComponent(
                state.request_id,
              )}/resolve-content-plan`,
              { method: "POST" },
            );

            watchTask(
              response.task,
              refresh,
              "Content Plan 任务已结束，已重新读取当前业务状态。",
            );
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            );

            if (planButton.isConnected) {
              planButton.disabled = false;
              planButton.textContent =
                "生成并筛选 Content Plan";
            }
          }
        },
      );
    }

    const generateButton =
      host.querySelector(
        "[data-generate-scripts]",
      );

    if (generateButton) {
      generateButton.addEventListener(
        "click",
        async () => {
          generateButton.disabled = true;
          generateButton.textContent =
            "正在生成脚本…";

          try {
            const response = await api(
              `/api/create/${encodeURIComponent(
                state.request_id,
              )}/generate-scripts`,
              { method: "POST" },
            );

            watchTask(
              response.task,
              refresh,
              "Script Generation 任务已结束，已重新读取当前业务状态。",
            );
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            );

            if (
              generateButton.isConnected
            ) {
              generateButton.disabled =
                false;
              generateButton.textContent =
                "根据最终选题生成脚本";
            }
          }
        },
      );
    }

    host
      .querySelectorAll(
        "[data-review-item]",
      )
      .forEach((card) => {
        const editor =
          card.querySelector(
            "[data-revision-editor]",
          );

        card
          .querySelectorAll(
            "[data-review-decision]",
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
        "[data-approve-all]",
      );

    if (approveAll) {
      approveAll.addEventListener(
        "click",
        () => {
          host
            .querySelectorAll(
              "[data-review-item]",
            )
            .forEach((card) => {
              const approved =
                card.querySelector(
                  'input[data-review-decision][value="approved"]',
                );
              const editor =
                card.querySelector(
                  "[data-revision-editor]",
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

    const submitReview =
      host.querySelector(
        "[data-submit-review]",
      );

    if (submitReview) {
      submitReview.addEventListener(
        "click",
        async () => {
          const cards = Array.from(
            host.querySelectorAll(
              "[data-review-item]",
            ),
          );

          if (!cards.length) {
            showToast(
              "当前没有可审核内容。",
            );
            return;
          }

          const items = [];

          for (const card of cards) {
            const decision =
              card.querySelector(
                "input[data-review-decision]:checked",
              )?.value;

            if (!decision) {
              showToast(
                "请逐条选择“通过 / 修改后通过 / 淘汰”。",
              );
              return;
            }

            const item = {
              content_id:
                card.dataset.contentId,
              decision,
              note:
                card.querySelector(
                  "[data-review-note]",
                )?.value?.trim() || "",
            };

            if (decision === "revised") {
              const revisedTitle =
                card.querySelector(
                  "[data-revised-title]",
                )?.value?.trim() || "";
              const revisedNarration =
                card.querySelector(
                  "[data-revised-narration]",
                )?.value?.trim() || "";

              if (
                !revisedTitle
                || !revisedNarration
              ) {
                showToast(
                  "修改后通过的标题和口播都不能为空。",
                );
                return;
              }

              item.revised_title =
                revisedTitle;
              item.revised_narration =
                revisedNarration;
            }

            items.push(item);
          }

          submitReview.disabled = true;
          submitReview.textContent =
            "正在提交 Human Review…";

          try {
            const response = await api(
              `/api/create/${encodeURIComponent(
                state.request_id,
              )}/review`,
              {
                method: "POST",
                body: JSON.stringify({
                  note:
                    "Internal Console Unified Human Review V1.",
                  items,
                }),
              },
            );

            const result =
              response.result?.result;

            if (
              result?.approved_item_count > 0
            ) {
              showToast(
                `Human Review 已完成：${Number(
                  result.approved_item_count,
                )} 条可导出，${Number(
                  result.rejected_item_count || 0,
                )} 条淘汰。`,
              );
            } else {
              showToast(
                "Human Review 已完成：本批次没有可导出内容。",
              );
            }

            await refresh();
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.detail?.message ||
                error.message,
            );

            if (
              submitReview.isConnected
            ) {
              submitReview.disabled = false;
              submitReview.textContent =
                "提交人工审核";
            }
          }
        },
      );
    }

    const exportButton =
      host.querySelector(
        "[data-export-excel]",
      );

    if (exportButton) {
      exportButton.addEventListener(
        "click",
        async () => {
          exportButton.disabled = true;
          exportButton.textContent =
            state.export?.completed
              ? "正在闭合内容历史…"
              : "正在导出并验证 Excel…";

          try {
            const response = await api(
              `/api/create/${encodeURIComponent(
                state.request_id,
              )}/export-mix`,
              { method: "POST" },
            );
            watchTask(
              response.task,
              refresh,
              "导出任务已结束，已重新读取 Export Receipt 与 Ledger 状态。",
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
              exportButton.disabled =
                false;
              exportButton.textContent =
                state.export?.completed
                  ? "完成导出记录"
                  : "导出正式 Excel";
            }
          }
        },
      );
    }
  }

  async function restore(requestId) {
    const host =
      document.querySelector(
        "#content-delivery-host",
      );

    if (!host || !requestId) {
      return;
    }

    host.innerHTML = `
      <section class="card review-section">
        <h2>正在恢复 内容交付 状态…</h2>
      </section>`;

    try {
      const response = await api(
        `/api/create/${encodeURIComponent(
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
                  内容交付
                </span>
                <h2>
                  ${escapeHtml(
                    actionLabel[
                      state.next_action
                    ] ||
                      state.next_action ||
                      "继续创作",
                  )}
                </h2>
              </div>

              <code>
                ${escapeHtml(
                  String(
                    state.request_id || "",
                  ),
                )}
              </code>
            </div>

            ${progress(state)}
          </section>

          ${renderBody(state)}
        </div>`;

      bind(
        host,
        state,
        () => restore(requestId),
      );
    } catch (error) {
      host.innerHTML = `
        <section class="card capacity-result blocked">
          <span class="capacity-kicker">
            内容交付 状态恢复失败
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
    }
  }

  return {
    restore,
  };
}
