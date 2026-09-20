import assert from "node:assert/strict";
import { startTaskPolling } from "../../static/assets/task-progress.js";
import { progressPanel } from "../../static/assets/case-components.js";

const doc = new EventTarget();
doc.visibilityState = "visible";
const win = new EventTarget();
const timers = new Map();
let nextTimer = 1;
win.setTimeout = (callback) => { const id = nextTimer++; timers.set(id, callback); return id; };
win.clearTimeout = (id) => timers.delete(id);
globalThis.document = doc;
globalThis.window = win;

let calls = 0;
let done = 0;
const statuses = ["queued", "running", "awaiting_review"];
const stop = startTaskPolling({
  api: async (url) => {
    assert.equal(url, "/api/tasks/task-123");
    return { task: { status: statuses[calls++], subject_ref: "7999999999999999901" } };
  },
  taskId: "task-123",
  onUpdate: () => {},
  onDone: () => { done++; },
});
const flush = () => new Promise((resolve) => setImmediate(resolve));
await flush();
assert.equal(calls, 1);
assert.equal(timers.size, 1);

doc.visibilityState = "hidden";
doc.dispatchEvent(new Event("visibilitychange"));
assert.equal(timers.size, 0);
doc.visibilityState = "visible";
doc.dispatchEvent(new Event("visibilitychange"));
await flush();
assert.equal(calls, 2);
assert.equal(timers.size, 1);

win.dispatchEvent(new Event("pageshow"));
await flush();
assert.equal(calls, 3);
assert.equal(done, 1);
assert.equal(timers.size, 0);
stop();
doc.dispatchEvent(new Event("visibilitychange"));
assert.equal(calls, 3);

const waiting = progressPanel({ task_type: "case_analysis", status: "awaiting_review", progress: 100, subject_ref: "7999999999999999901" });
assert.match(waiting, /去审核案例/);
assert.match(waiting, /\/cases\/7999999999999999901/);
const completed = progressPanel({ task_type: "case_analysis", status: "completed", progress: 100, subject_ref: "7999999999999999901" });
assert.match(completed, /查看案例/);
const failed = progressPanel({ task_id: "case-7999999999999999901-abc123", task_type: "case_analysis", status: "failed", progress: 2, error_code: "SOURCE_ACQUISITION_FAILED", subject_ref: "7999999999999999901" });
assert.match(failed, /分析未完成/);
assert.match(failed, /未能获取原视频/);
assert.match(failed, /\/cases\/new\?retry_task=case-7999999999999999901-abc123/);
assert.doesNotMatch(failed, /href="\/cases\/7999999999999999901"/);
const nonCaseFailure = progressPanel({ task_type: "content_generation", status: "failed", progress: 2 });
assert.match(nonCaseFailure, /任务未完成/);
assert.doesNotMatch(nonCaseFailure, /retry_task=/);

console.log("task polling resume and case completion actions PASS");
