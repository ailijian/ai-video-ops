import { createApiClient } from "./api-client.js?v=productized-stage3-3";
import { createCaseViews } from "./case-views.js?v=operator-attribution-v1";
import { createCustomerViews } from "./customer-views.js?v=productized-stage3-3";
import { progressPanel } from "./case-components.js?v=operator-attribution-v1";
import { startTaskPolling } from "./task-progress.js";
import { customerProgressPanel } from "./customer-components.js?v=productized-stage2-3";
import { matchWorkflowRoute } from "./routes.js";
import {
  createSpeakerViews,
} from "./speaker-views.js?v=productized-stage2-3";

import {
  speakerProgressPanel,
} from "./speaker-components.js?v=productized-stage2-3";

import {
  createContentViews,
} from "./content-views.js?v=productized-stage3-3";

import {
  createContentOperationsViews,
} from "./content-operations-views.js?v=productized-stage3-3";

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
  { path: "/cases", label: "案例", icon: "cases" },
  { path: "/customers", label: "客户", icon: "customers" },
  { path: "/create", label: "创作", icon: "create" },
  { path: "/tasks", label: "任务", icon: "tasks" },
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
    <a class="nav-link ${routeIsActive(path, item.path) ? "active" : ""}"
      href="${item.path}" data-route>
      ${icons[item.icon]}<span>${item.label}</span>
    </a>`).join("");
  const bottomLinks = navItems.map((item) => `
    <a class="bottom-link ${routeIsActive(path, item.path) ? "active" : ""}" href="${item.path}" data-route>
      ${icons[item.icon]}<span>${item.label}</span>
    </a>`).join("");
  return `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="sidebar-brand">${brandMark()}<div><strong>鲸汤AI视频</strong><small>代运营工作台</small></div></div>
        <nav class="side-nav" aria-label="主导航">${sideLinks}</nav>
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
  return `<div class="page-heading"><div class="page-heading-copy">${eyebrow ? `<p class="eyebrow">${escapeHtml(eyebrow)}</p>` : ""}<h1>${escapeHtml(title)}</h1>${description ? `<p>${escapeHtml(description)}</p>` : ""}</div>${action}</div>`;
}

function skeletonPage(title) {
  app.innerHTML = shell(title, `<main class="page"><section class="state-panel state-loading" aria-label="正在加载"><span class="loading-indicator" aria-hidden="true"></span><h1>正在加载</h1><p>请稍候，内容马上就好。</p></section></main>`);
  bindCommonActions();
}

function openModal({
  title,
  description,
  confirmLabel,
  cancelLabel = "取消",
  danger = false,
  reasonLabel = "原因",
  reasonPlaceholder = "请填写原因",
  reasonRequired = false,
  profileHintRequired = false,
} = {}) {
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<section class="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby="dialog-description">
      <div class="modal-header"><h2 id="dialog-title">${escapeHtml(title)}</h2><button class="icon-button modal-close" type="button" data-modal-cancel aria-label="关闭">×</button></div>
      <p id="dialog-description">${escapeHtml(description)}</p>
      ${reasonRequired ? `<div class="field modal-reason"><label for="modal-reason">${escapeHtml(reasonLabel)}</label><textarea id="modal-reason" placeholder="${escapeHtml(reasonPlaceholder)}" required></textarea><span class="form-error" data-modal-error role="alert">请填写原因后继续。</span></div>` : ""}
      ${profileHintRequired ? `<div class="field"><label for="modal-profile-hint">这个视频更接近哪种结构？</label><select id="modal-profile-hint" required><option value="">请选择</option><option value="mix">混剪型</option><option value="news">新闻体</option><option value="hybrid">混合型</option><option value="uncertain">不确定</option></select><span class="form-error" data-modal-profile-error role="alert">请选择结构类型。</span></div>` : ""}
      <div class="modal-actions"><button class="btn btn-secondary" type="button" data-modal-cancel>${escapeHtml(cancelLabel)}</button><button class="btn ${danger ? "btn-danger" : "btn-primary"}" type="button" data-modal-confirm>${escapeHtml(confirmLabel)}</button></div>
    </section>`;
    document.body.append(backdrop);
    document.body.classList.add("modal-open");
    const modal = backdrop.querySelector(".modal");
    const confirmButton = backdrop.querySelector("[data-modal-confirm]");
    const reasonInput = backdrop.querySelector("#modal-reason");
    const profileInput = backdrop.querySelector("#modal-profile-hint");
    let settled = false;

    const close = (result) => {
      if (settled) return;
      settled = true;
      document.removeEventListener("keydown", onKeydown);
      backdrop.remove();
      document.body.classList.remove("modal-open");
      previousFocus?.focus?.();
      resolve(result);
    };
    const cancel = () => close({ confirmed: false, reason: "" });
    const confirm = () => {
      const reason = reasonInput?.value.trim() || "";
      if (reasonRequired && !reason) {
        backdrop.querySelector("[data-modal-error]").classList.add("visible");
        reasonInput.focus();
        return;
      }
      if (profileHintRequired && !profileInput.value) {
        backdrop.querySelector("[data-modal-profile-error]").classList.add("visible");
        profileInput.focus();
        return;
      }
      close({ confirmed: true, reason, profileHint: profileInput?.value || null });
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        cancel();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...modal.querySelectorAll('button:not([disabled]), textarea:not([disabled]), select:not([disabled])')];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    backdrop.querySelectorAll("[data-modal-cancel]").forEach((button) => button.addEventListener("click", cancel));
    confirmButton.addEventListener("click", confirm);
    backdrop.addEventListener("click", (event) => { if (event.target === backdrop) cancel(); });
    document.addEventListener("keydown", onKeydown);
    (reasonInput || confirmButton).focus();
  });
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
    rejected: ["未收录", "pill-archived"],
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
    const [data, customerData, caseData, creationOptions] = await Promise.all([
      api("/api/workbench?projection=productized-stage3-3"),
      api("/api/customers"),
      api("/api/cases"),
      api("/api/create/options").catch(() => null),
    ]);
    const customers = customerData?.customers || data.customers || [];
    const cases = caseData?.cases || [];
    const selectedBusinessId = data.customer_selection?.selected_business_id || null;
    const status = selectedBusinessId || customers.length === 1
      ? data.status || null
      : null;
    const hasCustomers = customers.length > 0;
    const attention = data.attention || {};
    const attentionItems = [
      [Number(attention.case_reviews || 0), "个案例待审核", "/cases", "去审核"],
      [Number(attention.persona_reviews || 0), "个客户信息待确认", "/customers", "去确认"],
      [Number(attention.content_reviews || 0), "个内容批次待审核", "/tasks", "去审核"],
      [Number(attention.running_tasks || 0), "个任务正在运行", "/tasks", "查看"],
    ].filter(([number]) => number > 0);
    const attentionTotal = attentionItems.reduce((total, [number]) => total + number, 0);
    const attentionList = attentionItems.length
      ? attentionItems.map(([number, label, path, action]) => `<a class="action-row" href="${path}" data-route><span><strong>${number}</strong> ${label}</span><span class="action-row-link">${action}${icons.arrow}</span></a>`).join("")
      : `<div class="attention-empty"><span class="status-dot status-success"></span><span>当前没有需要处理的事项。</span></div>`;
    const contentCreation = data.capabilities?.content_creation || {};
    const summary = data.summary || {};
    const customerCount = customers.length;
    const approvedCustomerCount = Number(
      customers.filter((customer) => customer.status === "approved").length,
    );
    const caseCount = cases.length;
    const approvedCaseCount = Number(
      cases.filter((item) => item.status === "approved").length,
    );
    const readyCustomerCount = Number(
      creationOptions?.ready_customer_count
        ?? summary.ready_customer_count
        ?? contentCreation.ready_customer_count
        ?? 0,
    );
    const overviewRows = [
      ["客户", customerCount, `${approvedCustomerCount} 个已确认`, "/customers"],
      ["案例", caseCount, `${approvedCaseCount} 个已入库`, "/cases"],
      ["可创作客户", readyCustomerCount, readyCustomerCount ? "可以开始新的内容创作" : "仍需确认客户与出镜人", readyCustomerCount ? "/create" : "/customers"],
    ].map(([label, value, note, path]) => `
      <a class="workbench-overview-row" href="${path}" data-route>
        <span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(note)}</small></span>
        <span class="workbench-overview-value">${Number(value)}</span>
        ${icons.arrow}
      </a>`).join("");
    const recentTasks = (data.recent_tasks || []).slice(0, 4);
    const recentWork = recentTasks.length
      ? recentTasks.map((task) => `
        <a class="workbench-recent-row" href="/tasks/${encodeURIComponent(task.task_id)}" data-route>
          <span><strong>${escapeHtml(humanTaskType(task.task_type))}</strong><small>${escapeHtml(task.payload?.customer_name || task.payload?.case_title || "查看最新进度")}</small></span>
          ${statusPill(task.status)}
          ${icons.arrow}
        </a>`).join("")
      : `<div class="attention-empty"><span class="status-dot status-success"></span><span>还没有最近任务。</span></div>`;
    const creationAvailable = creationOptions
      ? readyCustomerCount > 0
      : contentCreation.available;
    const creationCard = creationAvailable
      ? `<a class="quick-action" href="/create" data-route><span class="quick-icon">${icons.create}</span><span><strong>开始创作</strong><small>选择客户与出镜人</small></span>${icons.arrow}</a>`
      : `<div class="quick-action quick-action-disabled" aria-disabled="true"><span class="quick-icon">${icons.create}</span><span><strong>开始创作</strong><small>需要已确认的客户与出镜人</small></span></div>`;
    const hold = status?.operational_hold;
    const holdNotice = hasCustomers && hold?.active ? `<div class="notice notice-warning"><span class="notice-icon">!</span><div><strong>客户联系已暂停</strong><p>解除暂停前，相关补拍工作不会继续。下一步：${escapeHtml(displayNextAction(status.primary_next_action))}</p></div></div>` : "";
    const emptyCustomerNote = !hasCustomers ? `<div class="notice notice-info"><span class="notice-icon">i</span><div><strong>还没有客户</strong><p>从添加案例或建立第一个客户开始。</p></div></div>` : "";
    const headingDescription = attentionTotal ? `今天有 ${attentionTotal} 件事需要处理。` : "当前没有需要处理的事项。";

    const body = `
      <main class="page page-standard workbench-page">
        ${pageHeading("", "工作台", headingDescription)}
        ${holdNotice}${emptyCustomerNote}
        <section class="workbench-section">
          <div class="section-head"><h2>需要你处理</h2></div>
          <div class="action-list" aria-label="待处理事项">${attentionList}</div>
        </section>
        <section class="workbench-section">
          <div class="section-head"><h2>当前概览</h2></div>
          <div class="workbench-overview" aria-label="当前业务数据">${overviewRows}</div>
        </section>
        <section class="workbench-section">
          <div class="section-head"><h2>快捷开始</h2></div>
          <div class="quick-actions">
            <a class="quick-action" href="/cases/new" data-route><span class="quick-icon">${icons.link}</span><span><strong>添加案例</strong><small>粘贴抖音视频链接</small></span>${icons.arrow}</a>
            <a class="quick-action" href="/customers/new" data-route><span class="quick-icon">${icons.customers}</span><span><strong>新建客户</strong><small>整理客户资料</small></span>${icons.arrow}</a>
            ${creationCard}
          </div>
        </section>
        <section class="workbench-section">
          <div class="section-head"><h2>最近记录</h2><a class="section-link" href="/tasks" data-route>查看全部</a></div>
          <div class="workbench-recent" aria-label="最近任务">${recentWork}</div>
        </section>
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
    const [data, activity] = await Promise.all([api("/api/tasks"), api("/api/tasks/activity")]);
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
}${task.created_by?.phone ? `<p class="task-operator">提交人：${escapeHtml(maskPhone(task.created_by.phone))}</p>` : ""}<a class="inline-link" href="/tasks/${encodeURIComponent(task.task_id)}" data-route><span>查看任务</span><span aria-hidden="true">›</span></a></article>`).join("")}</div>` : `
      <section class="card empty-state"><div class="empty-icon">${icons.tasks}</div><h2>暂时没有任务</h2><p>案例分析、客户信息分析、出镜人分析和视频创作都会出现在这里。</p><a class="btn btn-secondary" href="/cases/new" data-route>添加案例</a></section>`;
    const activityStatus = { queued: "排队中", running: "进行中", awaiting_review: "待审核", completed: "已完成", failed: "失败", approved: "已确认", created: "已创建", rejected: "未采用" };
    const activityRows = (events) => events.length ? `<div class="operator-activity-list">${events.map((event) => `<div class="operator-activity-row"><time>${escapeHtml(event.at ? new Date(event.at).toLocaleString("zh-CN") : "时间未记录")}</time><span>${escapeHtml(event.actor?.phone_masked || "历史记录 / 未记录")}</span><strong>${escapeHtml(event.kind)}</strong><span>${escapeHtml(event.subject)}</span><span>${escapeHtml(activityStatus[event.status] || "已记录")}</span></div>`).join("")}</div>` : `<section class="state-panel"><h2>暂无操作记录</h2><p>提交、审核和导出操作会出现在这里。</p></section>`;
    const accounts = activity.accounts || [];
    app.innerHTML = shell("任务记录", `<main class="page">${pageHeading("任务", "任务记录", "这里可以查看执行进度和团队操作记录。")}
      <div class="profile-tabs" role="tablist" aria-label="任务视图"><button class="profile-tab active" type="button" data-task-tab="tasks" role="tab" aria-selected="true">任务</button><button class="profile-tab" type="button" data-task-tab="activity" role="tab" aria-selected="false">操作记录</button></div>
      <div data-task-panel="tasks">${content}</div><div data-task-panel="activity" hidden><div class="activity-filter"><label for="activity-account">操作账号</label><select id="activity-account"><option value="">全部账号</option>${accounts.map((account) => `<option value="${account.user_id}">${escapeHtml(account.phone_masked)}</option>`).join("")}</select></div><div data-activity-rows>${activityRows(activity.events || [])}</div></div></main>`);
    bindCommonActions();
    document.querySelectorAll("[data-task-tab]").forEach((tab) => tab.addEventListener("click", () => {
      document.querySelectorAll("[data-task-tab]").forEach((item) => { item.classList.toggle("active", item === tab); item.setAttribute("aria-selected", String(item === tab)); });
      document.querySelectorAll("[data-task-panel]").forEach((panel) => { panel.hidden = panel.dataset.taskPanel !== tab.dataset.taskTab; });
    }));
    document.querySelector("#activity-account").addEventListener("change", async (event) => {
      const selected = event.target.value;
      const filtered = selected ? await api(`/api/tasks/activity?user_id=${encodeURIComponent(selected)}`) : activity;
      document.querySelector("[data-activity-rows]").innerHTML = activityRows(filtered.events || []);
    });
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
  const body = `<main class="page page-form"><section class="state-panel state-error"><span class="state-icon" aria-hidden="true">!</span><h1>暂时无法完成操作</h1><p>${escapeHtml(nextAction)}</p><button class="btn btn-primary" type="button" data-retry>重新尝试</button></section></main>`;
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
  openModal,
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
  openModal,
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
  openModal,
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
            "任务完成后，页面会重新读取业务结果确认最终状态。",
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
