import assert from "node:assert/strict";
import { createContentDeliveryViews } from "../../static/assets/content-delivery-views.js";

let html = "";
let state = { request_id: "gen_fictional_recovery", next_action: "RECOVER_GENERATION", content_plan: {},
  generation: { recovery_state: "retry_available", can_retry: true } };
const calls = [];
const buttons = new Map();
const host = {
  get innerHTML() { return html; },
  set innerHTML(value) { html = value; buttons.clear(); },
  querySelector(selector) {
    const attribute = selector.slice(1, -1);
    if (!html.includes(attribute)) return null;
    if (!buttons.has(selector)) buttons.set(selector, { isConnected: true, disabled: false,
      addEventListener(event, handler) { this[event] = handler; } });
    return buttons.get(selector);
  },
  querySelectorAll() { return []; },
};
globalThis.document = { querySelector: () => host };
const views = createContentDeliveryViews({
  api: async (path, options) => {
    calls.push([path, options?.method || "GET"]);
    assert.ok(!path.startsWith("/api/tasks/"), "completed canonical response must not poll a fabricated Task");
    if (options?.method === "POST") {
      state = { ...state, next_action: "EXCEL_EXPORTED", export: { completed: true }, export_closure: { completed: true } };
      return { response_version: "content-operation-response-v1.1", recovered: true, task: null,
        canonical_result: { ok: true, recovered: true } };
    }
    return { state };
  }, showToast() {}, escapeHtml: (value) => String(value),
});
await views.restore(state.request_id);
assert.match(html, /本次文案生成没有完成/);
assert.match(html, /重试生成文案/);
assert.doesNotMatch(html, /data-submit-review/);
assert.equal(calls.length, 1, "read-only restore must not start a generation");
state = { ...state, generation: { recovery_state: "blocked", can_retry: false } };
await views.restore(state.request_id);
assert.doesNotMatch(html, /data-retry-generation/);
state = { ...state, generation: { recovery_state: "outcome_unknown", can_retry: true } };
await views.restore(state.request_id);
assert.match(html, /不会自动再次请求生成/);
state = {...state, next_action:'RECOVER_GENERATION',generation:{recovery_state:'pending',operation_status:'running',can_retry:true}};
await views.restore(state.request_id);
assert.match(html,/正在恢复生成文案/);
assert.doesNotMatch(html,/data-retry-generation/);
assert.equal(calls.filter(([,method])=>method==='POST').length,0);
state = {...state,next_action:'RESUME_HUMAN_REVIEW',review:{approved:false,completed:false,
  resume_items:[{content_id:'gen_fixture-C001',decision:'approved',note:'original'}],resume_note:'unchanged'}};
await views.restore(state.request_id);
assert.match(html,/审核处理中，收据待完成/);
assert.match(html,/继续完成原操作/);
assert.doesNotMatch(html,/data-submit-review|下载 Excel/);
await buttons.get('[data-resume-human]').click({currentTarget:buttons.get('[data-resume-human]')});
assert.equal(calls.filter(([,method])=>method==='POST').length,1);
state = {...state,next_action:'EXPORT_EXCEL',review:{approved_item_count:1},export:{state:'export_receipt_pending',completed:false,can_resume:true}};
await views.restore(state.request_id);
assert.match(html,/导出文件已生成，交付确认待完成/);
assert.match(html,/继续完成原操作/);
assert.doesNotMatch(html,/下载 Excel/);
state = {...state,export:{state:'export_file_pending',completed:false,can_resume:true}};
await views.restore(state.request_id);
assert.match(html,/导出处理中，文件待生成/);
assert.doesNotMatch(html,/导出文件已生成|下载 Excel/);
state = {...state,export:{state:'legacy_unbound_orphan',completed:false,can_resume:false}};
await views.restore(state.request_id);
assert.match(html,/不能自动追认或下载/);
assert.doesNotMatch(html,/data-export-excel/);
state = { ...state, next_action: "EXPORT_EXCEL", review: { approved_item_count: 1 }, export: { completed: false } };
await views.restore(state.request_id);
await buttons.get("[data-export-excel]").click();
assert.equal(calls.filter(([, method]) => method === "POST").length, 2);
assert.match(html, /已完成/);
console.log("GENERATION_RECOVERY_AND_OPTIONAL_TASK_RESPONSE_PASS");
