const KNOWN_STATES = new Set([
  "idle",
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
  const submitted = !["idle", "submitting"].includes(normalized);
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

  if (normalized === "awaiting_review") {
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
