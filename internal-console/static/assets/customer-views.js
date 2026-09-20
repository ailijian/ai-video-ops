import {
  customerCard,
  customerFieldLabel,
  customerProgressPanel,
  customerStatusPill,
  editableFactValue,
  parseEditedFactValue,
} from "./customer-components.js?v=productized-stage2-3";
import {
  speakerCard,
} from "./speaker-components.js?v=productized-stage2-3";

import { escapeHtml } from "./case-components.js";
import {
  bindDecisionControls,
  NeedsInfoState,
  ProfileRow,
  ProfileSection,
  ProfileSummary,
  ProfileTabs,
  ReviewList,
} from "./profile-components.js?v=productized-stage2-3";
import { startTaskPolling } from "./task-progress.js";

const CUSTOMER_PROFILE_GROUPS = [
  {
    title: "基础信息",
    fields: [
      "public_display_name",
      "company_short_name",
      "industry",
      "years_in_business",
      "service_area",
      "location_public_area",
    ],
  },
  {
    title: "产品与服务",
    fields: [
      "primary_products_or_services",
      "secondary_products_or_services",
      "product_or_service_facts",
      "pricing_facts",
      "included_service_facts",
      "process_facts",
      "service_process",
      "service_time_facts",
    ],
  },
  {
    title: "客户与场景",
    fields: [
      "core_audience",
      "customer_use_cases",
      "customer_pains",
      "differentiators",
      "selection_reasons",
      "authorized_customer_cases_or_feedback",
    ],
  },
  {
    title: "经营与品牌",
    fields: [
      "brand_story",
      "founder_or_operator_story",
      "important_turning_points",
      "business_volume_fact",
      "time_efficiency_fact",
      "values",
      "business_principles",
      "beliefs",
      "tone_preferences",
    ],
  },
];

function customerProfileSections(facts = []) {
  const values = new Map(
    facts
      .filter((fact) => fact.state === "known")
      .map((fact) => [fact.field, fact.value]),
  );
  const grouped = new Set(CUSTOMER_PROFILE_GROUPS.flatMap((group) => group.fields));
  const sections = CUSTOMER_PROFILE_GROUPS.map((group) =>
    ProfileSection({
      title: group.title,
      rows: group.fields.map((field) =>
        ProfileRow({
          label: customerFieldLabel(field),
          value: values.get(field),
          labelFor: customerFieldLabel,
        }),
      ),
    }),
  );
  const other = facts.filter(
    (fact) => fact.state === "known" && !grouped.has(fact.field),
  );
  if (other.length) {
    sections.push(
      ProfileSection({
        title: "其他信息",
        rows: other.map((fact) =>
          ProfileRow({
            label: customerFieldLabel(fact.field),
            value: fact.value,
            labelFor: customerFieldLabel,
          }),
        ),
      }),
    );
  }
  return sections.filter(Boolean).join("");
}

export function createCustomerViews({
  app,
  api,
  navigate,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  openModal,
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
              <div class="progress-complete-actions">
                <p>客户信息已经整理好，可以开始确认。</p>
                <a class="btn btn-primary" href="/customers/${encodeURIComponent(businessId)}" data-route>确认客户信息</a>
                <a class="btn btn-secondary" href="/customers" data-route>返回客户</a>
              </div>`,
          );

          bindCommonActions();
        }
      },
    });
  }

  async function renderCustomers() {
    stopTaskPolling();
    skeletonPage("客户");

    try {
      const data = await api("/api/customers");
      const customers = data.customers || [];

      const content = customers.length
        ? `
          <div class="customer-list">
            ${customers.map(customerCard).join("")}
          </div>`
        : `
          <section class="state-panel empty-state">
            <span class="empty-icon" aria-hidden="true">＋</span>
            <h2>还没有客户</h2>
            <p>把已有介绍、采访记录和服务信息放进来，建立第一个客户档案。</p>
            <a class="btn btn-primary" href="/customers/new" data-route>
              新建客户
            </a>
          </section>`;

      app.innerHTML = shell(
        "客户",
        `
          <main class="page page-standard customer-list-page">
            ${pageHeading(
              "",
              "客户",
              "集中查看客户状态、出镜人和下一步工作。",
              `
                <a class="btn btn-primary" href="/customers/new" data-route>
                  新建客户
                </a>`,
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
        <main class="page page-form profile-mutation-page">
          ${pageHeading(
            "",
            "新建客户",
            "把你已经知道的客户资料放进来。",
          )}

          <section class="work-surface profile-form-surface" data-customer-new-surface>
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
                    门店介绍、采访记录、服务流程、价格和顾客问题都可以直接粘贴。
                  </span>
                </div>

                <div id="customer-form-error" class="form-error" role="alert"></div>
                <div class="profile-form-actions">
                  <button class="btn btn-primary btn-wide" type="submit">
                    分析客户信息
                  </button>
                </div>
                <p class="governance-copy">系统会先整理资料，之后仍需要你确认。</p>
              </form>
          </section>
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
        const surface = document.querySelector("[data-customer-new-surface]");

        errorBox.classList.remove("visible");

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
              surface.innerHTML = `<div data-customer-progress></div>`;
              bindCustomerProgress(
                result.existing_task,
                result.business_id,
              );
              return;
            }

            surface.innerHTML = `
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

          surface.innerHTML = `<div data-customer-progress></div>`;
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
        <details class="known-facts-disclosure">
          <summary>已经明确的信息 <span>${known.length} 项</span></summary>
          <dl class="profile-rows">
            ${known
              .map((item) =>
                ProfileRow({
                  label: customerFieldLabel(item.field),
                  value: item.value,
                  labelFor: customerFieldLabel,
                }),
              )
              .join("")}
          </dl>
        </details>`
      : "";

    app.innerHTML = shell(
      "确认客户信息",
      `
        <main class="page page-form customer-review-page profile-review-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "",
            "确认客户信息",
            `请检查“${detail.display_name}”的待确认信息。确认后的信息将用于后续视频内容。`,
          )}

          ${knownHtml}

          <section class="work-surface review-surface">
            <div class="review-surface-heading">
              <h2>需要你确认</h2>
              <p>逐项选择不采用、修改或确认。</p>
            </div>
            ${ReviewList({
              items: needsReview,
              labelFor: customerFieldLabel,
              namespace: "customer",
              editableValueFor: editableFactValue,
            })}
          </section>

          <div class="sticky-action review-submit-bar">
            <span data-review-progress>已确认 0 / ${needsReview.length}</span>
            <button
              id="submit-fact-review"
              class="btn btn-primary"
              type="button"
            >
              确认这些信息
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();
    bindDecisionControls({ submitSelector: "#submit-fact-review" });

    document
      .querySelector("#submit-fact-review")
      .addEventListener("click", async () => {
        const decisions = [];

        for (const candidate of needsReview) {
          const row = document.querySelector(
            `[data-review-row="${CSS.escape(candidate.candidate_id)}"]`,
          );
          const decision = row?.dataset.decision;

          const value = {
            candidate_id: candidate.candidate_id,
            decision,
            note:
              decision === "approve"
                ? "Internal Console reviewer confirmed this customer information."
                : decision === "reject"
                  ? "Internal Console reviewer did not accept this customer information."
                  : "Internal Console reviewer corrected this customer information.",
          };

          if (decision === "edit") {
            try {
              value.edited_value = parseEditedFactValue(
                candidate.value,
                row.querySelector(".review-edit-panel textarea").value,
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
                note: "Internal Console customer information review completed.",
              }),
            },
          );

          if (
            result.review.status === "completed_persona_blocked"
          ) {
            showToast("已保存，仍需补充一些关键信息。");
          } else {
            showToast("客户信息已确认，接下来请确认完整档案。");
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
      "确认客户档案",
      `
        <main class="page page-form customer-review-page profile-review-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>
              ← 返回客户
            </a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "",
            "确认客户档案",
            "请整体检查这些信息，确认后会用于后续内容创作。",
          )}

          <div class="work-surface profile-document">
            ${customerProfileSections(facts)}
          </div>

          <div class="sticky-action profile-approval-bar">
            <p>确认后的客户信息将用于后续视频内容。</p>
            <button
              id="approve-business-persona"
              class="btn btn-primary"
              type="button"
            >
              确认客户档案
            </button>
          </div>
        </main>`,
    );

    bindCommonActions();

    document
      .querySelector("#approve-business-persona")
      .addEventListener("click", async () => {
        const decision = await openModal({
          title: "确认客户档案？",
          description: "请确认你已经整体检查客户信息。确认后，这些信息会用于后续内容创作。",
          confirmLabel: "确认客户档案",
        });
        if (!decision.confirmed) return;

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
                note: "Internal Console reviewer confirmed the complete customer profile.",
              }),
            },
          );

          showToast("客户档案已确认");
          renderCustomerDetail(detail.business_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "确认客户档案";
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
        "更新客户资料",
        `
            <main class="page page-form profile-mutation-page">
            ${pageHeading(
                "",
                "更新客户资料",
                "修改后会重新分析，已确认的历史记录不会被静默覆盖。",
            )}

            <section class="work-surface profile-form-surface">
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

                <div class="profile-form-actions">
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
                ? "已提交更新后的客户资料"
                : "已重新提交客户资料",
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
            "",
            detail.display_name,
            "上一次客户信息分析没有完成，已经录入的资料仍然保留。",
            )}

            <section class="panel needs-info-state">
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
    const facts = (detail.business_persona?.facts || []).filter(
      (fact) => fact.state === "known",
    );
    const speakers = detail.speakers || [];
    const approvedSpeakers = speakers.filter(
      (speaker) => speaker.status === "approved",
    );
    const pendingSpeaker = speakers.find(
      (speaker) => speaker.status !== "approved",
    );
    const tabs = [
      { id: "overview", label: "概览" },
      { id: "profile", label: "客户资料" },
      { id: "speakers", label: "出镜人" },
      { id: "content", label: "内容" },
    ];
    const requestedTab = decodeURIComponent(location.hash.slice(1));
    const activeTab = tabs.some((tab) => tab.id === requestedTab)
      ? requestedTab
      : "overview";
    const primaryAction = detail.creation_entry_ready
      ? `<a class="btn btn-primary" href="/create?business_id=${encodeURIComponent(detail.business_id)}" data-route>开始创作</a>`
      : !speakers.length
        ? `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>`
        : pendingSpeaker
          ? `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/${encodeURIComponent(pendingSpeaker.speaker_id)}" data-route>确认出镜人信息</a>`
          : `<a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>`;
    const speakerContent = speakers.length
      ? `<div class="speaker-list">${speakers
          .map((speaker) => speakerCard(speaker, detail.business_id))
          .join("")}</div>`
      : `
        <section class="state-panel compact-empty-state">
          <span class="empty-icon" aria-hidden="true">＋</span>
          <h2>还没有出镜人</h2>
          <p>添加出镜人后，可以确认这个人的身份、经历和表达范围。</p>
          <a class="btn btn-primary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>
        </section>`;
    const tabContent = {
      overview: `
        ${ProfileSummary([
          {
            label: "客户资料",
            value: "已确认",
            note: `${facts.length} 项有效信息`,
          },
          {
            label: "出镜人",
            value: `${speakers.length} 位`,
            note: `${approvedSpeakers.length} 位已确认`,
          },
          {
            label: "创作状态",
            value: detail.creation_entry_ready ? "可以开始" : "尚未就绪",
            note: detail.creation_entry_ready
              ? "选择出镜人后进入创作"
              : "需要至少一位已确认出镜人",
          },
        ])}
        <section class="profile-next-action">
          <div>
            <span>下一步</span>
            <h2>${
              detail.creation_entry_ready
                ? "开始准备视频内容"
                : !speakers.length
                  ? "添加第一位出镜人"
                  : "完成出镜人信息确认"
            }</h2>
            <p>系统只会在客户和出镜人信息满足条件后开放创作。</p>
          </div>
        </section>`,
      profile: `<div class="work-surface profile-document">${customerProfileSections(facts)}</div>`,
      speakers: `
        <section class="profile-tab-section">
          <div class="section-head">
            <div><h2>出镜人</h2><p>管理谁可以以什么身份进行第一人称表达。</p></div>
            ${speakers.length ? `<a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/speakers/new" data-route>添加出镜人</a>` : ""}
          </div>
          ${speakerContent}
        </section>`,
      content: `
        <section class="profile-tab-section content-entry-list">
          <a class="content-entry-row" href="/customers/${encodeURIComponent(detail.business_id)}/content" data-route>
            <span><strong>内容管理</strong><small>查看客户的内容计划和交付进度</small></span><span class="case-chevron" aria-hidden="true">›</span>
          </a>
          <a class="content-entry-row ${detail.creation_entry_ready ? "" : "disabled"}" href="${detail.creation_entry_ready ? `/create?business_id=${encodeURIComponent(detail.business_id)}` : "#overview"}" ${detail.creation_entry_ready ? "data-route" : "data-profile-tab=\"overview\""}>
            <span><strong>开始创作</strong><small>${detail.creation_entry_ready ? "选择出镜人和创作模式" : "完成出镜人确认后开放"}</small></span><span class="case-chevron" aria-hidden="true">›</span>
          </a>
        </section>`,
    };

    app.innerHTML = shell(
      "客户详情",
      `
        <main class="page page-standard customer-detail-page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers" data-route>← 返回客户</a>
            ${customerStatusPill(detail.status)}
          </div>

          ${pageHeading(
            "",
            detail.display_name,
            detail.industry,
            `<div class="page-heading-actions">${primaryAction}<a class="btn btn-secondary" href="/customers/${encodeURIComponent(detail.business_id)}/edit" data-route>编辑资料</a></div>`,
          )}

          ${ProfileTabs(tabs, activeTab)}
          <div class="profile-tab-panel" data-active-profile-tab="${escapeHtml(activeTab)}">
            ${tabContent[activeTab]}
          </div>
        </main>`,
    );

    bindCommonActions();
    document.querySelectorAll("[data-profile-tab]").forEach((tab) => {
      tab.addEventListener("click", (event) => {
        event.preventDefault();
        const next = tab.dataset.profileTab;
        history.replaceState({}, "", `${location.pathname}#${next}`);
        renderApprovedCustomer(detail);
      });
    });
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
            "",
            "还缺少一些关键信息",
            `“${detail.display_name}”需要补充资料后才能继续。`,
          )}

          ${NeedsInfoState({
            description: "系统不会自动补写未知信息，请补充真实资料后重新分析。",
            items: blockers.map((field) => customerFieldLabel(field)),
            primaryHref: `/customers/${encodeURIComponent(detail.business_id)}/edit`,
            primaryLabel: "补充客户资料",
            secondaryHref: "/customers",
          })}
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
              <h2>正在准备客户信息</h2>
              <p>当前还没有可审核内容，请稍后再回来查看。</p>
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
