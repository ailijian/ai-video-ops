import { createApiClient } from "./api-client.js";
import { createCaseViews } from "./case-views.js?v=production-acceptance-1";
import { createCustomerViews } from "./customer-views.js";
import { progressPanel } from "./case-components.js?v=production-acceptance-1";
import { startTaskPolling } from "./task-progress.js";
import { customerProgressPanel } from "./customer-components.js";
import { matchWorkflowRoute } from "./routes.js";
import {
  createSpeakerViews,
} from "./speaker-views.js";

import {
  speakerProgressPanel,
} from "./speaker-components.js";

import {
  createContentViews,
} from "./content-views.js?v=branding-layout-2";

import {
  createContentOperationsViews,
} from "./content-operations-views.js?v=authority-resolver-1";

const app = document.querySelector("#app");
const toastRegion = document.querySelector("#toast-region");

const state = {
  user: null,
  csrfToken: null,
};

const icons = {
  home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3.5 10.5 12 3l8.5 7.5"/><path d="M5.5 9.5v10h13v-10M9.5 19.5v-6h5v6"/></svg>`,
  cases: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14.5" rx="2.5"/><path d="m9.5 9 5.5 3-5.5 3V9Z"/></svg>`,
  create: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3.5v17M3.5 12h17"/></svg>`,
  customers: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.5-3.8 2.2-5.8 5.5-5.8s5 2 5.5 5.8"/><path d="M15.5 6.2a3 3 0 0 1 0 5.7M16.5 14c2.4.5 3.6 2.2 4 5"/></svg>`,
  tasks: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="4" y="3.5" width="16" height="17" rx="2.5"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>`,
  user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5.2 20c.6-4 2.8-6.2 6.8-6.2s6.2 2.2 6.8 6.2"/></svg>`,
  logout: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M10 4H5.5A1.5 1.5 0 0 0 4 5.5v13A1.5 1.5 0 0 0 5.5 20H10M14.5 8l4 4-4 4M8 12h10"/></svg>`,
  arrow: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 4v16M4 12h16"/></svg>`,
  link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m9.5 14.5 5-5"/><path d="M7.2 16.8 5.5 18.5a3.5 3.5 0 0 1-5-5l3.2-3.2a3.5 3.5 0 0 1 5 0M16.8 7.2l1.7-1.7a3.5 3.5 0 0 1 5 5l-3.2 3.2a3.5 3.5 0 0 1-5 0" transform="translate(-2)"/></svg>`,
  inbox: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7.5 7 3h10l3 4.5v11.2a1.8 1.8 0 0 1-1.8 1.8H5.8A1.8 1.8 0 0 1 4 18.7V7.5Z"/><path d="M4 13h4l1.5 2h5l1.5-2h4"/></svg>`,
  alert: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3.5 21 20H3L12 3.5Z"/><path d="M12 9v5M12 17.5h.01"/></svg>`,
};

const navItems = [
  { path: "/workbench", label: "工作台", icon: "home" },
  { path: "/cases", label: "案例库", mobileLabel: "案例", icon: "cases" },
  { path: "/create", label: "视频创作", mobileLabel: "创作", icon: "create", primary: true },
  { path: "/customers", label: "客户与人设", mobileLabel: "客户", icon: "customers" },
  { path: "/tasks", label: "任务记录", mobileLabel: "任务", icon: "tasks" },
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function brandMark() {
  return `<img class="brand-mark" src="/assets/brand/logo.png?v=transparent-1" alt="">`;
}

function showToast(message) {
  toastRegion.innerHTML = `<div class="toast">${escapeHtml(message)}</div>`;
  window.setTimeout(() => { toastRegion.innerHTML = ""; }, 3000);
}

function maskPhone(phone) {
  const value = String(phone || "");
  if (/^\d{11}$/.test(value)) return `${value.slice(0, 3)}****${value.slice(-4)}`;
  return value;
}

const api = createApiClient({
  state,
  onUnauthorized: () => {
    state.user = null;
    state.csrfToken = null;
    navigate("/login", true);
  },
  onPasswordRequired: () => navigate("/change-password", true),
});

function navigate(path, replace = false) {
  if (replace) history.replaceState({}, "", path);
  else history.pushState({}, "", path);
  window.scrollTo({ top: 0, behavior: "instant" });
  renderRoute();
}

function routeIsActive(path, target) {
  if (target === "/workbench") return path === target;
  return path === target || path.startsWith(`${target}/`);
}

function shell(title, body) {
  const path = location.pathname;
  const sideLinks = navItems.map((item) => `
    <a class="nav-link ${item.primary ? "create-link" : ""} ${routeIsActive(path, item.path) ? "active" : ""}"
      href="${item.path}" data-route>
      ${icons[item.icon]}<span>${item.label}</span>
    </a>`).join("");
  const bottomLinks = navItems.map((item) => item.primary ? `
    <a class="bottom-link create-bottom ${routeIsActive(path, item.path) ? "active" : ""}" href="${item.path}" data-route>
      <span class="create-orb">${icons.create}</span><span>${item.mobileLabel}</span>
    </a>` : `
    <a class="bottom-link ${routeIsActive(path, item.path) ? "active" : ""}" href="${item.path}" data-route>
      ${icons[item.icon]}<span>${item.mobileLabel || item.label}</span>
    </a>`).join("");
  return `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="sidebar-brand">${brandMark()}<div><strong>鲸汤AI视频</strong><small>代运营工作台</small></div></div>
        <nav class="side-nav" aria-label="主导航">${sideLinks}</nav>
        <div class="sidebar-footer">内部生产工作台 · V1</div>
      </aside>
      <div class="main-column">
        <header class="topbar">
          <div class="mobile-brand">${brandMark()}<span class="topbar-title">${escapeHtml(title)}</span></div>
          <span class="topbar-title desktop-only">${escapeHtml(title)}</span>
          <div class="account-actions">
            <span class="account-phone">${escapeHtml(maskPhone(state.user?.phone))}</span>
            <button class="icon-button" type="button" data-action="change-password" aria-label="修改密码" title="修改密码">${icons.user}</button>
            <button class="icon-button desktop-only" type="button" data-action="logout" aria-label="退出登录" title="退出登录">${icons.logout}</button>
          </div>
        </header>
        ${body}
      </div>
      <nav class="bottom-nav" aria-label="底部导航">${bottomLinks}</nav>
    </div>`;
}

function bindCommonActions() {
  document.querySelectorAll("[data-route]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(link.getAttribute("href"));
    });
  });
  document.querySelectorAll('[data-action="change-password"]').forEach((button) => {
    button.addEventListener("click", () => navigate("/change-password"));
  });
  document.querySelectorAll('[data-action="logout"]').forEach((button) => {
    button.addEventListener("click", logout);
  });
}

function pageHeading(eyebrow, title, description, action = "") {
  return `<div class="page-heading"><p class="eyebrow">${escapeHtml(eyebrow)}</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p>${action}</div>`;
}

function skeletonPage(title) {
  app.innerHTML = shell(title, `<main class="page"><div class="skeleton skeleton-card"></div><div class="section skeleton skeleton-card"></div></main>`);
  bindCommonActions();
}

function statusPill(status) {
  const labels = {
    approved: ["已入库", "pill-approved"],
    awaiting_review: ["待审核", "pill-review"],
    analyzing: ["分析中", "pill-review"],
    queued: ["排队中", "pill-review"],
    running: ["进行中", "pill-review"],
    completed: ["已完成", "pill-approved"],
    failed: ["失败", "pill-failed"],
    archived: ["已归档", "pill-archived"],
  };
  const [label, className] = labels[status] || [status, "pill-archived"];
  return `<span class="pill ${className}">${escapeHtml(label)}</span>`;
}

function humanTaskType(value) {
  return {
    case_analysis: "案例分析",
    customer_analysis: "客户信息分析",
    speaker_analysis: "出镜人信息分析",
    content_generation: "视频创作",
    excel_export: "Excel 导出",
  }[value] || value;
}

function displayNextAction(value) {
  return {
    WAIT_FOR_OPERATOR_RELEASE: "等待你解除暂停",
    SEND_CUSTOMER_CAPTURE_PACK: "发送客户补拍清单",
    REVIEW_PERSONA: "审核客户档案",
    RUN_REPLENISHMENT: "补充客户信息",
  }[value] || value || "暂无动作";
}

function humanApprovalStatus(value) {
  return {
    APPROVED: "已确认",
    REVIEW_REQUIRED: "待确认",
    NOT_AVAILABLE: "暂无",
  }[value] || "待确认";
}

function renderLogin() {
  app.innerHTML = `
    <main class="auth-page">
      <div class="auth-wrap">
        <div class="auth-brand">${brandMark()}<div><strong>鲸汤AI视频代运营工作台</strong><span>内部运营专用</span></div></div>
        <section class="auth-card">
          <h1>欢迎回来</h1>
          <p>登录后继续处理案例、客户与视频创作任务。</p>
          <form id="login-form" novalidate>
            <div class="field"><label for="phone">手机号</label><input id="phone" name="phone" inputmode="tel" autocomplete="username" placeholder="请输入内部账号手机号" required></div>
            <div class="field"><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" placeholder="请输入密码" required></div>
            <div id="login-error" class="form-error" role="alert"></div>
            <button class="btn btn-primary btn-wide" type="submit">登录</button>
          </form>
        </section>
      </div>
    </main>`;
  document.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    const errorBox = document.querySelector("#login-error");
    button.disabled = true;
    button.textContent = "正在登录…";
    errorBox.classList.remove("visible");
    try {
      const payload = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          phone: document.querySelector("#phone").value,
          password: document.querySelector("#password").value,
        }),
        skipAuthRedirect: true,
      });
      state.user = payload.user;
      state.csrfToken = payload.csrf_token;
      navigate(payload.user.must_change_password ? "/change-password" : "/workbench", true);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.add("visible");
      button.disabled = false;
      button.textContent = "登录";
    }
  });
}

function renderChangePassword() {
  const firstLogin = state.user?.must_change_password;
  app.innerHTML = `
    <main class="auth-page">
      <div class="auth-wrap">
        <div class="auth-brand">${brandMark()}<div><strong>鲸汤AI视频代运营工作台</strong><span>账号安全</span></div></div>
        <section class="auth-card">
          <h1>${firstLogin ? "首次登录" : "修改密码"}</h1>
          <p>${firstLogin ? "请先设置一个新密码，再进入工作台。" : "修改后，其他已登录设备会自动退出。"}</p>
          <form id="password-form" novalidate>
            <div class="field"><label for="current-password">当前密码</label><input id="current-password" type="password" autocomplete="current-password" required></div>
            <div class="field"><label for="new-password">新密码</label><input id="new-password" type="password" autocomplete="new-password" required><span class="field-hint">至少 8 个字符，不能继续使用初始密码。</span></div>
            <div class="field"><label for="confirm-password">确认新密码</label><input id="confirm-password" type="password" autocomplete="new-password" required></div>
            <div id="password-error" class="form-error" role="alert"></div>
            <button class="btn btn-primary btn-wide" type="submit">${firstLogin ? "保存并进入工作台" : "保存新密码"}</button>
            ${firstLogin ? "" : '<button class="btn btn-quiet btn-wide" type="button" data-cancel>返回工作台</button>'}
          </form>
        </section>
      </div>
    </main>`;
  document.querySelector("[data-cancel]")?.addEventListener("click", () => navigate("/workbench"));
  document.querySelector("#password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    const errorBox = document.querySelector("#password-error");
    button.disabled = true;
    button.textContent = "正在保存…";
    errorBox.classList.remove("visible");
    try {
      const payload = await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: document.querySelector("#current-password").value,
          new_password: document.querySelector("#new-password").value,
          confirm_password: document.querySelector("#confirm-password").value,
        }),
      });
      state.user = payload.user;
      state.csrfToken = payload.csrf_token;
      showToast("密码已更新");
      navigate("/workbench", true);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.add("visible");
      button.disabled = false;
      button.textContent = firstLogin ? "保存并进入工作台" : "保存新密码";
    }
  });
}

async function renderWorkbench() {
  skeletonPage("工作台");
  try {
    const data = await api("/api/workbench");
    const status = data.status || null;
    const hasCustomers = data.has_customers === true;
    const customers = data.customers || [];
    const attentionTotal = data.attention.case_reviews + data.attention.persona_reviews + data.attention.content_reviews;
    const attentionCards = [
      [data.attention.case_reviews, "案例等待审核", "/cases", "查看案例"],
      [data.attention.persona_reviews, "客户信息等待审核", "/customers", "查看客户"],
      [data.attention.content_reviews, "内容批次等待审核", "/tasks", "查看任务"],
      [data.attention.running_tasks, "任务正在执行", "/tasks", "查看进度"],
    ].map(([number, label, path, action]) => `
      <article class="card attention-card"><div><div class="number">${number}</div><div class="label">${label}</div></div>
        <a class="inline-link" href="${path}" data-route><span>${action}</span>${icons.arrow}</a></article>`).join("");
    const contentCreation = data.capabilities?.content_creation || {};
    const creationCard = contentCreation.available
      ? `<a class="card quick-card" href="/create" data-route><span class="quick-icon">${icons.create}</span><div><strong>开始视频创作</strong><span>选择客户与出镜人</span></div></a>`
      : `<article class="card quick-card quick-card-disabled" aria-disabled="true"><span class="quick-icon">${icons.create}</span><div><strong>开始视频创作</strong><span>需要已批准的客户与出镜人</span></div></article>`;
    let operationalCard;
    let customerSection;
    let headingDescription;

    if (status) {
      const businessId = status.business.business_id;
      const selectedCustomer = customers.find(
        (customer) => customer.business_id === businessId,
      );
      const name = selectedCustomer?.display_name || businessId;
      const hold = status.operational_hold;
      const content = status.content;
      const truth = status.customer_truth;
      operationalCard = `
        <section class="card hold-card">
          <div class="status-kicker"><span class="status-dot"></span>${hold.active ? "已暂停" : "可以继续"}</div>
          <h2>${hold.active ? "客户联系已暂停" : "客户运营可以继续"}</h2>
          <p>${hold.active ? "你暂时决定不联系客户补拍素材。解除暂停前，这批补拍任务不会继续发送。" : "请按当前下一步继续处理。"}</p>
          <div class="hold-next">当前下一步<strong>${escapeHtml(displayNextAction(status.primary_next_action))}</strong></div>
        </section>`;
      customerSection = `
        <section class="section">
          <div class="section-head"><div><h2>当前客户</h2><p>查看当前可继续处理的工作</p></div></div>
          <article class="card customer-snapshot">
            <div class="snapshot-top"><div><h3>${escapeHtml(name)}</h3></div><span class="pill pill-approved">当前可用</span></div>
            <div class="snapshot-grid">
              <div class="metric"><span>客户档案</span><strong>${escapeHtml(humanApprovalStatus(truth.business_persona.status))}</strong></div>
              <div class="metric"><span>出镜人设</span><strong>${escapeHtml(humanApprovalStatus(truth.speaker_persona.status))}</strong></div>
              <div class="metric"><span>剩余内容空间</span><strong>${escapeHtml(content.remaining_high_quality_novel_capacity)} 条</strong></div>
              <div class="metric"><span>最近批次</span><strong>已有完成记录</strong></div>
            </div>
          </article>
        </section>`;
      headingDescription = attentionTotal ? `有 ${attentionTotal} 件事等待处理。` : "当前没有待审核事项，先查看运营状态。";
    } else if (!hasCustomers) {
      operationalCard = `
        <section class="card empty-state workbench-empty-state">
          <div class="empty-icon">${icons.customers}</div>
          <h2>还没有客户</h2>
          <p>从添加案例或建立第一个客户开始。</p>
        </section>`;
      customerSection = "";
      headingDescription = "还没有客户，从添加案例或建立第一个客户开始。";
    } else {
      const selectionError = data.customer_selection?.error;
      operationalCard = `
        <section class="card empty-state workbench-empty-state">
          <div class="empty-icon">${icons.customers}</div>
          <h2>尚未选择当前客户</h2>
          <p>${escapeHtml(selectionError?.message || `已有 ${customers.length} 个客户，请从客户列表选择。`)}</p>
          <a class="btn btn-secondary" href="/customers" data-route>查看客户</a>
        </section>`;
      customerSection = "";
      headingDescription = attentionTotal ? `有 ${attentionTotal} 件事等待处理。` : "请选择客户后查看对应运营状态。";
    }

    const body = `
      <main class="page">
        ${pageHeading("今日", "今天需要做什么", headingDescription)}
        <div class="dashboard-grid">
          ${operationalCard}
          <section class="attention-grid" aria-label="待处理事项">${attentionCards}</section>
        </div>

        <section class="section">
          <div class="section-head"><div><h2>快捷开始</h2><p>从常用生产入口继续</p></div></div>
          <div class="quick-grid">
            <a class="card quick-card" href="/cases/new" data-route><span class="quick-icon">${icons.link}</span><div><strong>添加案例</strong><span>粘贴真实视频链接</span></div></a>
            <a class="card quick-card" href="/customers/new" data-route><span class="quick-icon">${icons.customers}</span><div><strong>新建客户</strong><span>整理已有客户资料</span></div></a>
            ${creationCard}
          </div>
        </section>

        ${customerSection}
      </main>`;
    app.innerHTML = shell("工作台", body);
    bindCommonActions();
  } catch (error) {
    renderLoadError("工作台暂时无法读取", error);
  }
}

async function renderTasks() {
  skeletonPage("任务记录");
  try {
    const data = await api("/api/tasks");
    const content = data.tasks.length ? `<div class="task-list">${data.tasks.map((task) => `
      <article class="task-list-item">${
    task.task_type === "customer_analysis"
      ? customerProgressPanel(task, {
          compact: true,
        })
      : task.task_type === "speaker_analysis"
        ? speakerProgressPanel(task, {
            compact: true,
          })
        : progressPanel(task, {
            compact: true,
          })
}<a class="inline-link" href="/tasks/${encodeURIComponent(task.task_id)}" data-route><span>查看任务</span><span aria-hidden="true">›</span></a></article>`).join("")}</div>` : `
      <section class="card empty-state"><div class="empty-icon">${icons.tasks}</div><h2>暂时没有任务</h2><p>案例分析、客户信息分析、出镜人分析和视频创作都会出现在这里。</p><a class="btn btn-secondary" href="/cases/new" data-route>添加案例</a></section>`;
    app.innerHTML = shell("任务记录", `<main class="page">${pageHeading("任务", "任务记录", "这里显示执行进度；案例是否入库仍以人工审核结果为准。")}${content}</main>`);
    bindCommonActions();
  } catch (error) {
    renderLoadError("任务暂时无法读取", error);
  }
}

function renderPlaceholder(type) {
  const values = type === "customers" ? {
    title: "客户与人设",
    eyebrow: "客户",
    description: "客户资料与出镜人资料分别审核，待确认信息不会自动进入生产。",
    heading: "下一阶段接入客户审核",
    text: "本轮先完成案例工作流，客户资料整理与审核将在下一阶段接入。",
    action: "返回工作台",
  } : {
    title: "视频创作",
    eyebrow: "创作",
    description: "客户与出镜人 → 视频形式 → 数量 → 确认。",
    heading: "创作流程将在下一里程碑开放",
    text: "剩余内容空间不会因为切换视频形式而重置，也不会为了凑数量自动补齐。",
    action: "查看当前状态",
  };
  const body = `<main class="page">${pageHeading(values.eyebrow, values.title, values.description)}<section class="card notice-card"><h2>${values.heading}</h2><p>${values.text}</p><button class="btn btn-primary" type="button" data-back-workbench>${values.action}</button></section></main>`;
  app.innerHTML = shell(values.title, body);
  bindCommonActions();
  document.querySelector("[data-back-workbench]").addEventListener("click", () => navigate("/workbench"));
}

function renderLoadError(title, error) {
  const nextAction = error.detail?.next_action || "请稍后刷新页面重试。";
  const body = `<main class="page">${pageHeading("Error", title, error.message)}<section class="card notice-card"><h2>下一步</h2><p>${escapeHtml(nextAction)}</p><button class="btn btn-secondary" type="button" data-retry>重新尝试</button></section></main>`;
  app.innerHTML = shell(title, body);
  bindCommonActions();
  document.querySelector("[data-retry]").addEventListener("click", renderRoute);
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* local session still clears */ }
  state.user = null;
  state.csrfToken = null;
  navigate("/login", true);
}

const caseViews = createCaseViews({
  app,
  api,
  navigate,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  statusPill,
  showToast,
  renderLoadError,
});

const customerViews = createCustomerViews({
  app,
  api,
  navigate,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  renderLoadError,
});

const speakerViews = createSpeakerViews({
  app,
  api,
  navigate,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  renderLoadError,
});

const contentViews = createContentViews({
  app,
  api,
  shell,
  bindCommonActions,
  pageHeading,
  skeletonPage,
  showToast,
  renderLoadError,
});

const contentOperationsViews =
  createContentOperationsViews({
    app,
    api,
    shell,
    bindCommonActions,
    pageHeading,
    skeletonPage,
    renderLoadError,
  });

async function renderTaskDetail(taskId) {
  skeletonPage("任务进度");

  try {
    const payload = await api(
      `/api/tasks/${encodeURIComponent(taskId)}`,
    );

    if (
      payload.task.task_type ===
      "customer_analysis"
    ) {
      return customerViews.renderCustomerTaskDetail(
        payload.task,
      );
    }

    if (
      payload.task.task_type ===
      "speaker_analysis"
    ) {
      return speakerViews.renderSpeakerTaskDetail(
        payload.task,
      );
    }

    if (["content_generation", "excel_export"].includes(payload.task.task_type)) {
      const render = (task) => {
        app.innerHTML = shell(
          "任务进度",
          `<main class="page task-detail-page">${pageHeading(
            "后台任务",
            humanTaskType(task.task_type),
            "任务完成只表示执行结束；页面会重新读取 canonical artifact 确认业务状态。",
          )}<div data-live-progress>${progressPanel(task)}</div><a class="btn btn-secondary btn-wide" href="/tasks" data-route>返回任务记录</a></main>`,
        );
        bindCommonActions();
      };
      render(payload.task);
      startTaskPolling({
        api,
        taskId,
        onUpdate: render,
        onDone: render,
        onError: () => {},
      });
      return;
    }

    return caseViews.renderTaskDetail(
      taskId,
    );
  } catch (error) {
    renderLoadError("任务暂时无法读取", error);
  }
}

async function renderRoute() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  caseViews.stopTaskPolling();
  customerViews.stopTaskPolling();
  speakerViews.stopTaskPolling();
  if (!state.user) {
    if (path !== "/login") return navigate("/login", true);
    return renderLogin();
  }
  if (state.user.must_change_password && path !== "/change-password") {
    return navigate("/change-password", true);
  }
  if (path === "/login" || path === "/") return navigate("/workbench", true);
  if (path === "/change-password") return renderChangePassword();
  if (path === "/workbench") return renderWorkbench();
  if (path === "/cases") return caseViews.renderCases();
  if (path === "/cases/new") return caseViews.renderCaseNew();
  if (path === "/tasks") return renderTasks();
  if (path === "/customers") return customerViews.renderCustomers();
if (path === "/customers/new") return customerViews.renderCustomerNew();
  if (path === "/create") return contentViews.renderCreate();
  const workflowRoute = matchWorkflowRoute(path);
  if (
    workflowRoute?.name ===
    "speaker-new"
  ) {
    return speakerViews.renderSpeakerNew(
      workflowRoute.businessId,
    );
  }

  if (
    workflowRoute?.name ===
    "speaker-detail"
  ) {
    return speakerViews.renderSpeakerDetail(
      workflowRoute.businessId,
      workflowRoute.speakerId,
    );
  }
  if (workflowRoute?.name === "case-detail") {
    return caseViews.renderCaseDetail(workflowRoute.value);
  }
  if (workflowRoute?.name === "customer-edit") {
    return customerViews.renderCustomerEdit(
      workflowRoute.value,
    );
  }
  if (
    workflowRoute?.name ===
    "customer-content-operations"
  ) {
    return contentOperationsViews
      .renderContentOperations(
        workflowRoute.value,
      );
  }

  if (workflowRoute?.name === "customer-detail") {
    return customerViews.renderCustomerDetail(workflowRoute.value);
  }
  if (workflowRoute?.name === "task-detail") {
    return renderTaskDetail(workflowRoute.value);
  }
}

async function bootstrap() {
  try {
    const payload = await api("/api/auth/me", { skipAuthRedirect: true });
    state.user = payload.user;
    state.csrfToken = payload.csrf_token;
  } catch {
    state.user = null;
    state.csrfToken = null;
  }
  await renderRoute();
}

window.addEventListener("popstate", renderRoute);
bootstrap();
