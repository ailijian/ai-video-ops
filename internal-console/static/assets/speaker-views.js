import { escapeHtml } from "./case-components.js";

import {
  editableFactValue,
  parseEditedFactValue,
} from "./customer-components.js?v=productized-stage2-3";

import {
  speakerFieldLabel,
  speakerProgressPanel,
  speakerStatusPill,
  speakerTypeLabel,
} from "./speaker-components.js?v=productized-stage2-3";

import {
  bindDecisionControls,
  ProfileRow,
  ProfileSection,
  ReviewList,
} from "./profile-components.js?v=productized-stage2-3";

import { startTaskPolling } from "./task-progress.js";

const SPEAKER_PROFILE_GROUPS = [
  {
    title: "基本信息",
    fields: ["public_display_name", "public_role"],
  },
  {
    title: "可以表达",
    fields: ["speaker_role_facts", "first_person_allowed_topics"],
  },
  {
    title: "明确不能表达",
    fields: ["first_person_forbidden_claims"],
  },
  {
    title: "角色边界",
    fields: ["role_scope_constraints"],
  },
  {
    title: "暂未确认",
    fields: ["unknown_facts"],
  },
];

function speakerProfileSections(facts = []) {
  const values = new Map(
    facts
      .filter((fact) => fact.state === "known")
      .map((fact) => [fact.field, fact.value]),
  );
  const grouped = new Set(SPEAKER_PROFILE_GROUPS.flatMap((group) => group.fields));
  const sections = SPEAKER_PROFILE_GROUPS.map((group) =>
    ProfileSection({
      title: group.title,
      rows: group.fields.map((field) =>
        ProfileRow({
          label: speakerFieldLabel(field),
          value: values.get(field),
          labelFor: speakerFieldLabel,
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
            label: speakerFieldLabel(fact.field),
            value: fact.value,
            labelFor: speakerFieldLabel,
          }),
        ),
      }),
    );
  }
  if (!values.has("first_person_forbidden_claims")) {
    sections.push(`
      <section class="profile-section">
        <div class="profile-section-heading">
          <h2>明确不能表达</h2>
        </div>
        <dl class="profile-rows">
          <div class="profile-row">
            <dt>额外明确限制</dt>
            <dd>
              <p class="profile-value-text">未记录额外明确限制</p>
              <p class="field-hint">仍然受通用第一人称边界约束：只有已经确认属于这个人的经历、职责和允许主题，才能以第一人称表达。</p>
            </dd>
          </div>
        </dl>
      </section>`);
  }
  return sections.filter(Boolean).join("");
}

export function createSpeakerViews({
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
              <div class="progress-complete-actions">
                <p>出镜人信息已经整理好，可以开始确认。</p>
                <a class="btn btn-primary" href="/customers/${encodeURIComponent(businessId)}/speakers/${encodeURIComponent(speakerId)}" data-route>确认出镜人信息</a>
                <a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}#speakers" data-route>返回出镜人</a>
              </div>`,
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

      const customerProfileApproved =
        customer.business_persona?.approved === true;

      app.innerHTML = shell(
        "添加出镜人",
        `
          <main class="page page-form profile-mutation-page">
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
              "",
              "添加出镜人",
              customerProfileApproved
                ? `为“${customer.display_name}”整理一位出镜人的真实经历、职责和表达边界。`
                : `先保存“${customer.display_name}”的出镜人资料；客户档案确认后再继续分析。`,
            )}

              <section class="work-surface profile-form-surface" data-speaker-new-surface>
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
                      写入这个人的真实经历、职责和擅长表达的内容。
                    </span>
                  </div>

                  <div class="field">
                    <label for="speaker-forbidden">
                      额外明确限制（选填）
                    </label>

                    <textarea
                      id="speaker-forbidden"
                      rows="5"
                      placeholder="每行一条。例如：&#10;不得声称自己具备未提供的专业资质&#10;不得把未经确认的数据说成自己的经营结果"
                    ></textarea>

                    <span class="field-hint">
                      如资料中有明确的表达限制，可以在这里补充；没有可留空。
                    </span>
                  </div>

                  <div
                    id="speaker-form-error"
                    class="form-error"
                    role="alert"
                  ></div>

                  <div class="profile-form-actions">
                    <button
                      class="btn btn-primary btn-wide"
                      type="submit"
                    >
                      ${customerProfileApproved ? "分析出镜人信息" : "保存出镜人资料"}
                    </button>
                  </div>
                  <p class="governance-copy">确认出镜人档案，不会自动获得照片、视频或肖像素材使用权。</p>
                </form>
              </section>
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

            const surface = document.querySelector("[data-speaker-new-surface]");

            errorBox.classList.remove("visible");

            const forbiddenClaims =
              document
                .querySelector("#speaker-forbidden")
                .value
                .split(/\r?\n/)
                .map((item) => item.trim())
                .filter(Boolean);

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

              if (result.draft_saved) {
                showToast("出镜人资料已保存，客户档案确认后可以继续。");
                return navigate(
                  `/customers/${encodeURIComponent(businessId)}`,
                );
              }

              if (result.duplicate) {
                if (
                  result.existing_task &&
                  ["queued", "running"].includes(
                    result.existing_task.status,
                  )
                ) {
                  surface.innerHTML =
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

              surface.innerHTML =
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
                customerProfileApproved
                  ? "分析出镜人信息"
                  : "保存出镜人资料";
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
    bindDecisionControls({ submitSelector: buttonId });

    document
      .querySelector(buttonId)
      .addEventListener(
        "click",
        async () => {
          const decisions = [];

          for (const candidate of needsReview) {
            const row = document.querySelector(
              `[data-review-row="${CSS.escape(
                candidate.candidate_id,
              )}"]`,
            );

            const decision =
              row?.dataset.decision;

            const value = {
              candidate_id:
                candidate.candidate_id,
              decision,
              note:
                decision === "approve"
                  ? "Internal Console reviewer confirmed this speaker information."
                  : decision === "reject"
                    ? "Internal Console reviewer did not accept this speaker information."
                    : "Internal Console reviewer corrected this speaker information.",
            };

            if (decision === "edit") {
              try {
                value.edited_value =
                  parseEditedFactValue(
                    candidate.value,
                    row.querySelector(
                      ".review-edit-panel textarea",
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
        <details class="known-facts-disclosure">
          <summary>已经明确的信息 <span>${known.length} 项</span></summary>
          <dl class="profile-rows">
            ${known
              .map((item) =>
                ProfileRow({
                  label: speakerFieldLabel(item.field),
                  value: item.value,
                  labelFor: speakerFieldLabel,
                }),
              )
              .join("")}
          </dl>
        </details>`
      : "";

    const isSupplement =
      detail.latest_intake_type === "gap_supplement";
    const reviewTitle = isSupplement
      ? "确认刚补充的信息"
      : "确认出镜人信息";

    app.innerHTML = shell(
      reviewTitle,
      `
        <main class="page page-form customer-review-page profile-review-page">
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
            "",
            reviewTitle,
            isSupplement
              ? "这里只审核本轮新增事实，之前已经确认的信息不会要求再次审核。"
              : `请检查“${detail.display_name}”本人可以承担的职责、经历和表达范围。`,
          )}

          ${knownHtml}

          <section class="work-surface review-surface">
            <div class="review-surface-heading">
              <h2>需要你确认</h2>
              <p>逐项选择不采用、修改或确认。</p>
            </div>
            ${ReviewList({
              items: needsReview,
              labelFor: speakerFieldLabel,
              namespace: "speaker",
              editableValueFor: editableFactValue,
            })}
          </section>

          <div class="sticky-action review-submit-bar">
            <span data-review-progress>已确认 0 / ${needsReview.length}</span>
            <button
              id="submit-speaker-fact-review"
              class="btn btn-primary"
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
                  note: "Internal Console speaker information review completed.",
                }),
              },
            );

            if (
              result.review.status ===
              "completed_persona_blocked"
            ) {
              showToast(
                "已保存，仍需补充一些关键信息。",
              );
            } else {
              showToast(
                "出镜人信息已确认，接下来请确认完整档案。",
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
      "确认出镜人档案",
      `
        <main class="page page-form customer-review-page profile-review-page">
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
            "",
            "确认出镜人档案",
            "整体检查这个人的身份、经历与表达边界。",
          )}

          <div class="work-surface profile-document">
            ${speakerProfileSections(facts)}
          </div>

          <div class="sticky-action profile-approval-bar">
            <p>确认档案不会建立照片、视频或肖像素材使用权。</p>
            <button
              id="approve-speaker-persona"
              class="btn btn-primary"
              type="button"
            >
              确认出镜人档案
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
          const decision = await openModal({
            title: "确认出镜人档案？",
            description: "请确认你已经整体检查这个人的身份、经历和表达边界。确认不会建立照片、视频或肖像素材使用权。",
            confirmLabel: "确认出镜人档案",
          });
          if (!decision.confirmed) return;

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
                  note: "Internal Console reviewer confirmed the complete speaker profile.",
                }),
              },
            );

            showToast(
              "出镜人档案已确认",
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
              "确认出镜人档案";
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
        <main class="page page-form approved-speaker-page">
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
            "",
            detail.display_name,
            detail.public_role,
          )}

          <div class="work-surface profile-document">
            ${speakerProfileSections(facts)}
          </div>

          <p class="governance-copy speaker-rights-note">确认出镜人档案不代表已经获得这个人的照片、视频或肖像素材使用权。</p>
        </main>`,
    );

    bindCommonActions();
  }

  function renderNeedsMoreInfo(
    detail,
    businessId,
  ) {
    const gaps = detail.readiness_gaps || [];
    const blockers = gaps.map((item) => item.title);
    const primary = detail.can_recheck_existing
      ? `<button id="recheck-speaker-readiness" class="btn btn-primary" type="button">重新检查现有资料</button>`
      : `<a class="btn btn-primary" href="/customers/${encodeURIComponent(
          businessId,
        )}/speakers/${encodeURIComponent(
          detail.speaker_id,
        )}/supplement" data-route>补充出镜人资料</a>`;

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
            "",
            "还缺少一些关键信息",
            `“${detail.display_name}”需要补充真实资料后才能继续。`,
          )}

          <section class="panel needs-info-state">
            <span class="state-icon" aria-hidden="true">!</span>
            <div>
              <h2>还缺少一些关键信息</h2>
              <p>${detail.can_recheck_existing
                ? "现有人工确认资料可以按新规则直接重新检查，不会调用模型。"
                : "系统不会自动补写未知信息，只需补充当前缺失的内容。"}</p>
              ${blockers.length ? `<ul>${blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
              <div class="needs-info-actions">
                ${primary}
                <a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}" data-route>稍后处理</a>
              </div>
            </div>
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

    document
      .querySelector("#recheck-speaker-readiness")
      ?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = "正在检查…";
        try {
          const result = await api(
            `/api/customers/${encodeURIComponent(businessId)}/speakers/${encodeURIComponent(detail.speaker_id)}/readiness/recheck`,
            { method: "POST" },
          );
          if (
            result.recheck.status ===
            "completed_persona_review_required"
          ) {
            showToast("现有资料已满足要求，请确认出镜人档案。");
          } else {
            showToast("已重新检查，请继续补充仍缺少的信息。");
          }
          renderSpeakerDetail(businessId, detail.speaker_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "重新检查现有资料";
        }
      });
  }

  async function renderSpeakerSupplement(
    businessId,
    speakerId,
  ) {
    stopTaskPolling();
    skeletonPage("补充出镜人资料");
    try {
      const detail = await api(
        `/api/customers/${encodeURIComponent(businessId)}/speakers/${encodeURIComponent(speakerId)}`,
      );
      const gaps = detail.readiness_gaps || [];
      app.innerHTML = shell(
        "补充出镜人资料",
        `
          <main class="page page-form profile-mutation-page">
            <div class="case-review-heading">
              <a class="back-link" href="/customers/${encodeURIComponent(businessId)}/speakers/${encodeURIComponent(speakerId)}" data-route>← 返回出镜人</a>
              ${speakerStatusPill(detail.status)}
            </div>
            ${pageHeading(
              "",
              "补充出镜人资料",
              "只补当前缺少的信息；之前已经确认的事实和人工决定会完整保留。",
            )}
            <section class="work-surface profile-form-surface">
              <form id="speaker-supplement-form" novalidate>
                ${gaps
                  .map(
                    (gap) => `
                      <div class="field">
                        <label for="speaker-gap-${escapeHtml(gap.field)}">${escapeHtml(gap.title)}</label>
                        <textarea id="speaker-gap-${escapeHtml(gap.field)}" data-gap-field="${escapeHtml(gap.field)}" rows="5" maxlength="12000" required></textarea>
                        <span class="field-hint">${escapeHtml(gap.question)}</span>
                      </div>`,
                  )
                  .join("")}
                <div id="speaker-supplement-error" class="form-error" role="alert"></div>
                <div class="profile-form-actions">
                  <button class="btn btn-primary btn-wide" type="submit">提交补充资料</button>
                  <a class="btn btn-secondary" href="/customers/${encodeURIComponent(businessId)}" data-route>稍后处理</a>
                </div>
              </form>
            </section>
          </main>`,
      );
      bindCommonActions();
      document
        .querySelector("#speaker-supplement-form")
        .addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.currentTarget.querySelector("button[type=submit]");
          const answers = Object.fromEntries(
            [...event.currentTarget.querySelectorAll("[data-gap-field]")].map(
              (input) => [input.dataset.gapField, input.value.trim()],
            ),
          );
          if (Object.values(answers).some((value) => !value)) {
            showToast("请完成当前列出的补充项。");
            return;
          }
          button.disabled = true;
          button.textContent = "正在提交…";
          try {
            const result = await api(
              `/api/customers/${encodeURIComponent(businessId)}/speakers/${encodeURIComponent(speakerId)}/gaps/supplement`,
              {
                method: "POST",
                body: JSON.stringify({ answers }),
              },
            );
            const task = result.task || result.existing_task;
            app.innerHTML = shell(
              "出镜人信息分析",
              `<main class="page">${pageHeading(
                "出镜人",
                detail.display_name,
                "正在整理本轮新增资料，旧资料不会重新分析。",
              )}<div data-speaker-progress></div></main>`,
            );
            bindCommonActions();
            bindSpeakerProgress(task, businessId, speakerId);
          } catch (error) {
            showToast(error.detail?.next_action || error.message);
            button.disabled = false;
            button.textContent = "提交补充资料";
          }
        });
    } catch (error) {
      renderLoadError("补充资料暂时无法打开", error);
    }
  }

  function renderSavedSpeakerDraft(detail, businessId) {
    const ready = detail.status === "analysis_pending";
    app.innerHTML = shell(
      "出镜人详情",
      `
        <main class="page">
          <div class="case-review-heading">
            <a class="back-link" href="/customers/${encodeURIComponent(businessId)}#speakers" data-route>← 返回客户详情</a>
            ${speakerStatusPill(detail.status)}
          </div>
          ${pageHeading(
            "出镜人资料已保存",
            detail.display_name,
            `${detail.public_role} · ${ready ? "可以继续确认" : "待客户档案确认"}`,
          )}
          <section class="panel needs-info-state">
            <span class="state-icon" aria-hidden="true">✓</span>
            <div>
              <h2>${ready ? "继续确认出镜人" : "待客户档案确认"}</h2>
              <p>${
                ready
                  ? "客户档案已经确认，现在可以用已保存的资料继续分析，不需要重新填写。"
                  : "姓名、身份、已有资料和表达边界已经保存。客户档案确认后才能分析和批准出镜人档案。"
              }</p>
              <div class="needs-info-actions">
                ${ready ? '<button id="analyze-saved-speaker" class="btn btn-primary" type="button">继续确认出镜人</button>' : `<a class="btn btn-primary" href="/customers/${encodeURIComponent(businessId)}" data-route>继续客户档案</a>`}
                <a class="btn btn-secondary" href="/customers" data-route>稍后处理</a>
              </div>
            </div>
          </section>
        </main>`,
    );
    bindCommonActions();
    document.querySelector("#analyze-saved-speaker")?.addEventListener(
      "click",
      async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = "正在开始…";
        try {
          const result = await api(
            `/api/customers/${encodeURIComponent(businessId)}/speakers/${encodeURIComponent(detail.speaker_id)}/analyze`,
            { method: "POST" },
          );
          const task = result.task || result.existing_task;
          app.innerHTML = shell(
            "出镜人信息分析",
            `<main class="page">${pageHeading(
              "出镜人",
              detail.display_name,
              "正在用已保存的资料整理待确认信息。",
            )}<div data-speaker-progress></div></main>`,
          );
          bindCommonActions();
          bindSpeakerProgress(task, businessId, detail.speaker_id);
        } catch (error) {
          showToast(error.detail?.next_action || error.message);
          button.disabled = false;
          button.textContent = "继续确认出镜人";
        }
      },
    );
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
                "正在把已有资料整理成待确认的出镜人信息。",
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

      if (["pending_customer_profile", "analysis_pending"].includes(detail.status)) {
        return renderSavedSpeakerDraft(detail, businessId);
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
              <h2>正在准备出镜人信息</h2>
              <p>当前还没有可审核内容，请稍后再回来查看。</p>
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
            "正在从已有资料中整理待确认的出镜人信息。",
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
    renderSpeakerSupplement,
    renderSpeakerDetail,
    renderSpeakerTaskDetail,
    stopTaskPolling,
  };
}
