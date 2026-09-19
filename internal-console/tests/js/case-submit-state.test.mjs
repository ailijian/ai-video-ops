import assert from "node:assert/strict";
import {
  projectCaseSubmitState,
  resetCaseSubmitState,
} from "../../static/assets/case-submit-state.mjs";

const idle = projectCaseSubmitState("idle");
assert.equal(idle.submitVisible, true);
assert.equal(idle.submitDisabled, false);
assert.equal(idle.submitLabel, "开始分析");
assert.equal(idle.inputDisabled, false);

for (const state of ["queued", "running"]) {
  const projection = projectCaseSubmitState(state);
  assert.equal(projection.submitVisible, false);
  assert.equal(projection.inputDisabled, true);
  assert.equal(projection.primaryAction, null);
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
