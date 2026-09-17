import {
  escapeHtml,
} from "./case-components.js";


export function createContentViews({
  app,
  api,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  renderLoadError,
}) {
  let options = null;
  let confirmationKey = null;

  function lockEntryForm(
    submitLabel =
      "Generation Request 已建立",
  ) {
    const entryForm =
      document.querySelector(
        "#content-entry-form",
      );

    if (!entryForm) return;

    entryForm.classList.add(
      "completed",
    );

    entryForm
      .querySelectorAll(
        "input, select, button",
      )
      .forEach((control) => {
        if (
          control.id ===
          "create-business"
        ) {
          return;
        }

        control.disabled = true;
      });

    const submitButton =
      entryForm.querySelector(
        "#check-content-capacity",
      );

    if (submitButton) {
      submitButton.textContent =
        submitLabel;
    }
  }


  function unlockEntryForm() {
    const entryForm =
      document.querySelector(
        "#content-entry-form",
      );

    if (!entryForm) return;

    entryForm.classList.remove(
      "completed",
    );

    entryForm
      .querySelectorAll(
        "input, select, button",
      )
      .forEach((control) => {
        control.disabled = false;
      });

    const submitButton =
      entryForm.querySelector(
        "#check-content-capacity",
      );

    if (submitButton) {
      submitButton.textContent =
        "检查内容容量";
    }
  }

  function renderRequestEstablished(
    host,
    {
      requestId,
      profile,
      confirmedQuantity,
      handoffReady,
    },
  ) {
    const profileLabel =
      profile === "news"
        ? "News"
        : "Mix";

    host.innerHTML = `
      <section class="card generation-request-result">
        <span class="generation-request-kicker">
          Generation Request 已建立
        </span>

        <h2>
          已确认生成
          ${Number(confirmedQuantity)}
          条
        </h2>

        <div class="generation-request-summary">
          <div class="generation-request-meta">
            <span>Request ID</span>
            <code>${escapeHtml(
              requestId,
            )}</code>
          </div>

          <div class="generation-request-meta">
            <span>Profile</span>
            <strong>${escapeHtml(
              profileLabel,
            )}</strong>
          </div>

          <div class="generation-request-meta">
            <span>确认数量</span>
            <strong>
              ${Number(confirmedQuantity)} 条
            </strong>
          </div>
        </div>

        <div class="source-planning-handoff">
          <strong>
            ${
              handoffReady === false
                ? "Source Planning Handoff 待建立"
                : "Source Planning Handoff 已准备"
            }
          </strong>

          <p>
            下一步将解析 Approved Pattern、
            Approved Case 与 Fingerprint，
            再建立 Generation Source Plan。
          </p>

          ${
            handoffReady === false
              ? `
                <button
                  id="recover-source-handoff"
                  class="btn btn-secondary btn-wide"
                  type="button"
                >
                  恢复 Source Planning Handoff
                </button>`
              : ""
          }
        </div>

        <div class="capacity-authority-note">
          <strong>
            当前仍未开始生成
          </strong>

          <span>
            没有调用远程模型，
            没有生成脚本，
            没有创建 Generation Batch，
            没有写入 Content Ledger。
          </span>
        </div>

        <p class="generation-request-footnote">
          Generation Request 是不可静默覆盖的
          canonical artifact。
        </p>
      </section>`;
  }

  async function restoreActiveRequest() {
    const businessSelect =
      document.querySelector(
        "#create-business",
      );

    if (!businessSelect) return;

    const host =
      document.querySelector(
        "#capacity-preview-result",
      );

    if (!host) return;

    let active = null;

    try {
      const response = await api(
        "/api/create/active-request" +
          `?business_id=${encodeURIComponent(
            businessSelect.value,
          )}`,
      );

      active =
        response.active_request;

    } catch (error) {
      host.innerHTML = `
        <section
          class="card capacity-result blocked"
        >
          <span class="capacity-kicker">
            暂时无法确认当前创作状态
          </span>

          <h2>
            为避免重复创建 Request，
            当前已停止继续操作
          </h2>

          <p>
            ${escapeHtml(
              error.detail?.next_action ||
                error.message,
            )}
          </p>
        </section>`;

      lockEntryForm(
        "暂时无法继续",
      );

      showToast(
        error.detail?.next_action ||
          error.message,
      );

      return;
    }

    if (!active) {
      unlockEntryForm();
      return;
    }

    const speakerSelect =
      document.querySelector(
        "#create-speaker",
      );

    if (
      speakerSelect
      && active.speaker_id
    ) {
      const found =
        Array.from(
          speakerSelect.options,
        ).some(
          (option) =>
            option.value ===
            active.speaker_id,
        );

      if (!found) {
        host.innerHTML = `
          <section
            class="card capacity-result blocked"
          >
            <span class="capacity-kicker">
              Active Request Authority 异常
            </span>

            <h2>
              当前 Request 的出镜人
              无法在客户 Authority 中恢复
            </h2>
          </section>`;

        lockEntryForm(
          "暂时无法继续",
        );

        return;
      }

      speakerSelect.value =
        active.speaker_id;
    }

    const profileRadio =
      document.querySelector(
        'input[name="create-profile"]' +
          `[value="${active.profile}"]`,
      );

    if (profileRadio) {
      profileRadio.checked = true;

      document
        .querySelectorAll(
          ".profile-choice",
        )
        .forEach((label) => {
          label.classList.toggle(
            "selected",
            label.querySelector(
              "input",
            ).checked,
          );
        });
    }

    const quantityInput =
      document.querySelector(
        "#create-quantity",
      );

    if (
      quantityInput
      && active.requested_quantity
    ) {
      quantityInput.value =
        String(
          active.requested_quantity
        );
    }

    renderRequestEstablished(
      host,
      {
        requestId:
          active.request_id,
        profile:
          active.profile,
        confirmedQuantity:
          active.confirmed_quantity,
        handoffReady:
          active.handoff_ready,
      },
    );

    lockEntryForm();

    if (
      active.handoff_ready
      === false
    ) {
      const recoverButton =
        document.querySelector(
          "#recover-source-handoff",
        );

      if (recoverButton) {
        recoverButton.addEventListener(
          "click",
          async () => {
            recoverButton.disabled =
              true;

            recoverButton.textContent =
              "正在恢复…";

            try {
              const response =
                await api(
                  "/api/create/confirm",
                  {
                    method: "POST",
                    body:
                      JSON.stringify({
                        business_id:
                          active.business_id,
                        speaker_id:
                          active.speaker_id,
                        profile:
                          active.profile,
                        requested_quantity:
                          Number(
                            active
                              .requested_quantity,
                          ),
                        confirmed_quantity:
                          Number(
                            active
                              .confirmed_quantity,
                          ),
                        idempotency_key:
                          newConfirmationKey(),
                      }),
                  },
                );

              const result =
                response.result;

              renderRequestEstablished(
                host,
                {
                  requestId:
                    result.request_id,
                  profile:
                    active.profile,
                  confirmedQuantity:
                    result
                      .confirmed_quantity,
                  handoffReady: true,
                },
              );

              lockEntryForm();

              showToast(
                "Source Planning Handoff 已恢复。",
              );

            } catch (error) {
              showToast(
                error.detail
                  ?.next_action ||
                  error.message,
              );

              if (
                recoverButton
                  .isConnected
              ) {
                recoverButton.disabled =
                  false;

                recoverButton.textContent =
                  (
                    "恢复 Source "
                    + "Planning Handoff"
                  );
              }
            }
          },
        );
      }
    }
  }

    function newConfirmationKey() {
    if (
        globalThis.crypto
        ?.randomUUID
    ) {
        return (
        globalThis.crypto
            .randomUUID()
        );
    }

    return [
        "console",
        Date.now(),
        Math.random()
        .toString(36)
        .slice(2, 14),
    ].join("_");
    }

  function selectedCustomer(
    businessId,
  ) {
    return (
      options?.customers || []
    ).find(
      (customer) =>
        customer.business_id ===
        businessId,
    );
  }

  function approvedSpeakers(
    customer,
  ) {
    return (
      customer?.speakers || []
    ).filter(
      (speaker) =>
        speaker.status ===
        "approved",
    );
  }

  function renderResult(
    preview,
  ) {
    const host =
      document.querySelector(
        "#capacity-preview-result",
      );

    if (!host) return;

    const capacity =
      preview.capacity || {};

    const recommendation =
      preview.recommendation || {};

    const profile =
      preview.selection?.profile ||
      "mix";

    const profileState =
      preview.profiles?.[profile] ||
      {};

    confirmationKey = null;

    if (
      recommendation.status ===
      "profile_unavailable"
    ) {
      host.innerHTML = `
        <section class="card capacity-result blocked">
          <span class="capacity-kicker">
            当前模式暂不可生产
          </span>

          <h2>
            ${profile === "news"
              ? "News 当前还没有达到生产就绪"
              : "当前 Production Profile 不可用"}
          </h2>

          <p>
            当前 Authority 状态：
            <strong>${escapeHtml(
              profileState.status ||
                "unknown",
            )}</strong>
          </p>

          <p>
            没有生成脚本，也没有创建 Generation Request。
          </p>

          <div class="capacity-next">
            建议切换到当前可用的 Mix 模式。
          </div>
        </section>`;

      return;
    }

    const requested =
      Number(
        recommendation
          .requested_quantity || 0,
      );

    const available =
      Number(
        capacity
          .high_quality_novel_capacity ||
          0,
      );

    const recommended =
      Number(
        recommendation
          .recommended_quantity || 0,
      );

    if (
      recommendation.status ===
      "capacity_exhausted"
    ) {
      host.innerHTML = `
        <section class="card capacity-result blocked">
          <span class="capacity-kicker">
            当前没有可继续消耗的新内容容量
          </span>

          <h2>
            高质量新内容容量为 0
          </h2>

          <p>
            系统不会为了凑数量重复已有语义，也不会生成 Padding。
          </p>

          <div class="capacity-next">
            下一步需要补充新的 Customer Truth、真实问题、服务边界或具体案例。
          </div>
        </section>`;

      return;
    }

    const limited =
      recommendation.status ===
      "capacity_limited";

    confirmationKey =
        newConfirmationKey();

    const gaps =
      capacity
        .content_gap_summary || [];

    host.innerHTML = `
      <section class="card capacity-result ${
        limited ? "limited" : "ready"
      }">
        <span class="capacity-kicker">
          ${limited
            ? "数量已按质量上限收缩"
            : "当前容量可以支持"}
        </span>

        <h2>
          ${limited
            ? `建议本轮生成 ${recommended} 条`
            : `可以生成 ${recommended} 条`}
        </h2>

        <div class="capacity-metrics">
          <div>
            <span>你希望生成</span>
            <strong>${requested}</strong>
          </div>

          <div>
            <span>当前高质量容量</span>
            <strong>${available}</strong>
          </div>

          <div>
            <span>建议本轮</span>
            <strong>${recommended}</strong>
          </div>
        </div>

        ${
          limited
            ? `
              <p class="capacity-explanation">
                如果继续补到 ${requested} 条，
                会开始出现事实重复、角度重复或信息增益不足。
                系统不会为了完成数量生成 Padding。
              </p>`
            : `
              <p class="capacity-explanation">
                当前 Approved Persona 与历史内容容量足以支撑这次请求。
                本次检查没有生成任何脚本。
              </p>`
        }

        ${
          gaps.length
            ? `
              <div class="capacity-gap">
                <strong>如果希望继续扩充容量</strong>
                ${gaps
                  .map(
                    (gap) =>
                      `<p>${escapeHtml(
                        gap,
                      )}</p>`,
                  )
                  .join("")}
              </div>`
            : ""
        }

        <div class="capacity-authority-note">
          <strong>
            Content Capacity ≠ Media Rights
          </strong>
          <span>
            当前只确认脚本语义容量。
            肖像、视频和素材使用授权仍是独立 Authority。
          </span>
        </div>

        ${
          recommendation.can_continue
            ? `
              <button
                id="content-generation-next"
                class="btn btn-primary btn-wide"
                type="button"
              >
                下一步：确认生成 ${recommended} 条
              </button>

              <p class="field-hint capacity-temporary-note">
                点击后会建立 immutable Generation Request 与 Source Planning Handoff；
                仍不会调用模型或生成脚本。
              </p>`
            : ""
        }
      </section>`;

    const nextButton =
      document.querySelector(
        "#content-generation-next",
      );

    if (nextButton) {
        nextButton.addEventListener(
            "click",
            async () => {
            const key =
                confirmationKey ||
                newConfirmationKey();

            confirmationKey = key;

            nextButton.disabled = true;
            nextButton.textContent =
                "正在建立 Generation Request…";

            try {
                const response = await api(
                "/api/create/confirm",
                {
                    method: "POST",
                    body: JSON.stringify({
                    business_id:
                        preview.business
                        .business_id,
                    speaker_id:
                        preview.speaker
                        .speaker_id,
                    profile,
                    requested_quantity:
                        requested,
                    confirmed_quantity:
                        recommended,
                    idempotency_key:
                        key,
                    }),
                },
                );

                const result =
                response.result;

                renderRequestEstablished(
                host,
                {
                    requestId:
                    result.request_id,
                    profile,
                    confirmedQuantity:
                    result.confirmed_quantity,
                    handoffReady: true,
                },
                );

                showToast(
                result.recovered
                    ? "已恢复现有 Generation Request。"
                    : "Generation Request 已建立。",
                );

                lockEntryForm();
            } catch (error) {
                showToast(
                error.detail?.next_action ||
                    error.message,
                );

                if (
                nextButton.isConnected
                ) {
                nextButton.disabled = false;
                nextButton.textContent =
                    `下一步：确认生成 ${recommended} 条`;
                }
            }
            },
        );
        }
  }

  function renderForm(
    data,
  ) {
    options = data;

    const customers =
      (data.customers || [])
        .filter(
          (customer) =>
            customer.creation_ready,
        );

    if (!customers.length) {
      app.innerHTML = shell(
        "视频创作",
        `
          <main class="page">
            ${pageHeading(
              "创作",
              "开始一次视频创作",
              "需要先有 Approved Business Persona 和 Approved Speaker Persona。",
            )}

            <section class="card empty-state">
              <h2>还没有可用于创作的客户</h2>

              <p>
                先到“客户”完成客户档案和至少一个出镜人设的人工批准。
              </p>

              <a
                class="btn btn-primary"
                href="/customers"
                data-route
              >
                去客户与人设
              </a>
            </section>
          </main>`,
      );

      bindCommonActions();
      return;
    }

    const params =
      new URLSearchParams(
        window.location.search,
      );

    const requestedBusiness =
      params.get("business_id");

    const initialCustomer =
      customers.find(
        (customer) =>
          customer.business_id ===
          requestedBusiness,
      ) || customers[0];

    const speakers =
      approvedSpeakers(
        initialCustomer,
      );

    const requestedSpeaker =
      params.get("speaker_id");

    const initialSpeaker =
      speakers.find(
        (speaker) =>
          speaker.speaker_id ===
          requestedSpeaker,
      ) || speakers[0];

    app.innerHTML = shell(
      "视频创作",
      `
        <main class="page create-entry-page">
          ${pageHeading(
            "创作",
            "开始一次视频创作",
            "先确认客户、出镜人、创作模式和数量。系统会先检查高质量内容容量，不会直接生成。",
          )}

          <section class="card create-entry-card">
            <form
              id="content-entry-form"
              novalidate
            >
              <div class="field">
                <label for="create-business">
                  客户
                </label>

                <select
                  id="create-business"
                  required
                >
                  ${customers
                    .map(
                      (customer) => `
                        <option
                          value="${escapeHtml(
                            customer.business_id,
                          )}"
                          ${
                            customer.business_id ===
                            initialCustomer.business_id
                              ? "selected"
                              : ""
                          }
                        >
                          ${escapeHtml(
                            customer.display_name,
                          )}
                        </option>`,
                    )
                    .join("")}
                </select>
              </div>

              <div class="field">
                <label for="create-speaker">
                  出镜人
                </label>

                <select
                  id="create-speaker"
                  required
                >
                  ${speakers
                    .map(
                      (speaker) => `
                        <option
                          value="${escapeHtml(
                            speaker.speaker_id,
                          )}"
                          ${
                            speaker.speaker_id ===
                            initialSpeaker?.speaker_id
                              ? "selected"
                              : ""
                          }
                        >
                          ${escapeHtml(
                            speaker.display_name,
                          )} ·
                          ${escapeHtml(
                            speaker.public_role,
                          )}
                        </option>`,
                    )
                    .join("")}
                </select>
              </div>

              <div class="field">
                <label>
                  创作模式
                </label>

                <div class="profile-choice-grid">
                  <label class="profile-choice selected">
                    <input
                      type="radio"
                      name="create-profile"
                      value="mix"
                      checked
                    >

                    <strong>Mix</strong>
                    <span>
                      素材混剪 / 数字人口播混剪
                    </span>
                  </label>

                  <label class="profile-choice">
                    <input
                      type="radio"
                      name="create-profile"
                      value="news"
                    >

                    <strong>News</strong>
                    <span>
                      新闻体内容；最终可用性以 Authority 检查为准
                    </span>
                  </label>
                </div>
              </div>

              <div class="field">
                <label for="create-quantity">
                  希望生成多少条
                </label>

                <input
                  id="create-quantity"
                  type="number"
                  min="1"
                  max="20"
                  step="1"
                  value="5"
                  inputmode="numeric"
                  required
                >

                <span class="field-hint">
                  1–20 条。请求数量不是生成承诺；
                  系统会先检查当前高质量容量。
                </span>
              </div>

              <div
                id="content-entry-error"
                class="form-error"
                role="alert"
              ></div>

              <button
                id="check-content-capacity"
                class="btn btn-primary btn-wide"
                type="submit"
              >
                检查内容容量
              </button>
            </form>
          </section>

          <div id="capacity-preview-result"></div>

          <section class="card notice-card create-authority-card">
            <h2>先检查容量，再显式建立 Generation Request</h2>

            <p>
            “检查内容容量”保持完全只读。
            只有在容量结果出来后再次点击确认，
            才会建立 immutable Generation Request 和 Source Planning Handoff。
            </p>

            <p>
            这一阶段仍不调用远程模型、
            不生成脚本、不创建 Generation Batch、
            不写入 Content Ledger。
            </p>
          </section>
        </main>`,
    );

    bindCommonActions();

    const businessSelect =
      document.querySelector(
        "#create-business",
      );

    const speakerSelect =
      document.querySelector(
        "#create-speaker",
      );

    businessSelect.addEventListener(
      "change",
      async () => {
        unlockEntryForm();

        const customer =
          selectedCustomer(
            businessSelect.value,
          );

        const nextSpeakers =
          approvedSpeakers(
            customer,
          );

        speakerSelect.innerHTML =
          nextSpeakers
            .map(
              (speaker) => `
                <option
                  value="${escapeHtml(
                    speaker.speaker_id,
                  )}"
                >
                  ${escapeHtml(
                    speaker.display_name,
                  )} ·
                  ${escapeHtml(
                    speaker.public_role,
                  )}
                </option>`,
            )
            .join("");

        document.querySelector(
          "#capacity-preview-result",
        ).innerHTML = "";

        confirmationKey = null;

        lockEntryForm(
          "正在检查现有 Request…",
        );

        await restoreActiveRequest();
      },
    );

    speakerSelect.addEventListener(
      "change",
      () => {
        document.querySelector(
          "#capacity-preview-result",
        ).innerHTML = "";

        confirmationKey = null;
      },
    );

    document
      .querySelectorAll(
        ".profile-choice input",
      )
      .forEach((input) => {
        input.addEventListener(
          "change",
          () => {
            document
              .querySelectorAll(
                ".profile-choice",
              )
              .forEach(
                (label) => {
                  label.classList.toggle(
                    "selected",
                    label.querySelector(
                      "input",
                    ).checked,
                  );
                },
              );

            document.querySelector(
              "#capacity-preview-result",
            ).innerHTML = "";

            confirmationKey = null;
          },
        );
      });

    document
      .querySelector(
        "#create-quantity",
      )
      .addEventListener(
        "input",
        () => {
          document.querySelector(
            "#capacity-preview-result",
          ).innerHTML = "";

          confirmationKey = null;
        },
      );

    document
      .querySelector(
        "#content-entry-form",
      )
      .addEventListener(
        "submit",
        async (event) => {
          event.preventDefault();

          const errorBox =
            document.querySelector(
              "#content-entry-error",
            );

          errorBox.classList.remove(
            "visible",
          );

          const quantity =
            Number(
              document.querySelector(
                "#create-quantity",
              ).value,
            );

          if (
            !Number.isInteger(
              quantity,
            )
            || quantity < 1
            || quantity > 20
          ) {
            errorBox.textContent =
              "请输入 1–20 之间的整数。";

            errorBox.classList.add(
              "visible",
            );

            return;
          }

          const speakerId =
            speakerSelect.value;

          if (!speakerId) {
            errorBox.textContent =
              "请选择一个已批准的出镜人。";

            errorBox.classList.add(
              "visible",
            );

            return;
          }

          const profile =
            document.querySelector(
              'input[name="create-profile"]:checked',
            ).value;

          document.querySelector(
            "#capacity-preview-result",
          ).innerHTML = "";

          confirmationKey = null;

          const button =
            document.querySelector(
              "#check-content-capacity",
            );

          button.disabled = true;
          button.textContent =
            "正在检查…";

          try {
            const result = await api(
              "/api/create/capacity-preview",
              {
                method: "POST",
                body: JSON.stringify({
                  business_id:
                    businessSelect.value,
                  speaker_id:
                    speakerId,
                  profile,
                  quantity,
                }),
              },
            );

            renderResult(
              result.preview,
            );

            document
              .querySelector(
                "#capacity-preview-result",
              )
              ?.scrollIntoView({
                behavior: "smooth",
                block: "start",
              });
          } catch (error) {
            errorBox.textContent =
              error.detail?.next_action ||
              error.message;

            errorBox.classList.add(
              "visible",
            );
          } finally {
            button.disabled = false;
            button.textContent =
              "检查内容容量";
          }
        },
      );
  }

  async function renderCreate() {
    skeletonPage(
      "视频创作",
    );

    try {
      const data = await api(
        "/api/create/options",
      );

      renderForm(
        data,
      );

      lockEntryForm(
        "正在检查现有 Request…",
      );

      await restoreActiveRequest();
    } catch (error) {
      renderLoadError(
        "创作入口暂时无法读取",
        error,
      );
    }
  }

  return {
    renderCreate,
  };
}