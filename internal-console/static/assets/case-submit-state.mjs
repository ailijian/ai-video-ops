const KNOWN_STATES = new Set([
  "idle",
  "restoring",
  "submitting",
  "queued",
  "running",
  "awaiting_review",
  "approved",
  "failed",
  "rejected",
]);

export function projectCaseSubmitState(status = "idle") {
  const normalized = KNOWN_STATES.has(status) ? status : "idle";
  const submitted = !["idle", "restoring", "submitting"].includes(normalized);
  const projection = {
    status: normalized,
    inputDisabled: normalized !== "idle",
    pasteDisabled: normalized !== "idle",
    submitVisible: normalized === "idle" || normalized === "submitting",
    submitDisabled: normalized === "submitting",
    submitLabel: normalized === "submitting" ? "正在提交…" : "开始分析",
    primaryAction: null,
    allowReanalysis: false,
    showNewCaseReset: submitted,
  };

  if (["queued", "running"].includes(normalized)) {
    projection.primaryAction = { kind: "progress", label: "查看当前进度" };
  } else if (normalized === "awaiting_review") {
    projection.primaryAction = { kind: "review", label: "去审核案例" };
  } else if (normalized === "approved") {
    projection.primaryAction = { kind: "existing", label: "查看已有案例" };
  } else if (["failed", "rejected"].includes(normalized)) {
    projection.primaryAction = { kind: "reanalyze", label: "重新分析" };
    projection.allowReanalysis = true;
  }

  return projection;
}

export function resetCaseSubmitState() {
  return projectCaseSubmitState("idle");
}

export function caseTaskResumeDestination(task) {
  if (task?.task_type !== "case_analysis") return null;
  if (task.current_active_task_id) return `/tasks/${encodeURIComponent(task.current_active_task_id)}`;
  if (task.current_case_status === "approved" && task.subject_ref) {
    return `/cases/${encodeURIComponent(task.subject_ref)}`;
  }
  if (task.status === "failed") return null;
  return task.task_id ? `/tasks/${encodeURIComponent(task.task_id)}` : null;
}

export function projectFailedCaseTask(task) {
  const sourceUrl = task?.payload?.source_url;
  if (
    task?.task_type !== "case_analysis" ||
    task.status !== "failed" ||
    typeof task.task_id !== "string" ||
    !/^\d{10,24}$/.test(String(task.subject_ref || "")) ||
    typeof sourceUrl !== "string" ||
    !sourceUrl.trim()
  ) return null;

  const hint = task.payload.operator_profile_hint || task.payload.profile;
  return {
    taskId: task.task_id,
    caseId: String(task.subject_ref),
    sourceUrl,
    operatorProfileHint: ["mix", "news", "hybrid", "uncertain"].includes(hint) ? hint : null,
    industry: typeof task.payload.industry === "string" ? task.payload.industry : null,
    sourceAcquisitionFailed: task.error_code === "SOURCE_ACQUISITION_FAILED",
  };
}
