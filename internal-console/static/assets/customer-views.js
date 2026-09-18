import {
  customerCard,
  customerFieldLabel,
  customerProgressPanel,
  customerStatusPill,
  displayFactValue,
  editableFactValue,
  parseEditedFactValue,
} from "./customer-components.js";
import {
  speakerCard,
} from "./speaker-components.js";

import { escapeHtml } from "./case-components.js";
import { startTaskPolling } from "./task-progress.js";

export function createCustomerViews({
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

  function bindCustomerProgress(task, businessId) {
    const host = document.querySelector("[data-customer-progress]");
    if (!host) return;

    host.innerHTML = customerProgressPanel(task);

    stopPolling = startTaskPolling({
      api,
      taskId: task.task_id,

      onUpdate(next) {
        const current = document.querySelector("[data-customer-progress]");
        if (current) current.innerHTML = customerProgressPanel(next);
      },

      onDone(next) {
        const current = document.querySelector("[data-customer-progress]");
        if (!current) return;

        current.innerHTML = customerProgressPanel(next);

        if (next.status === "awaiting_review") {
          current.insertAdjacentHTML(
            "beforeend",
            `
              <a
                class="btn btn-primary btn-wide progress-review-link"
                href="/customers/${encodeURIComponent(businessId)}"
                data-route
              >
                去确认客户信息
              </a>`,
          );

          bindCommonActions();
        }
      },
    });
  }

  async function renderCustomers() {
    stopTaskPolling();
    skeletonPage("客户与人设");

    try {
      const data = await api("/api/customers");
      const customers = data.customers || [];

      const content = customers.length
        ? `
          <div class="customer-list">
            ${customers.map(customerCard).join("")}
          </div>`
        : `
          <section class="card empty-state">
            <h2>还没有客户</h2>
            <p>
              新建第一个客户，把已有介绍、采访记录和服务信息直接粘贴进来。
            </p>
            <a class="btn btn-primary" href="/customers/new" data-route>
              新建客户
            </a>
          </section>`;

      app.innerHTML = shell(
        "客户与人设",
        `
          <main class="page">
            ${pageHeading(
              "客户",
              "客户与人设",
              "客户事实与出镜人设分别审核。AI 提取的信息不会自动进入正式客户档案。",
              `
                <div class="section">
                  <a class="btn btn-primary" href="/customers/new" data-route>
                    + 新建客户
                  </a>
                </div>`,
            )}

            ${content}
          </main>`,
      );

      bindCommonActions();
    } catch (error) {
      renderLoadError("客户列表暂时无法读取", error);
    }
  }

  function renderCustomerNew() {
    stopTaskPolling();

    app.innerHTML = shell(
      "新建客户",
      `
        <main class="page">
          ${pageHeading(
            "新建客户",
            "先把你已经知道的放进来",
            "不用整理成表格。门店介绍、采访记录、服务流程、顾客问题等已有资料都可以直接粘贴。",
          )}

          <div class="customer-new-layout">
            <section class="card customer-new-panel">
              <form id="customer-new-form" novalidate>
                <div class="field">
                  <label for="customer-name">客户名称</label>
                  <input
                    id="customer-name"
                    autocomplete="off"
                    maxlength="200"
                    placeholder="例如：小爪宠物店"
                    required
                  >
                </div>

                <div class="field">
                  <label for="customer-industry">行业</label>
                  <input
                    id="customer-industry"
                    autocomplete="off"
                    maxlength="120"
                    placeholder="例如：宠物服务"
                    required
                  >
                </div>

                <div class="field">
                  <label for="customer-materials">已有资料</label>
                  <textarea
                    id="customer-materials"
                    rows="12"
                    maxlength="50000"
                    placeholder="把你现在已经知道的客户情况粘贴进来。采访记录、门店介绍、服务流程、价格、顾客问题都可以。"
                    required
                  ></textarea>
                  <span class="field-hint">
                    原始资料保留在本地 Authority；发送给模型前会先经过隐私安全投影。
                  </span>
                </div>

                <div id="customer-form-error" class="form-error" role="alert"></div>
                <div id="customer-analysis-result"></div>

                <div class="sticky-action">
                  <button class="btn btn-primary btn-wide" type="submit">
                    分析客户信息
                  </button>
                </div>
              </form>
            </section>

            <aside class="card notice-card">
              <h2>这一步不会建立正式客户档案</h2>
              <p>
                AI 只负责把已有资料整理成待确认事实。你仍需要逐条确认，
                最后再单独批准 Business Persona。
              </p>
            </aside>
          </div>
        </main>`,
    );

    bindCommonActions();

    document
      .querySelector("#customer-new-form")
      .addEventListener("submit", async (event) => {
        event.preventDefault();

        const button = event.currentTarget.querySelector(
          "button[type=submit]",
        );

        const errorBox = document.querySelector("#customer-form-error");
        const resultBox = document.querySelector(
          "#customer-analysis-result",
        );

        errorBox.classList.remove("visible");
        resultBox.innerHTML = "";

        button.disabled = true;
        button.textContent = "正在提交…";

        const payload = {
          customer_name: document.querySelector("#customer-name").value,
          industry: document.querySelector("#customer-industry").value,
          materials: document.querySelector("#customer-materials").value,
        };

        try {
          const result = await api("/api/customers/analyze", {
            method: "POST",
            body: JSON.stringify(payload),
          });

          if (result.duplicate) {
            if (
              result.existing_task &&
              ["queued", "running"].includes(result.existing_task.status)
            ) {
              resultBox.innerHTML = `<div data-customer-progress></div>`;
              bindCustomerProgress(
                result.existing_task,
                result.business_id,
              );
              return;
            }

            resultBox.innerHTML = `
              <div class="result-banner">
                <h3>这个客户已经存在</h3>
                <p>无需重新建立，可以直接继续现有流程。</p>
                <a
                  class="btn btn-secondary speaker-add-button"
                  href="/customers/${encodeURIComponent(result.business_id)}"
                  data-route
                >
                  查看现有客户
                </a>
              </div>`;

            bindCommonActions();
            return;
          }

          resultBox.innerHTML = `<div data-customer-progress></div>`;
          bindCustomerProgress(result.task, result.business_id);
        } catch (error) {
          errorBox.textContent =
            error.detail?.next_action || error.message;

          errorBox.classList.add("visible");
        } finally {
          button.disabled = false;
          button.textContent = "分析客户信息";
        }
      });
  }

  function renderFactReview(detail) {
    const candidates = detail.fact_candidates || [];

    const known = candidates.filter(
      (item) => item.state === "known_candidate",
    );

    const needsReview = candidates.filter(
      (item) => item.state === "requires_review",
    );

    const knownHtml = known.length
      ? `
        <section class="section">
          <div class="section-head">
            <div>
              <h2>已经明确的信息</h2>
              <p>这些来自你直接输入的客户身份信息。</p>
            </div>
          </div>

          <div class="fact-list">
            ${known
              .map(
                (item) => `
                  <article class="card fact-card confirmed">
                    <div class="fact-card-head">
                      <strong>${escapeHtml(
                        customerFieldLabel(item.field),
                      )}</strong>
                      <span class="pill pill-approved">已确认</span>
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
            data-fact-card="${escapeHtml(item.candidate_id)}"
          >
            <div class="fact-card-head">
              <strong>${escapeHtml(customerFieldLabel(item.field))}</strong>
              <span class="pill pill-review">需要确认</span>
            </div>

            ${displayFactValue(item.value)}

            ${
              item.source_excerpt
                ? `
                  <details class="fact-source">
                    <summary>查看依据</summary>
                    <p>${escapeHtml(item.source_excerpt)}</p>
                  </details>`
                : ""
            }

            <div class="fact-choice-row">
              <button
                class="fact-choice"
                type="button"
                data-fact-choice="reject"
              >
                不采用
              </button>

              <button
                class="fact-choice"
                type="button"
                data-fact-choice="edit"
              >
                修改
              </button>

              <button
                class="fact-choice primary"
                type="button"
                data-fact-choice="approve"
              >
                确认
              </button>
            </div>

            <div class="fact-edit-panel" hidden>
              <label>修改后的事实</label>
              <textarea rows="4">${escapeHtml(
                editableFactValue(item.value),
              )}</textarea>
              <span>列表型内容请一行写一项。</span>
            </div>
          </article>`,
      )
      .join("");

    app.innerHTML = shell(
      "客户信息审核",
      `
        <main class="page customer-review-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户列表
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "客户信息审核",
            detail.display_name,
            "AI 已经把现有资料整理成事实候选。请确认哪些信息可以进入正式客户档案。",
          )}

          ${knownHtml}

          <section class="section">
            <div class="section-head">
              <div>
                <h2>需要你确认</h2>
                <p>${needsReview.length} 条 AI 提取结果尚未形成 Customer Truth。</p>
              </div>
            </div>

            <div class="fact-list">${reviewHtml}</div>
          </section>

          <div class="sticky-action">
            <button
              id="submit-fact-review"
              class="btn btn-primary btn-wide"
              type="button"
            >
              确认这些信息
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();

    document.querySelectorAll("[data-fact-card]").forEach((card) => {
      card.querySelectorAll("[data-fact-choice]").forEach((button) => {
        button.addEventListener("click", () => {
          const decision = button.dataset.factChoice;

          card.dataset.decision = decision;

          card
            .querySelectorAll("[data-fact-choice]")
            .forEach((item) => {
              item.classList.toggle("active", item === button);
            });

          const editPanel = card.querySelector(".fact-edit-panel");
          editPanel.hidden = decision !== "edit";

          if (decision === "edit") {
            editPanel.querySelector("textarea").focus();
          }
        });
      });
    });

    document
      .querySelector("#submit-fact-review")
      .addEventListener("click", async () => {
        const decisions = [];

        for (const candidate of needsReview) {
          const card = document.querySelector(
            `[data-fact-card="${CSS.escape(candidate.candidate_id)}"]`,
          );

          const decision = card?.dataset.decision;

          if (!decision) {
            showToast(
              `还有“${customerFieldLabel(candidate.field)}”没有确认。`,
            );
            card?.scrollIntoView({
              behavior: "smooth",
              block: "center",
            });
            return;
          }

          const value = {
            candidate_id: candidate.candidate_id,
            decision,
            note:
              decision === "approve"
                ? "Internal Console Human Review confirmed this fact."
                : decision === "reject"
                  ? "Internal Console Human Review did not accept this fact."
                  : "Internal Console Human Review corrected this fact.",
          };

          if (decision === "edit") {
            try {
              value.edited_value = parseEditedFactValue(
                candidate.value,
                card.querySelector(".fact-edit-panel textarea").value,
              );
            } catch (error) {
              showToast(error.message);
              return;
            }
          }

          decisions.push(value);
        }

        const button = document.querySelector("#submit-fact-review");
        button.disabled = true;
        button.textContent = "正在保存…";

        try {
          const result = await api(
            `/api/customers/${encodeURIComponent(
              detail.business_id,
            )}/facts/review`,
            {
              method: "POST",
              body: JSON.stringify({
                decisions,
                note: "Initial Customer Truth Human Review completed.",
              }),
            },
          );

          if (
            result.review.status === "completed_persona_blocked"
          ) {
            showToast("已保存，但仍缺少建立客户档案所需的关键信息。");
          } else {
            showToast("客户信息已确认，进入客户档案总审核。");
          }

          renderCustomerDetail(detail.business_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "确认这些信息";
        }
      });
  }

  function renderPersonaReview(detail) {
    const persona = detail.business_persona;
    const facts = (persona?.facts || []).filter(
      (fact) => fact.state === "known",
    );

    app.innerHTML = shell(
      "客户档案审核",
      `
        <main class="page customer-review-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户列表
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "客户档案审核",
            detail.display_name,
            "单条事实已经完成确认。现在请从整体上再次检查客户档案，批准后它才会成为正式 Business Persona。",
          )}

          <div class="authority-banner">
            <strong>这是第二道人工作业门。</strong>
            <span>
              “事实已确认”不等于“客户档案已批准”。请从整体上检查是否准确、完整且适合进入生产。
            </span>
          </div>

          <section class="section">
            <div class="section-head">
              <div>
                <h2>将进入正式档案的信息</h2>
                <p>共 ${facts.length} 个已知事实。</p>
              </div>
            </div>

            <div class="fact-list">
              ${facts
                .map(
                  (fact) => `
                    <article class="card fact-card confirmed">
                      <div class="fact-card-head">
                        <strong>${escapeHtml(
                          customerFieldLabel(fact.field),
                        )}</strong>
                        <span class="pill pill-approved">已确认</span>
                      </div>
                      ${displayFactValue(fact.value)}
                    </article>`,
                )
                .join("")}
            </div>
          </section>

          <div class="sticky-action">
            <button
              id="approve-business-persona"
              class="btn btn-primary btn-wide"
              type="button"
            >
              确认并建立客户档案
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();

    document
      .querySelector("#approve-business-persona")
      .addEventListener("click", async () => {
        if (
          !window.confirm(
            "确认已经整体复核客户档案，并批准它成为正式 Business Persona？",
          )
        ) {
          return;
        }

        const button = document.querySelector(
          "#approve-business-persona",
        );

        button.disabled = true;
        button.textContent = "正在批准…";

        try {
          await api(
            `/api/customers/${encodeURIComponent(
              detail.business_id,
            )}/persona/approve`,
            {
              method: "POST",
              body: JSON.stringify({
                note:
                  "Internal Console Human Review approved the complete Business Persona.",
              }),
            },
          );

          showToast("客户档案已批准");
          renderCustomerDetail(detail.business_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "确认并建立客户档案";
        }
      });
  }

  async function renderCustomerEdit(businessId) {
    stopTaskPolling();
    skeletonPage("修改客户资料");

    try {
        const payload = await api(
        `/api/customers/${encodeURIComponent(
            businessId,
        )}/input`,
        );

        const source = payload.input;

        app.innerHTML = shell(
        "修改客户资料",
        `
            <main class="page">
            ${pageHeading(
                "重新分析",
                "修改已有资料",
                "本次修改不会覆盖之前的失败记录，而是建立一个新的 Intake。",
            )}

            <section class="card customer-new-panel">
                <form id="customer-edit-form">
                <div class="field">
                    <label for="customer-name">客户名称</label>
                    <input
                    id="customer-name"
                    maxlength="200"
                    value="${escapeHtml(source.customer_name || "")}"
                    required
                    >
                </div>

                <div class="field">
                    <label for="customer-industry">行业</label>
                    <input
                    id="customer-industry"
                    maxlength="120"
                    value="${escapeHtml(source.industry || "")}"
                    required
                    >
                </div>

                <div class="field">
                    <label for="customer-materials">已有资料</label>
                    <textarea
                    id="customer-materials"
                    rows="14"
                    maxlength="50000"
                    required
                    >${escapeHtml(source.materials || "")}</textarea>
                </div>

                <div id="customer-edit-error" class="form-error"></div>

                <div class="sticky-action">
                    <button class="btn btn-primary btn-wide" type="submit">
                    重新分析
                    </button>
                </div>
                </form>
            </section>
            </main>`,
        );

        bindCommonActions();

        document
        .querySelector("#customer-edit-form")
        .addEventListener("submit", async (event) => {
            event.preventDefault();

            const button =
            event.currentTarget.querySelector(
                "button[type=submit]",
            );

            button.disabled = true;
            button.textContent = "正在提交…";

            try {
            const result = await api(
                `/api/customers/${encodeURIComponent(
                businessId,
                )}/reanalyze`,
                {
                method: "POST",
                body: JSON.stringify({
                    customer_name:
                    document.querySelector(
                        "#customer-name",
                    ).value,
                    industry:
                    document.querySelector(
                        "#customer-industry",
                    ).value,
                    materials:
                    document.querySelector(
                        "#customer-materials",
                    ).value,
                }),
                },
            );

            showToast(
                result.new_intake
                ? `已建立 ${result.intake_id}`
                : "已继续使用原始资料",
            );

            navigate(
                `/customers/${encodeURIComponent(
                businessId,
                )}`,
            );
            } catch (error) {
            const errorBox =
                document.querySelector(
                "#customer-edit-error",
                );

            errorBox.textContent =
                error.detail?.next_action ||
                error.message;

            errorBox.classList.add(
                "visible",
            );

            button.disabled = false;
            button.textContent =
                "重新分析";
            }
        });
    } catch (error) {
        renderLoadError(
        "客户原始资料暂时无法读取",
        error,
        );
    }
    }

  function renderFailedCustomer(detail) {
    app.innerHTML = shell(
        "客户信息分析失败",
        `
        <main class="page">
            <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
                ← 返回客户列表
            </a>
            ${customerStatusPill("failed")}
            </div>

            ${pageHeading(
            "客户",
            detail.display_name,
            "上一次客户信息分析没有完成。已录入资料和失败记录都会保留。",
            )}

            <section class="card notice-card">
            <h2>分析没有完成</h2>
            <p>
                ${escapeHtml(
                detail.task?.error_message ||
                    "模型调用或分析过程没有完成。",
                )}
            </p>

            <div class="customer-recovery-actions">
                <button
                id="retry-customer-analysis"
                class="btn btn-primary"
                type="button"
                >
                继续分析
                </button>

                <a
                class="btn btn-secondary"
                href="/customers/${encodeURIComponent(
                    detail.business_id,
                )}/edit"
                data-route
                >
                修改资料后重新分析
                </a>
            </div>
            </section>

            <div class="authority-banner">
            <strong>失败记录不会被删除。</strong>
            <span>
                继续分析会使用原始 Intake；修改资料会建立新的 Intake，
                旧资料和失败记录仍然保留。
            </span>
            </div>
        </main>`,
    );

    bindCommonActions();

    document
        .querySelector("#retry-customer-analysis")
        .addEventListener("click", async () => {
        const button = document.querySelector(
            "#retry-customer-analysis",
        );

        button.disabled = true;
        button.textContent = "正在继续…";

        try {
            const result = await api(
            `/api/customers/${encodeURIComponent(
                detail.business_id,
            )}/retry`,
            {
                method: "POST",
            },
            );

            const task =
            result.task ||
            result.existing_task;

            showToast("已重新开始客户信息分析");

            app.innerHTML = shell(
            "客户信息分析",
            `
                <main class="page">
                ${pageHeading(
                    "客户",
                    detail.display_name,
                    "正在继续分析已有客户资料。",
                )}
                <div data-customer-progress></div>
                </main>`,
            );

            bindCommonActions();
            bindCustomerProgress(
            task,
            detail.business_id,
            );
        } catch (error) {
            showToast(
            error.detail?.next_action ||
                error.message,
            );

            button.disabled = false;
            button.textContent = "继续分析";
        }
        });
    }

  function renderApprovedCustomer(detail) {
    const facts = (
      detail.business_persona?.facts || []
    ).filter(
      (fact) => fact.state === "known",
    );

    const speakers =
      detail.speakers || [];
    
    const defaultSpeaker =
      speakers.find(
        (speaker) =>
          speaker.status ===
          "approved",
      );

    const speakerContent = speakers.length
      ? `
        <div class="speaker-list">
          ${speakers
            .map((speaker) =>
              speakerCard(
                speaker,
                detail.business_id,
              ),
            )
            .join("")}
        </div>`
      : `
        <section class="card speaker-empty-card">
          <h3>还没有出镜人</h3>
          <p>
            客户档案已经批准。下一步可以建立一个独立的 Speaker Persona。
          </p>

          <a
            class="btn btn-primary"
            href="/customers/${encodeURIComponent(
              detail.business_id,
            )}/speakers/new"
            data-route
          >
            + 添加出镜人
          </a>
        </section>`;

    const readiness = detail.creation_entry_ready
      ? `
        <section class="section">
          <article class="card creation-ready-card">
            <div>
              <span class="status-kicker">
                <span class="status-dot"></span>
                Persona 条件已完成
              </span>

              <h2>可以进入创作流程</h2>

              <p>
                已存在 Approved Business Persona 和至少一个
                Approved Speaker Persona。
              </p>

              <p class="creation-rights-note">
                这不代表肖像、视频或其他生产素材已经获得使用授权。
              </p>
            </div>

            <div class="content-ops-actions">
              <a
                class="btn btn-secondary"
                href="/customers/${encodeURIComponent(
                  detail.business_id,
                )}/content"
                data-route
              >
                内容运营
              </a>

              <a
                class="btn btn-primary"
                href="/create?business_id=${encodeURIComponent(
                  detail.business_id,
                )}&speaker_id=${encodeURIComponent(
                  defaultSpeaker?.speaker_id || "",
                )}"
                data-route
              >
                开始创作
              </a>
            </div>
          </article>
        </section>`
      : "";

    app.innerHTML = shell(
      "客户详情",
      `
        <main class="page">
          <div class="case-review-heading">
            <a
              class="back-link"
              href="/customers"
              data-route
            >
              ← 返回客户列表
            </a>

            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "客户",
            detail.display_name,
            detail.industry,
          )}

          <section class="customer-overview-grid">
            <article class="card customer-overview-card">
              <span>客户档案</span>
              <strong>已批准</strong>
              <p>
                Business Persona 已完成 Human Approval。
              </p>
            </article>

            <article class="card customer-overview-card">
              <span>出镜人设</span>
              <strong>
                ${Number(detail.speaker_count || 0)} 个
              </strong>
              <p>
                Business Persona 与 Speaker Persona 独立管理。
              </p>
            </article>
          </section>

          <section class="section">
            <div class="section-head">
              <div>
                <h2>出镜人</h2>
                <p>
                  管理谁可以以什么身份进行第一人称表达。
                </p>
              </div>

              ${
                speakers.length
                  ? `
                    <a
                      class="btn btn-secondary"
                      href="/customers/${encodeURIComponent(
                        detail.business_id,
                      )}/speakers/new"
                      data-route
                    >
                      + 添加出镜人
                    </a>`
                  : ""
              }
            </div>

            ${speakerContent}
          </section>

          ${readiness}

          <section class="section">
            <div class="section-head">
              <div>
                <h2>客户信息</h2>
                <p>
                  当前 Approved Business Persona 中的已知事实。
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
                            customerFieldLabel(
                              fact.field,
                            ),
                          )}
                        </strong>
                      </div>

                      ${displayFactValue(
                        fact.value,
                      )}
                    </article>`,
                )
                .join("")}
            </div>
          </section>

          <div class="rights-banner">
            <strong>
              出镜人设与媒体使用权是两套 Authority。
            </strong>

            <span>
              Speaker Persona Approved 只定义第一人称表达权限，
              不自动赋予任何照片、视频或肖像素材生产使用权。
            </span>
          </div>
        </main>`,
    );

    bindCommonActions();
  }

  function renderNeedsMoreInfo(detail) {
    const blockers =
      detail.fact_review?.business_persona_blockers || [];

    app.innerHTML = shell(
      "客户信息待补充",
      `
        <main class="page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户列表
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "客户信息",
            detail.display_name,
            "已经保存本轮人工确认结果，但现有 Customer Truth 还不足以建立 Business Persona。",
          )}

          <section class="card notice-card">
            <h2>还缺少关键信息</h2>
            <p>
              ${
                blockers.length
                  ? blockers
                      .map((field) => customerFieldLabel(field))
                      .join("、")
                  : "仍有关键 Customer Truth 未确认。"
              }
            </p>
            <p>
              不会为了完成档案而让 AI 自动补齐未知信息。
            </p>
          </section>
        </main>`,
    );

    bindCommonActions();
  }

  async function renderCustomerDetail(businessId) {
    stopTaskPolling();
    skeletonPage("客户详情");

    try {
      const detail = await api(
        `/api/customers/${encodeURIComponent(businessId)}`,
      );

      if (
        detail.status === "analyzing" &&
        detail.task
      ) {
        app.innerHTML = shell(
          "客户信息分析",
          `
            <main class="page">
              ${pageHeading(
                "客户",
                detail.display_name,
                "正在把已有资料整理成待确认事实。",
              )}
              <div data-customer-progress></div>
            </main>`,
        );

        bindCommonActions();
        bindCustomerProgress(detail.task, businessId);
        return;
      }
      
      if (detail.status === "failed") {
        return renderFailedCustomer(detail);
        }
      if (detail.status === "fact_review_required") {
        return renderFactReview(detail);
      }

      if (detail.status === "persona_review_required") {
        return renderPersonaReview(detail);
      }

      if (detail.status === "approved") {
        return renderApprovedCustomer(detail);
      }

      if (detail.status === "needs_more_info") {
        return renderNeedsMoreInfo(detail);
      }

      app.innerHTML = shell(
        "客户详情",
        `
          <main class="page">
            ${pageHeading(
              "客户",
              detail.display_name,
              "当前客户流程尚未到达可审核状态。",
            )}
            <section class="card notice-card">
              <h2>当前状态</h2>
              <p>${escapeHtml(detail.status || "未知")}</p>
            </section>
          </main>`,
      );

      bindCommonActions();
    } catch (error) {
      renderLoadError("客户暂时无法读取", error);
    }
  }

  function renderCustomerTaskDetail(task) {
    stopTaskPolling();

    const businessId = task.subject_ref;

    app.innerHTML = shell(
      "任务进度",
      `
        <main class="page task-detail-page">
          ${pageHeading(
            "任务进度",
            task.payload?.customer_name || "客户信息分析",
            "正在从已有客户资料中提取待确认事实。你可以离开这个页面。",
          )}
          <div data-customer-progress>
            ${customerProgressPanel(task)}
          </div>
        </main>`,
    );

    bindCommonActions();
    bindCustomerProgress(task, businessId);
  }

  return {
    renderCustomers,
    renderCustomerNew,
    renderCustomerEdit,
    renderCustomerDetail,
    renderCustomerTaskDetail,
    stopTaskPolling,
    };
}