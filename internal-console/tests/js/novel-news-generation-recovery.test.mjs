import assert from 'node:assert/strict';
import { createNovelNewsViews } from '../../static/assets/novel-news-views.js';

let html = '';
let state = {stage: 'generation', generation: {recovery_state: 'dispatched_outcome_unknown',
  intent_sha256: 'a'.repeat(64), operation_id: 'b'.repeat(32)}};
const calls = [];
const elements = new Map();
const host = {
  get innerHTML() { return html; },
  set innerHTML(value) {
    html = value;
    elements.clear();
    for (const match of value.matchAll(/data-novel-action="([^"]+)"/g)) {
      elements.set(`[data-novel-action="${match[1]}"]`, {dataset: {novelAction: match[1]},
        disabled: value.includes(`data-novel-action="${match[1]}" disabled`), isConnected: true,
        addEventListener(event, handler) { this[event] = handler; }});
    }
    if (value.includes('data-novel-retry-consent')) elements.set('[data-novel-retry-consent]', {
      checked: false, addEventListener(event, handler) { this[event] = handler; }});
  },
  querySelector(selector) { return elements.get(selector) || null; },
  querySelectorAll(selector) { return selector === '[data-novel-action]' ?
    [...elements.values()].filter(e => e.dataset?.novelAction) : []; },
};
const view = createNovelNewsViews({escapeHtml: String, showToast() {}, api: async (path, options) => {
  calls.push([path, options]);
  if (options?.method === 'POST') {
    assert.ok(path.endsWith('/retry-generation'));
    assert.deepEqual(JSON.parse(options.body), {parent_intent_sha256: 'a'.repeat(64),
      confirmation: 'retry_unknown_generation_with_possible_additional_cost'});
    state = {stage: 'review', generation: {recovery_state: 'review_required'}, beats: []};
    return {accepted: false, task: null};
  }
  return {state};
}});
await view.restore('gen_fictional', host);
assert.match(html, /模型执行结果无法确认/);
assert.match(html, /不会自动重复生成/);
assert.match(html, /额外模型费用/);
assert.doesNotMatch(html, /data-novel-action="generate"|data-submit-novel-review|下载 Excel/);
assert.ok(calls.every(([, o]) => !o?.method), 'Restoring unknown never submits generation');
assert.equal(elements.get('[data-novel-action="retry-generation"]').disabled, true);
const consent = elements.get('[data-novel-retry-consent]');
consent.checked = true;
consent.change({currentTarget: consent});
assert.equal(elements.get('[data-novel-action="retry-generation"]').disabled, false);
await elements.get('[data-novel-action="retry-generation"]').click();
assert.equal(calls.filter(([, o]) => o?.method === 'POST').length, 1);
assert.match(html, /审核新闻体/);
for (const recovery_state of ['validated_result_unpublished', 'confirmed_failure', 'not_dispatched']) {
  state = {stage: 'generation', generation: {recovery_state, intent_sha256: 'a'.repeat(64)}};
  await view.restore('gen_fictional', host);
  if (recovery_state === 'validated_result_unpublished') {
    assert.match(html, /继续完成原操作/);
    assert.match(html, /不会重新调用模型/);
  }
  if (recovery_state === 'confirmed_failure') assert.match(html, /已确认生成结果未通过校验/);
}
state = {stage: 'generation', generation: {task_running: true, recovery_state: 'dispatched_outcome_unknown'}};
await view.restore('gen_fictional', host);
assert.match(html, /正在生成新闻体/);
assert.doesNotMatch(html, /重新尝试生成/);
state = {stage: 'blocked', generation: {recovery_state: 'source_or_authorization_conflict'}};
await view.restore('gen_fictional', host);
assert.match(html, /来源或授权已变化/);
assert.doesNotMatch(html, /data-novel-action="generate"/);
state = {stage: 'generation', generation: {recovery_state: 'dispatched_outcome_unknown', legacy_unbound: true}};
await view.restore('gen_fictional', host);
assert.match(html, /旧版生成缺少可信尝试记录/);
assert.doesNotMatch(html, /data-novel-action="retry-generation"|data-submit-novel-review/);
console.log('NOVEL_NEWS_GENERATION_RECOVERY_UI_PASS');
