import assert from "node:assert/strict";
import {
  projectCaseSubmitState,
  projectFailedCaseTask,
  resetCaseSubmitState,
} from "../../static/assets/case-submit-state.mjs";

const idle = projectCaseSubmitState("idle");
assert.equal(idle.submitVisible, true);
assert.equal(idle.submitDisabled, false);
assert.equal(idle.submitLabel, "开始分析");
assert.equal(idle.inputDisabled, false);
const restoring = projectCaseSubmitState("restoring");
assert.equal(restoring.submitVisible, false);
assert.equal(restoring.inputDisabled, true);

for (const state of ["queued", "running"]) {
  const projection = projectCaseSubmitState(state);
  assert.equal(projection.submitVisible, false);
  assert.equal(projection.inputDisabled, true);
  assert.deepEqual(projection.primaryAction, { kind: "progress", label: "查看当前进度" });
}

const awaiting = projectCaseSubmitState("awaiting_review");
assert.deepEqual(awaiting.primaryAction, { kind: "review", label: "去审核案例" });
assert.equal(awaiting.submitVisible, false);

const approved = projectCaseSubmitState("approved");
assert.deepEqual(approved.primaryAction, { kind: "existing", label: "查看已有案例" });

for (const state of ["failed", "rejected"]) {
  const projection = projectCaseSubmitState(state);
  assert.equal(projection.allowReanalysis, true);
  assert.deepEqual(projection.primaryAction, { kind: "reanalyze", label: "重新分析" });
  assert.equal(projection.submitVisible, false);
}

assert.deepEqual(resetCaseSubmitState(), idle);

const failedTask = {
  task_id: "case-7999999999999999901-abc123",
  task_type: "case_analysis",
  subject_ref: "7999999999999999901",
  status: "failed",
  error_code: "SOURCE_ACQUISITION_FAILED",
  payload: {
    source_url: "https://www.douyin.com/video/7999999999999999901",
    operator_profile_hint: "hybrid",
  },
};
assert.deepEqual(projectFailedCaseTask(failedTask), {
  taskId: failedTask.task_id,
  caseId: failedTask.subject_ref,
  sourceUrl: failedTask.payload.source_url,
  operatorProfileHint: "hybrid",
  sourceAcquisitionFailed: true,
});
assert.equal(projectFailedCaseTask({ ...failedTask, status: "running" }), null);
assert.equal(projectFailedCaseTask({ ...failedTask, task_type: "content_generation" }), null);
assert.equal(projectFailedCaseTask({ ...failedTask, payload: {} }), null);
assert.equal(projectFailedCaseTask({ ...failedTask, subject_ref: "not-a-video-id" }), null);
