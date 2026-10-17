import assert from "node:assert/strict";
import { caseReviewContent } from "../../static/assets/case-components.js";
import { bindCaseReviewNavigation } from "../../static/assets/case-views.js";

const base = {
  permissions: { can_review: true },
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
const ownerHtml = caseReviewContent({...base, permissions: {can_review: false}, evidence_review: pending}, () => "");
assert.doesNotMatch(ownerHtml, /data-review-action=/);
assert.match(ownerHtml, /等待指定审核人/);
assert.doesNotMatch(ownerHtml, /type="checkbox"|data-evidence-kind/);
const classifiedOwner = caseReviewContent({...base, permissions: {can_review: false}, classification: {status: "confirmed"}, evidence_review: pending}, () => "");
assert.match(classifiedOwner, /分类已确认，等待指定审核人/);
assert.doesNotMatch(classifiedOwner, /核对分类|data-review-action=|type="checkbox"/);
for (const detail of [
  {...base, review: {can_review: false}, evidence_review: pending},
  {...base, classification_required: true, classification: {status: "pending"}, evidence_review: pending},
]) {
  const blocked = caseReviewContent(detail, () => "");
  assert.doesNotMatch(blocked, /data-review-action=|type="checkbox"/);
}
assert.match(html, /勾选尚未保存/);
assert.match(html, /data-scroll-review-decision/);
assert.doesNotMatch(html, /href="#case-review-decision"/);
let jump, scrolled = false, focused = false;
bindCaseReviewNavigation({querySelector(selector) {
  return selector === "[data-scroll-review-decision]" ? {addEventListener(_,handler){jump=handler;}}
    : {scrollIntoView(){scrolled=true;},focus(){focused=true;}};
}});
jump();
assert.ok(scrolled && focused);
assert.doesNotMatch(html, /模型建议修正/);
const unavailable = caseReviewContent({ ...base, evidence_review: { required: true, available: false } }, () => "");
assert.match(unavailable, /disabled/);
const ordinary = caseReviewContent(base, () => "");
assert.doesNotMatch(ordinary, /入库前确认/);
assert.match(ordinary, /批准入库/);
console.log("CASE_FINAL_EVIDENCE_REVIEW_UI_PASS");

const terminal=caseReviewContent({...base,evidence_review:pending,
  reviewed_by:{phone:'19900001903'},permissions:{can_review:true,can_reanalyze:true},
  review:{decision:'reject',reason:'缺少可参考的结构',can_review:false,reviewed_at:'2026-10-17T01:00:00Z',attempt_id:'exact-attempt'}},()=>"");
assert.match(terminal,/本次投稿未收录|缺少可参考的结构/);
assert.match(terminal,/199\*{4}1903/);
assert.match(terminal,/分析疑点记录/);
assert.match(terminal,/attempt_id=exact-attempt/);
assert.doesNotMatch(terminal,/data-review-action=|type="checkbox"|待审核的分析疑点/);
