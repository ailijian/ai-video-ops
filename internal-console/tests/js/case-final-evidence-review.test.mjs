import assert from "node:assert/strict";
import { caseReviewContent } from "../../static/assets/case-components.js";

const base = {
  case_id: "7624492255264509193", status: "awaiting_review", title: "测试案例",
  platform: "douyin", review: { can_review: true },
  review_media: { source_url: "https://www.douyin.com/video/7624492255264509193" },
};
const pending = {
  required: true, available: true,
  narration_items: [{ item_id: "A002", start: 1, end: 2, source_text: "原始语音识别", suggested_text: "模型建议修正" }],
  shot_items: [{ item_id: "frame_000003000ms.jpg", start: 3, end: 3.2 }],
};
const html = caseReviewContent({ ...base, evidence_review: pending }, () => "");
assert.match(html, /入库前确认/);
assert.match(html, /确认保留原识别/);
assert.match(html, /确认保留当前分镜/);
assert.match(html, /确认并批准入库/);
assert.doesNotMatch(html, /模型建议修正/);
const unavailable = caseReviewContent({ ...base, evidence_review: { required: true, available: false } }, () => "");
assert.match(unavailable, /disabled/);
const ordinary = caseReviewContent(base, () => "");
assert.doesNotMatch(ordinary, /入库前确认/);
assert.match(ordinary, /批准入库/);
console.log("CASE_FINAL_EVIDENCE_REVIEW_UI_PASS");
