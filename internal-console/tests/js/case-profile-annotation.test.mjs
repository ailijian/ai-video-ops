import assert from "node:assert/strict";
import { caseCard, caseReviewContent } from "../../static/assets/case-components.js";
import { createCaseViews } from "../../static/assets/case-views.js";

const legacy = {
  case_id: "7999999999999999901", status: "approved", title: "历史案例",
  industry: "待分类", review: { approved: true }, can_annotate_profile: true,
  approved_case_sha256: "a".repeat(64), profile_annotation_sha256: null,
};
const pill = () => "已入库";
assert.match(caseCard(legacy, pill), /行业：待分类/);
assert.match(caseCard({ ...legacy, industry: "本地生活" }, pill), /行业：本地生活/);
assert.doesNotMatch(caseCard(legacy, pill), /提交标记：|历史补充：/);
assert.match(caseReviewContent(legacy, pill), /补充结构类型/);
for (const [hint, label] of Object.entries({ mix: "混剪型", news: "新闻体", hybrid: "混合型", uncertain: "不确定" })) {
  const annotated = { ...legacy, profile_annotation: { operator_profile_hint: hint }, observed_source_profile: "mix" };
  for (const render of [caseCard, caseReviewContent]) {
    const html = render(annotated, pill);
    assert.ok(html.includes(`历史补充：${label}`));
    assert.match(html, /系统观察：混剪型/);
    assert.doesNotMatch(html, /提交标记：|approved_case_sha256|annotation_grants/);
    const submitted = render({ ...annotated, operator_profile_hint: "news" }, pill);
    assert.match(submitted, /提交标记：新闻体/);
    assert.doesNotMatch(submitted, /历史补充：|data-profile-annotation/);
  }
}
assert.doesNotMatch(caseReviewContent({ ...legacy, can_annotate_profile: false }, pill), /data-profile-annotation/);

// Exercise the real handler with a small DOM boundary; no server/business writes.
let handler;
const button = { disabled: false, addEventListener: (_, fn) => { handler = fn; } };
globalThis.document = {
  querySelector: (selector) => selector === "[data-profile-annotation]" ? button : null,
  querySelectorAll: () => [],
};
const calls = [];
let current = legacy;
let decision = { confirmed: false };
const app = { innerHTML: "", querySelectorAll: () => [] };
const views = createCaseViews({
  app,
  api: async (url, options) => {
    calls.push({ url, options });
    if (options?.method === "POST") {
      const request = JSON.parse(options.body);
      assert.equal(request.operator_profile_hint, "news");
      assert.equal(request.approved_case_sha256, legacy.approved_case_sha256);
      assert.equal(request.expected_annotation_sha256, null);
      assert.equal(request.note, "人工选择");
      assert.ok(!("annotated_by_phone" in request));
      current = { ...legacy, profile_annotation: { operator_profile_hint: "news" } };
      return { case: current };
    }
    return current;
  },
  shell: (_, html) => html,
  skeletonPage() {}, bindCommonActions() {}, showToast() {}, statusPill: pill,
  renderLoadError: (_, error) => { throw error; },
  openModal: async (options) => {
    assert.equal(options.profileHintRequired, true);
    assert.equal(options.reasonOptional, true);
    return decision;
  },
});
await views.renderCaseDetail(legacy.case_id);
assert.equal(calls.filter(({ options }) => options?.method === "POST").length, 0, "no automatic backfill");
await handler({ currentTarget: button });
assert.equal(calls.length, 1, "cancel does not write");
decision = { confirmed: true, profileHint: "news", reason: "人工选择" };
await handler({ currentTarget: button });
assert.equal(calls[1].url, `/api/cases/${legacy.case_id}/profile-annotation`);
assert.equal(calls.length, 3, "save rereads canonical detail projection");
assert.match(app.innerHTML, /历史补充：新闻体/);
views.dispose();
console.log("CASE_PROFILE_ANNOTATION_UI_PASS");
