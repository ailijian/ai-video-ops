import assert from "node:assert/strict";
import { caseCard, caseReviewContent } from "../../static/assets/case-components.js";
import { createCaseViews } from "../../static/assets/case-views.js";

const legacy = {
  case_id: "7999999999999999901", status: "approved", title: "历史案例",
  industry: "待分类", review: { approved: true }, can_annotate_industry: true,
  approved_case_sha256: "a".repeat(64), industry_annotation_sha256: null,
};
const pill = () => "已入库";
assert.match(caseCard(legacy, pill), /行业：待分类/);
assert.match(caseReviewContent(legacy, pill), /补充行业/);
const supplemented = { ...legacy, industry_annotation: { industry: "餐饮" } };
assert.match(caseCard(supplemented, pill), /行业（历史补充）：餐饮/);
assert.match(caseReviewContent(supplemented, pill), /行业（历史补充）：餐饮/);
assert.equal(supplemented.industry, "待分类", "the canonical field stays unchanged");
const submitted = { ...supplemented, industry: "零售", can_annotate_industry: false, industry_annotation: null };
assert.match(caseCard(submitted, pill), /行业：零售/);
assert.doesNotMatch(caseReviewContent(submitted, pill), /data-industry-annotation/);

let handler;
const button = { disabled: false, addEventListener: (_, fn) => { handler = fn; } };
globalThis.document = {
  querySelector: (selector) => selector === "[data-industry-annotation]" ? button : null,
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
      assert.deepEqual(request, {
        industry: "餐饮", note: "人工确认",
        approved_case_sha256: legacy.approved_case_sha256,
        expected_annotation_sha256: null,
      });
      current = supplemented;
      return { case: current };
    }
    return current;
  },
  shell: (_, html) => html,
  skeletonPage() {}, bindCommonActions() {}, showToast() {}, statusPill: pill,
  renderLoadError: (_, error) => { throw error; },
  openModal: async (options) => {
    assert.equal(options.industryRequired, true);
    return decision;
  },
});
await views.renderCaseDetail(legacy.case_id);
assert.equal(calls.filter(({ options }) => options?.method === "POST").length, 0);
await handler({ currentTarget: button });
assert.equal(calls.length, 1, "cancelling does not save");
decision = { confirmed: true, industry: "餐饮", reason: "人工确认" };
await handler({ currentTarget: button });
assert.equal(calls[1].url, `/api/cases/${legacy.case_id}/industry-annotation`);
assert.match(app.innerHTML, /行业（历史补充）：餐饮/);
views.dispose();
console.log("CASE_INDUSTRY_ANNOTATION_UI_PASS");
