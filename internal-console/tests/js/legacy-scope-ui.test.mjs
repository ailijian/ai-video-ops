import test from "node:test";
import assert from "node:assert/strict";
import {scopeReviewMarkup, bindLegacyScope} from "../../static/assets/legacy-scope-ui.mjs";

const item = {target: {source_intake_id: "source-1", constraint_id: "concern-1", constraint_sha256: "a".repeat(64)},
  groups: [{raw_answer_ref: "Q09", source_text: "<script>其他主体资料</script>", claims: [{id: "C-1", value: "未核实"}]}], eligible: true, receipts: []};
test("ordinary colleague sees sources but cannot adjudicate or continue production", () => {
  const html = scopeReviewMarkup({can_adjudicate: false, items: [item]});
  assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>|<form|\/create|继续创作/);
});
test("authorized review defaults to insufficient evidence and has a real submit", () => {
  const html = scopeReviewMarkup({can_adjudicate: true, items: [item]});
  assert.match(html, /<select name="decision"><option value="insufficient_evidence">/);
  assert.match(html, /type="submit"/); assert.match(html, /请选择已核对的来源/);
});
test("source failure cannot masquerade as clearance", async () => {
  const host = {isConnected: true, innerHTML: ""};
  await bindLegacyScope({host, businessId: "fictional", api: async () => {throw Error("offline");}});
  assert.match(host.innerHTML, /暂时无法读取/); assert.match(host.innerHTML, /现有限制保持有效/);
});
test("latest effective scope is separate from preserved historical blocking decision", () => {
  const receipt = {reason:"explicit", at:"2026-10-16T00:00:00Z", sha256:"b".repeat(64), actor:{namespace:"a".repeat(32),user_id:1}};
  const html = scopeReviewMarkup({can_adjudicate:false, items:[{...item, receipts:[
    {...receipt,decision:"insufficient_evidence"}, {...receipt,decision:"external_claims_only"}]}]});
  assert.match(html,/当前有效范围：仅外部关联主张待核实/);
  assert.match(html,/历史范围裁决（1）/);
  assert.match(html,/历史决定：证据不足，保持当前阻断/);
});
