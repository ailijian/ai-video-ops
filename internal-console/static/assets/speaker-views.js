import { escapeHtml } from "./case-components.js";

import {
  displayFactValue,
  editableFactValue,
  parseEditedFactValue,
} from "./customer-components.js";

import {
  speakerFieldLabel,
  speakerProgressPanel,
  speakerStatusPill,
  speakerTypeLabel,
} from "./speaker-components.js";

import { startTaskPolling } from "./task-progress.js";

export function createSpeakerViews({
  app,
  api,
  navigate,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  renderLoadError,
}) {
  let stopPolling = null;

  function stopTaskPolling() {
    stopPolling?.();
    stopPolling = null;
  }

  function bindSpeakerProgress(
    task,
    businessId,
    speakerId,
  ) {
    const host = document.querySelector(
      "[data-speaker-progress]",
    );

    if (!host) return;

    host.innerHTML = speakerProgressPanel(task);

    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,

      onUpdate(next) {
        const current = document.querySelector(
          "[data-speaker-progress]",
        );

        if (current) {
          current.innerHTML =
            speakerProgressPanel(next);
        }
      },

      onDone(next) {
        const current = document.querySelector(
          "[data-speaker-progress]",
        );

        if (!current) return;

        current.innerHTML =
          speakerProgressPanel(next);

        if (next.status === "awaiting_review") {
          current.insertAdjacentHTML(
            "beforeend",
            `
              <a
                class="btn btn-primary btn-wide progress-review-link"
                href="/customers/${encodeURIComponent(
                  businessId,
                )}/speakers/${encodeURIComponent(speakerId)}"
                data-route
              >
                去确认出镜人信息
              </a>`,
          );

          bindCommonActions();
        }
      },
    });
  }

  async function renderSpeakerNew(businessId) {
    stopTaskPolling();
    skeletonPage("添加出镜人");

    try {
      const customer = await api(
        `/api/customers/${encodeURIComponent(businessId)}`,
      );

      if (
        customer.business_persona?.approved !== true
      ) {
        return renderLoadError(
          "暂时不能添加出镜人",
          {
            message: "客户档案还没有批准。",
            detail: {
              next_action:
                "请先完成 Business Persona 审核。",
            },
          },
        );
      }

      app.innerHTML = shell(
        "添加出镜人",
        `
          <main class="page">
            <div class="case-review-heading">
              <a
                class="back-link"
                href="/customers/${encodeURIComponent(businessId)}"
                data-route
              >
                ← 返回客户详情
              </a>
            </div>

            ${pageHeading(
              "出镜人",
              "添加一个出镜人",
              `为“${customer.display_name}”建立独立的 Speaker Persona。这里只管理这个人可以以第一人称说什么。`,
            )}

            <div class="customer-new-layout">
              <section class="card customer-new-panel">
                <form id="speaker-new-form" novalidate>
                  <div class="field">
                    <label for="speaker-name">姓名</label>
                    <input
                      id="speaker-name"
                      maxlength="200"
                      autocomplete="off"
                      placeholder="例如：王琳"
                      required
                    >
                  </div>

                  <div class="field">
                    <label for="speaker-role">公开身份</label>
                    <input
                      id="speaker-role"
                      maxlength="200"
                      autocomplete="off"
                      placeholder="例如：店主、主理人、一线厨师"
                      required
                    >
                  </div>

                  <div class="field">
                    <label for="speaker-type">出镜人类型</label>
                    <select id="speaker-type" required>
                      <option value="owner_founder">店主 / 创始人</option>
                      <option value="frontline_expert">一线专业人员</option>
                      <option value="brand">品牌角色</option>
                      <option value="generic">其他出镜人</option>
                    </select>
                  </div>

                  <div class="field">
                    <label for="speaker-materials">已有资料</label>
                    <textarea
                      id="speaker-materials"
                      rows="11"
                      maxlength="50000"
                      placeholder="粘贴这个人的真实经历、实际职责、亲自做过的事情、擅长讲的内容、采访记录等。"
                      required
                    ></textarea>

                    <span class="field-hint">
                      Business Persona 中的经营事实不会自动变成这个人的第一人称经历。
                    </span>
                  </div>

                  <div class="field">
                    <label for="speaker-forbidden">
                      不能以第一人称表达
                    </label>

                    <textarea
                      id="speaker-forbidden"
                      rows="5"
                      placeholder="每行一条。例如：&#10;不得声称自己具备未提供的专业资质&#10;不得把未经确认的数据说成自己的经营结果"
                      required
                    ></textarea>

                    <span class="field-hint">
                      至少写一条明确边界。系统不会让 AI 自动决定这部分权限。
                    </span>
                  </div>

                  <div
                    id="speaker-form-error"
                    class="form-error"
                    role="alert"
                  ></div>

                  <div id="speaker-analysis-result"></div>

                  <div class="sticky-action">
                    <button
                      class="btn btn-primary btn-wide"
                      type="submit"
                    >
                      分析出镜人信息
                    </button>
                  </div>
                </form>
              </section>

              <aside class="card notice-card">
                <h2>两件事保持独立</h2>
                <p>
                  出镜人设只定义这个人可以用第一人称表达什么。
                </p>
                <p>
                  即使 Speaker Persona 最终批准，也不代表已经获得肖像、
                  视频或其他媒体素材使用授权。
                </p>
              </aside>
            </div>
          </main>`,
      );

      bindCommonActions();

      document
        .querySelector("#speaker-new-form")
        .addEventListener(
          "submit",
          async (event) => {
            event.preventDefault();

            const button =
              event.currentTarget.querySelector(
                "button[type=submit]",
              );

            const errorBox =
              document.querySelector(
                "#speaker-form-error",
              );

            const resultBox =
              document.querySelector(
                "#speaker-analysis-result",
              );

            errorBox.classList.remove("visible");
            resultBox.innerHTML = "";

            const forbiddenClaims =
              document
                .querySelector("#speaker-forbidden")
                .value
                .split(/\r?\n/)
                .map((item) => item.trim())
                .filter(Boolean);

            if (!forbiddenClaims.length) {
              errorBox.textContent =
                "请至少填写一条第一人称禁止表达边界。";
              errorBox.classList.add("visible");
              return;
            }

            button.disabled = true;
            button.textContent = "正在提交…";

            try {
              const result = await api(
                `/api/customers/${encodeURIComponent(
                  businessId,
                )}/speakers/analyze`,
                {
                  method: "POST",
                  body: JSON.stringify({
                    speaker_name:
                      document.querySelector(
                        "#speaker-name",
                      ).value,
                    public_role:
                      document.querySelector(
                        "#speaker-role",
                      ).value,
                    speaker_type:
                      document.querySelector(
                        "#speaker-type",
                      ).value,
                    materials:
                      document.querySelector(
                        "#speaker-materials",
                      ).value,
                    forbidden_claims:
                      forbiddenClaims,
                  }),
                },
              );

              if (result.duplicate) {
                if (
                  result.existing_task &&
                  ["queued", "running"].includes(
                    result.existing_task.status,
                  )
                ) {
                  resultBox.innerHTML =
                    `<div data-speaker-progress></div>`;

                  bindSpeakerProgress(
                    result.existing_task,
                    businessId,
                    result.speaker_id,
                  );

                  return;
                }

                return navigate(
                  `/customers/${encodeURIComponent(
                    businessId,
                  )}/speakers/${encodeURIComponent(
                    result.speaker_id,
                  )}`,
                );
              }

              resultBox.innerHTML =
                `<div data-speaker-progress></div>`;

              bindSpeakerProgress(
                result.task,
                businessId,
                result.speaker_id,
              );
            } catch (error) {
              errorBox.textContent =
                error.detail?.next_action ||
                error.message;

              errorBox.classList.add("visible");
            } finally {
              button.disabled = false;
              button.textContent =
                "分析出镜人信息";
            }
          },
        );
    } catch (error) {
      renderLoadError(
        "客户暂时无法读取",
        error,
      );
    }
  }

  function bindFactChoices(
    needsReview,
    {
        buttonId,
        submit,
    },
    ) {
    document
      .querySelectorAll("[data-speaker-fact-card]")
      .forEach((card) => {
        card
          .querySelectorAll("[data-speaker-fact-choice]")
          .forEach((button) => {
            button.addEventListener(
              "click",
              () => {
                const decision =
                  button.dataset.speakerFactChoice;

                card.dataset.decision =
                  decision;

                card
                  .querySelectorAll(
                    "[data-speaker-fact-choice]",
                  )
                  .forEach((item) => {
                    item.classList.toggle(
                      "active",
                      item === button,
                    );
                  });

                const editPanel =
                  card.querySelector(
                    ".fact-edit-panel",
                  );

                editPanel.hidden =
                  decision !== "edit";

                if (decision === "edit") {
                  editPanel
                    .querySelector("textarea")
                    .focus();
                }
              },
            );
          });
      });

    document
      .querySelector(buttonId)
      .addEventListener(
        "click",
        async () => {
          const decisions = [];

          for (const candidate of needsReview) {
            const card = document.querySelector(
              `[data-speaker-fact-card="${CSS.escape(
                candidate.candidate_id,
              )}"]`,
            );

            const decision =
              card?.dataset.decision;

            if (!decision) {
              showToast(
                `还有“${speakerFieldLabel(
                  candidate.field,
                )}”没有确认。`,
              );

              card?.scrollIntoView({
                behavior: "smooth",
                block: "center",
              });

              return;
            }

            const value = {
              candidate_id:
                candidate.candidate_id,
              decision,
              note:
                decision === "approve"
                  ? "Internal Console Human Review confirmed this Speaker fact."
                  : decision === "reject"
                    ? "Internal Console Human Review did not accept this Speaker fact."
                    : "Internal Console Human Review corrected this Speaker fact.",
            };

            if (decision === "edit") {
              try {
                value.edited_value =
                  parseEditedFactValue(
                    candidate.value,
                    card.querySelector(
                      ".fact-edit-panel textarea",
                    ).value,
                  );
              } catch (error) {
                showToast(error.message);
                return;
              }
            }

            decisions.push(value);
          }

          await submit(decisions);
        },
      );
  }

  function renderSpeakerFactReview(
    detail,
    businessId,
  ) {
    const candidates =
      detail.fact_candidates || [];

    const known = candidates.filter(
      (item) =>
        item.state === "known_candidate",
    );

    const needsReview = candidates.filter(
      (item) =>
        item.state === "requires_review",
    );

    const knownHtml = known.length
      ? `
        <section class="section">
          <div class="section-head">
            <div>
              <h2>已经明确的信息</h2>
              <p>
                姓名、公开身份和人工设定的表达边界来自直接输入。
              </p>
            </div>
          </div>

          <div class="fact-list">
            ${known
              .map(
                (item) => `
                  <article class="card fact-card confirmed">
                    <div class="fact-card-head">
                      <strong>
                        ${escapeHtml(
                          speakerFieldLabel(item.field),
                        )}
                      </strong>
                      <span class="pill pill-approved">
                        已确认
                      </span>
                    </div>

                    ${displayFactValue(item.value)}
                  </article>`,
              )
              .join("")}
          </div>
        </section>`
      : "";

    const reviewHtml = needsReview
      .map(
        (item) => `
          <article
            class="card fact-card"
            data-speaker-fact-card="${escapeHtml(
              item.candidate_id,
            )}"
          >
            <div class="fact-card-head">
              <strong>
                ${escapeHtml(
                  speakerFieldLabel(item.field),
                )}
              </strong>

              <span class="pill pill-review">
                需要确认
              </span>
            </div>

            ${displayFactValue(item.value)}

            ${
              item.source_excerpt
                ? `
                  <details class="fact-source">
                    <summary>查看依据</summary>
                    <p>${escapeHtml(
                      item.source_excerpt,
                    )}</p>
                  </details>`
                : ""
            }

            <div class="fact-choice-row">
              <button
                class="fact-choice"
                type="button"
                data-speaker-fact-choice="reject"
              >
                不采用
              </button>

              <button
                class="fact-choice"
                type="button"
                data-speaker-fact-choice="edit"
              >
                修改
              </button>

              <button
                class="fact-choice primary"
                type="button"
                data-speaker-fact-choice="approve"
              >
                确认
              </button>
            </div>

            <div class="fact-edit-panel" hidden>
              <label>修改后的事实</label>

              <textarea rows="4">${escapeHtml(
                editableFactValue(item.value),
              )}</textarea>

              <span>
                列表型内容请一行写一项。
              </span>
            </div>
          </article>`,
      )
      .join("");

    app.innerHTML = shell(
      "出镜人信息审核",
      `
        <main class="page customer-review-page">
          <div class="case-review-heading">
            <a
              class="back-link"
              href="/customers/${encodeURIComponent(
                businessId,
              )}"
              data-route
            >
              ← 返回客户详情
            </a>

            ${speakerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "出镜人信息审核",
            detail.display_name,
            detail.public_role
          )}

          <div class="speaker-boundary-banner">
            <strong>
              Business Fact 不会自动变成这个人的第一人称事实。
            </strong>
            <span>
              这里只审核这个人本人可以承担的职责、经历和表达范围。
            </span>
          </div>

          ${knownHtml}

          <section class="section">
            <div class="section-head">
              <div>
                <h2>需要你确认</h2>
                <p>
                  ${needsReview.length}
                  条 AI 提取结果仍不是 Speaker Truth。
                </p>
              </div>
            </div>

            <div class="fact-list">
              ${reviewHtml}
            </div>
          </section>

          <div class="sticky-action">
            <button
              id="submit-speaker-fact-review"
              class="btn btn-primary btn-wide"
              type="button"
            >
              确认这些信息
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();

    bindFactChoices(
      needsReview,
      {
        buttonId:
          "#submit-speaker-fact-review",

        submit: async (decisions) => {
          const button =
            document.querySelector(
              "#submit-speaker-fact-review",
            );

          button.disabled = true;
          button.textContent = "正在保存…";

          try {
            const result = await api(
              `/api/customers/${encodeURIComponent(
                businessId,
              )}/speakers/${encodeURIComponent(
                detail.speaker_id,
              )}/facts/review`,
              {
                method: "POST",
                body: JSON.stringify({
                  decisions,
                  note:
                    "Initial Speaker Fact Human Review completed.",
                }),
              },
            );

            if (
              result.review.status ===
              "completed_persona_blocked"
            ) {
              showToast(
                "已保存，但还缺少建立出镜人设所需的信息。",
              );
            } else {
              showToast(
                "出镜人事实已确认，进入人设总审核。",
              );
            }

            renderSpeakerDetail(
              businessId,
              detail.speaker_id,
            );
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.message,
            );

            button.disabled = false;
            button.textContent =
              "确认这些信息";
          }
        },
      },
    );
  }

  function renderSpeakerPersonaReview(
    detail,
    businessId,
  ) {
    const persona =
      detail.speaker_persona;

    const facts = (
      persona?.facts || []
    ).filter(
      (fact) => fact.state === "known",
    );

    app.innerHTML = shell(
      "出镜人设审核",
      `
        <main class="page customer-review-page">
          <div class="case-review-heading">
            <a
              class="back-link"
              href="/customers/${encodeURIComponent(
                businessId,
              )}"
              data-route
            >
              ← 返回客户详情
            </a>

            ${speakerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "出镜人设审核",
            detail.display_name,
            detail.public_role
          )}

          <div class="authority-banner">
            <strong>
              这是第二道人工作业门。
            </strong>

            <span>
              Speaker Facts 已确认，不等于 Speaker Persona 已批准。
              请从整体上确认这个人的第一人称表达边界是否可靠。
            </span>
          </div>

          <section class="section">
            <div class="section-head">
              <div>
                <h2>将进入正式人设的信息</h2>
                <p>
                  共 ${facts.length} 个已知 Speaker Facts。
                </p>
              </div>
            </div>

            <div class="fact-list">
              ${facts
                .map(
                  (fact) => `
                    <article class="card fact-card confirmed">
                      <div class="fact-card-head">
                        <strong>
                          ${escapeHtml(
                            speakerFieldLabel(fact.field),
                          )}
                        </strong>
                        <span class="pill pill-approved">
                          已确认
                        </span>
                      </div>

                      ${displayFactValue(fact.value)}
                    </article>`,
                )
                .join("")}
            </div>
          </section>

          <div class="rights-banner">
            <strong>
              批准人设不会建立媒体使用权。
            </strong>

            <span>
              肖像、视频、照片和其他生产素材授权仍由独立 Authority 管理。
            </span>
          </div>

          <div class="sticky-action">
            <button
              id="approve-speaker-persona"
              class="btn btn-primary btn-wide"
              type="button"
            >
              确认并建立出镜人设
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();

    document
      .querySelector(
        "#approve-speaker-persona",
      )
      .addEventListener(
        "click",
        async () => {
          if (
            !window.confirm(
              "确认已经整体复核这个人的第一人称表达权限，并批准 Speaker Persona？\n\n这不会建立肖像或视频素材使用权。",
            )
          ) {
            return;
          }

          const button =
            document.querySelector(
              "#approve-speaker-persona",
            );

          button.disabled = true;
          button.textContent = "正在批准…";

          try {
            await api(
              `/api/customers/${encodeURIComponent(
                businessId,
              )}/speakers/${encodeURIComponent(
                detail.speaker_id,
              )}/persona/approve`,
              {
                method: "POST",
                body: JSON.stringify({
                  note:
                    "Internal Console Human Review approved the complete Speaker Persona.",
                }),
              },
            );

            showToast(
              "出镜人设已批准",
            );

            renderSpeakerDetail(
              businessId,
              detail.speaker_id,
            );
          } catch (error) {
            showToast(
              error.detail?.next_action ||
                error.message,
            );

            button.disabled = false;
            button.textContent =
              "确认并建立出镜人设";
          }
        },
      );
  }

  function renderApprovedSpeaker(
    detail,
    businessId,
  ) {
    const facts = (
      detail.speaker_persona?.facts || []
    ).filter(
      (fact) => fact.state === "known",
    );

    app.innerHTML = shell(
      "出镜人详情",
      `
        <main class="page">
          <div class="case-review-heading">
            <a
              class="back-link"
              href="/customers/${encodeURIComponent(
                businessId,
              )}"
              data-route
            >
              ← 返回客户详情
            </a>

            ${speakerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "出镜人",
            detail.display_name,
            detail.public_role
          )}

          <section class="customer-overview-grid">
            <article class="card customer-overview-card">
              <span>Speaker Persona</span>
              <strong>已批准</strong>
              <p>
                这个人的第一人称表达 Authority 已经建立。
              </p>
            </article>

            <article class="card customer-overview-card">
              <span>媒体使用权</span>
              <strong>未建立</strong>
              <p>
                人设批准不等于肖像、视频或素材使用授权。
              </p>
            </article>
          </section>

          <section class="section">
            <div class="section-head">
              <div>
                <h2>出镜人设</h2>
                <p>
                  当前 Approved Speaker Persona 中的已知事实。
                </p>
              </div>
            </div>

            <div class="fact-list">
              ${facts
                .map(
                  (fact) => `
                    <article class="card fact-card confirmed">
                      <div class="fact-card-head">
                        <strong>
                          ${escapeHtml(
                            speakerFieldLabel(fact.field),
                          )}
                        </strong>
                      </div>

                      ${displayFactValue(fact.value)}
                    </article>`,
                )
                .join("")}
            </div>
          </section>

          <div class="rights-banner">
            <strong>
              Speaker Persona ≠ Media Rights
            </strong>

            <span>
              当前只证明“这个人可以以什么身份说什么”，
              不代表任何照片、视频或肖像素材已经获得生产授权。
            </span>
          </div>
        </main>`,
    );

    bindCommonActions();
  }

  function renderNeedsMoreInfo(
    detail,
    businessId,
  ) {
    const blockers =
      detail.fact_review
        ?.speaker_persona_blockers || [];

    app.innerHTML = shell(
      "出镜人信息待补充",
      `
        <main class="page">
          <div class="case-review-heading">
            <a
              class="back-link"
              href="/customers/${encodeURIComponent(
                businessId,
              )}"
              data-route
            >
              ← 返回客户详情
            </a>

            ${speakerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "出镜人",
            detail.display_name,
            "本轮确认结果已经保存，但现有 Speaker Truth 还不足以建立正式人设。",
          )}

          <section class="card notice-card">
            <h2>还缺少关键信息</h2>

            <p>
              ${
                blockers.length
                  ? blockers
                      .map((field) =>
                        speakerFieldLabel(field),
                      )
                      .join("、")
                  : "仍有关键 Speaker Truth 未确认。"
              }
            </p>

            <p>
              系统不会为了完成 Speaker Persona 而让 AI 自动补齐未知信息。
            </p>
          </section>
        </main>`,
    );

    bindCommonActions();
  }

  function renderFailedSpeaker(
    detail,
    businessId,
  ) {
    app.innerHTML = shell(
      "出镜人分析失败",
      `
        <main class="page">
          <div class="case-review-heading">
            <a
              class="back-link"
              href="/customers/${encodeURIComponent(
                businessId,
              )}"
              data-route
            >
              ← 返回客户详情
            </a>

            ${speakerStatusPill("failed")}
          </div>

          ${pageHeading(
            "出镜人",
            detail.display_name,
            "本次出镜人分析没有完成，已建立的客户档案不会受到影响。",
          )}

          <section class="card notice-card">
            <h2>分析没有完成</h2>

            <p>
              ${escapeHtml(
                detail.task?.error_message ||
                  "出镜人信息分析没有完成。",
              )}
            </p>

            <p>
              当前 V1 不会删除失败记录。可以返回客户详情后重新进入出镜人流程。
            </p>
          </section>
        </main>`,
    );

    bindCommonActions();
  }

  async function renderSpeakerDetail(
    businessId,
    speakerId,
  ) {
    stopTaskPolling();
    skeletonPage("出镜人详情");

    try {
      const detail = await api(
        `/api/customers/${encodeURIComponent(
          businessId,
        )}/speakers/${encodeURIComponent(speakerId)}`,
      );

      if (
        detail.status === "analyzing" &&
        detail.task
      ) {
        app.innerHTML = shell(
          "出镜人信息分析",
          `
            <main class="page">
              ${pageHeading(
                "出镜人",
                detail.display_name,
                "正在把已有资料整理成待确认的 Speaker Facts。",
              )}

              <div data-speaker-progress></div>
            </main>`,
        );

        bindCommonActions();

        bindSpeakerProgress(
          detail.task,
          businessId,
          speakerId,
        );

        return;
      }

      if (
        detail.status ===
        "fact_review_required"
      ) {
        return renderSpeakerFactReview(
          detail,
          businessId,
        );
      }

      if (
        detail.status ===
        "persona_review_required"
      ) {
        return renderSpeakerPersonaReview(
          detail,
          businessId,
        );
      }

      if (detail.status === "approved") {
        return renderApprovedSpeaker(
          detail,
          businessId,
        );
      }

      if (
        detail.status === "needs_more_info"
      ) {
        return renderNeedsMoreInfo(
          detail,
          businessId,
        );
      }

      if (detail.status === "failed") {
        return renderFailedSpeaker(
          detail,
          businessId,
        );
      }

      app.innerHTML = shell(
        "出镜人详情",
        `
          <main class="page">
            ${pageHeading(
              "出镜人",
              detail.display_name,
              "当前出镜人流程尚未到达可审核状态。",
            )}

            <section class="card notice-card">
              <h2>当前状态</h2>
              <p>${escapeHtml(
                detail.status || "未知",
              )}</p>
            </section>
          </main>`,
      );

      bindCommonActions();
    } catch (error) {
      renderLoadError(
        "出镜人暂时无法读取",
        error,
      );
    }
  }

  function renderSpeakerTaskDetail(
    task,
  ) {
    stopTaskPolling();

    const businessId =
      task.payload?.business_id;

    const speakerId =
      task.payload?.speaker_id ||
      task.subject_ref;

    app.innerHTML = shell(
      "任务进度",
      `
        <main class="page task-detail-page">
          ${pageHeading(
            "任务进度",
            task.payload?.speaker_name ||
              "出镜人信息分析",
            "正在从已有资料中提取待确认的 Speaker Facts。",
          )}

          <div data-speaker-progress>
            ${speakerProgressPanel(task)}
          </div>
        </main>`,
    );

    bindCommonActions();

    bindSpeakerProgress(
      task,
      businessId,
      speakerId,
    );
  }

  return {
    renderSpeakerNew,
    renderSpeakerDetail,
    renderSpeakerTaskDetail,
    stopTaskPolling,
  };
}