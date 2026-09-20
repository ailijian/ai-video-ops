import assert from "node:assert/strict";
import { submitCaseBatch } from "../../static/assets/case-batch-submit.mjs";

const items = ["1", "2", "3", "4"].map((url) => ({ url, hint: "uncertain" }));
const submitted = [];
const progress = [];
const capacityError = Object.assign(new Error("稍后重试"), { detail: { code: "GPU_PENDING_LIMIT_REACHED" }, status: 429 });
const result = await submitCaseBatch(items, async (item) => {
  submitted.push(item.url);
  if (item.url === "2") return { duplicate: true, state: "approved", case_id: "2" };
  if (item.url === "4") throw capacityError;
  return { duplicate: false, task: { task_id: `case-${item.url}` } };
}, (item) => progress.push(item));
assert.deepEqual(submitted, ["1", "2", "3", "4"]);
assert.deepEqual(result.pending.map((item) => item.url), ["4"]);
assert.equal(result.results.length, 4);
assert.equal(progress.length, 4);
assert.equal(result.results[1].response.state, "approved");

const stopped = await submitCaseBatch(items, async (item) => {
  if (item.url === "2") throw capacityError;
  return { duplicate: false, task: { task_id: `case-${item.url}` } };
});
assert.deepEqual(stopped.pending.map((item) => item.url), ["2", "3", "4"]);

const transientError = Object.assign(new Error("短链接暂不可用"), { detail: { code: "CASE_SOURCE_RESOLUTION_FAILED" } });
const continued = await submitCaseBatch(items.slice(0, 3), async (item) => {
  if (item.url === "2") throw transientError;
  return { duplicate: false, task: { task_id: `case-${item.url}` } };
});
assert.deepEqual(continued.pending.map((item) => item.url), ["2"]);
assert.equal(continued.results.length, 3);
console.log("case batch submit PASS");
