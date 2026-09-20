import assert from "node:assert/strict";
import { progressPanel } from "../../static/assets/case-components.js";
import { caseAcquisitionWarning } from "../../static/assets/case-views.js";

assert.equal(caseAcquisitionWarning(null), "");
assert.equal(caseAcquisitionWarning({ mode: "qiyun", configured: true }), "");
assert.match(caseAcquisitionWarning({ mode: "qiyun", configured: false }), /尚未连接/);
assert.match(caseAcquisitionWarning({ mode: "legacy_downloader", configured: true }), /原有下载方式/);
assert.match(caseAcquisitionWarning({ mode: "upload_only", configured: true }), /无法自动获取视频/);
assert.match(caseAcquisitionWarning(null, { unavailable: true }), /无法确认/);
assert.match(caseAcquisitionWarning({ mode: "unknown" }, { unavailable: true }), /无法确认/);
assert.equal(caseAcquisitionWarning({ mode: "legacy_downloader" }, { hasFile: true }), "");

const task = { task_type: "case_analysis", task_id: "case-test", subject_ref: "7999999999999999901", status: "queued", progress: 0, stage: "等待开始" };
assert.doesNotMatch(progressPanel({ ...task, payload: { acquisition_provider: "qiyun" } }), /视频获取方式/);
assert.match(progressPanel({ ...task, payload: { acquisition_provider: "legacy_downloader" } }), /视频获取方式：原有下载方式/);
assert.doesNotMatch(progressPanel({ ...task, payload: { acquisition_provider: "legacy_downloader", source_upload: { upload_id: "fixture" } } }), /视频获取方式/);
assert.doesNotMatch(progressPanel({ ...task, payload: {} }), /视频获取方式/);
assert.doesNotMatch(progressPanel({ ...task, task_type: "customer_analysis" }), /视频获取方式/);
console.log("case acquisition visibility PASS");
