/* Read-only presentation of the existing permission-scoped Task projection. */
import { formatConsoleTime as dashboardTime } from "./ui-format.mjs?v=ui-1";

const labels = { queued: "排队中", running: "进行中", awaiting_review: "待人工处理", completed: "执行完成", failed: "执行未完成", cancelled: "已取消" };

export function taskSourceResults(results) {
  const [tasks, activity] = results;
  return {
    tasks: tasks?.status === "fulfilled" && Array.isArray(tasks.value?.tasks) ? tasks.value.tasks : null,
    activity: activity?.status === "fulfilled" && Array.isArray(activity.value?.events) ? activity.value : null,
  };
}

export function taskListRows(tasks, { escapeHtml: e, icons, humanTaskType }) {
  return tasks.map(task => {
    const type = humanTaskType(task.task_type);
    const kind = /[\u4e00-\u9fff]/.test(type) ? type : "后台任务";
    // Customer/Speaker names are submitted context already admitted by this API.
    // Do not turn arbitrary Case payload suggestions into confirmed Case titles.
    const name = task.task_type === "customer_analysis" ? task.payload?.customer_name
      : task.task_type === "speaker_analysis" ? task.payload?.speaker_name : null;
    const historical = task.status === "failed" && (task.current_active_task_id || task.current_case_status === "approved");
    const status = historical ? "历史执行未完成" : labels[task.status] || "查看状态";
    const note = historical ? "已有后续处理结果，可在原任务查看历史。"
      : task.status === "failed" ? "打开原任务查看原因与恢复方式。"
      : task.stage && /[\u4e00-\u9fff]/.test(task.stage) ? task.stage : status;
    const at = dashboardTime(task.updated_at);
    return `<a class="task-record" href="/tasks/${encodeURIComponent(task.task_id)}" data-route title="Task ID: ${e(task.task_id)}" aria-label="${e(name || kind)}，${e(status)}，查看任务">
      <span class="task-record-icon ${task.status === "failed" && !historical ? "failed" : ""}">${icons[task.task_type === "case_analysis" ? "cases" : ["customer_analysis","speaker_analysis"].includes(task.task_type) ? "customers" : "tasks"]}</span>
      <span class="task-record-main">${name ? `<small>${e(kind)}</small>` : ""}<strong>${e(name || kind)}</strong><span class="task-record-note">${e(note)}</span></span>
      <span class="task-record-meta"><span class="pill ${task.status === "failed" && !historical ? "pill-failed" : "pill-archived"}">${e(status)}</span>${at ? `<time datetime="${e(task.updated_at)}" title="任务更新">${e(at)}</time>` : ""}</span>${icons.arrow}</a>`;
  }).join("");
}

export function taskReadFailure(label) {
  return `<section class="task-read-failure" role="status"><p>${label}暂时无法读取，其他已读取的内容仍可使用。</p><button class="btn btn-secondary" type="button" data-task-refresh>重新读取</button></section>`;
}

export function taskActivityRows(events, { escapeHtml: e }) {
  const status = { queued:"排队中",running:"进行中",awaiting_review:"待人工处理",completed:"执行完成",failed:"执行未完成",approved:"已确认",created:"已创建",rejected:"未采用" };
  return events.length ? `<div class="operator-activity-list">${events.map(event => `<div class="operator-activity-row"><time>${e(dashboardTime(event.at) || "时间未记录")}</time><span>${e(event.actor?.phone_masked || "历史记录 / 未记录")}</span><strong>${e(event.kind)}</strong><span>${e(event.subject)}</span><span>${e(status[event.status] || "已记录")}</span></div>`).join("")}</div>`
    : `<section class="state-panel"><h2>暂无操作记录</h2><p>提交、审核和导出操作会出现在这里。</p></section>`;
}
