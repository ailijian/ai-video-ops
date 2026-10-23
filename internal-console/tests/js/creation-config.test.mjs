import test from "node:test";
import assert from "node:assert/strict";
import { createConfiguration, changeConfiguration as change, configurationSummary as summary, reviewConfiguration, creationConfigurationUrl } from "../../static/assets/creation-config-model.mjs";
import { scopedConfigurationContext, configurationMarkup,repurposeSelectionMarkup } from "../../static/assets/creation-config-view.mjs";
import { createConfigurationSession } from "../../static/assets/creation-config-session.mjs";

test("stage recommendations prefill editable persona/story splits and preserve exact totals", () => {
  let s = createConfiguration();
  assert.deepEqual(s.quantities, { novel: 10, repurpose: 0, persona: 5, story: 5, conversion: 0 });
  assert.equal(summary(s).valid, true); assert.equal(summary(s).planned, 20);
  assert.equal(summary(s).previewCurrent, false); // Recommendations grant no Native eligibility.
  s = change(change(s, "persona", "7"), "story", "3");
  assert.equal(summary(s).valid, true); assert.equal(summary(s).total, 20);
  assert.equal(summary(s).expectedDelivery, null);
  s = reviewConfiguration(s); assert.equal(summary(s).previewCurrent, true);
  s = change(s, "persona", "6"); assert.equal(summary(s).previewCurrent, false); assert.equal(summary(s).valid, false);
  s = change(s, "stage", "trust");
  assert.deepEqual(s.quantities, { novel: 10, repurpose: 0, persona: 15, story: 15, conversion: 0 });
  assert.equal(s.combinedTarget, 30); assert.equal(summary(s).planned, 40); assert.equal(summary(s).valid, true);
  assert.equal(summary(s).previewCurrent, false); assert.equal(summary(s).expectedDelivery, null);
  s = change(s, "mode", "free");
  assert.ok(Object.values(s.quantities).every(value => value === 0));
  s = change(s, "mode", "stage"); assert.equal(s.quantities.persona, 15);
  s = change(s, "stage", "launch"); assert.equal(s.quantities.persona, 5); assert.equal(s.quantities.story, 5);
});

test("new stage defaults never fill or rewrite an old unallocated or custom draft on read", () => {
  for (const quantities of [
    { novel: 10, repurpose: 0, persona: null, story: null, conversion: 0 },
    { novel: 10, repurpose: 0, persona: 7, story: 3, conversion: 0 },
  ]) {
    const saved = { ...createConfiguration(), quantities, revision: 8, previewRevision: null };
    const original = structuredClone(saved);
    const result = summary(saved);
    assert.deepEqual(saved, original);
    assert.equal(result.valid, quantities.persona !== null);
    assert.equal(result.previewCurrent, false);
    // An explicit stage selection, rather than reading an existing draft, applies the new recommendation.
    const reset = change(saved, "stage", "launch");
    assert.equal(reset.revision, 9); assert.equal(reset.quantities.persona, 5); assert.equal(reset.quantities.story, 5);
    assert.deepEqual(saved, original);
  }
});
test("free zero, invalid and overflow counts cannot proceed; Repurpose explicit and no semantic inflation", () => {
  let s = createConfiguration("free"); assert.equal(summary(s).valid, false);
  s = change(s,"persona","1"); assert.equal(summary(s).valid,true);
  s = change(s,"repurpose","1"); assert.equal(summary(s).valid,false);
  s = change(s,"repurposeEnabled",true); assert.equal(summary(s).total,2); assert.equal(summary(s).newContentTarget,1);
  assert.equal(summary(s).valid,false);
  s=change(s,'repurposeSourceIds',['historical-C001']);assert.equal(summary(s).valid,true);
  const markup=repurposeSelectionMarkup(s,{repurpose:{loaded:true,open:true,sources:[{source_content_id:'historical-C001',source_title:'<客户原稿>',source_central_claim:'已批准来源'}]}});
  assert.match(markup,/&lt;客户原稿&gt;/);assert.match(markup,/checked/);assert.doesNotMatch(markup,/<客户原稿>/);
  assert.equal(change(s,'repurposeEnabled',false).repurposeSourceIds.length,0);
  s = change(s,"persona","1.5"); assert.equal(summary(s).valid,false);
  s = change(s,"persona",Number.MAX_SAFE_INTEGER); s=change(s,"story",1); assert.equal(summary(s).valid,false);
});
test("steady initial finite cycle needs confirmation, every edit invalidates check", () => {
  let s = createConfiguration("stage","steady"); assert.equal(s.cycles,1); assert.equal(summary(s).valid,false);
  assert.deepEqual(s.quantities, { novel: 1, repurpose: 0, persona: 3, story: 2, conversion: 2 });
  s = change(s,"cyclesConfirmed",true); assert.equal(summary(s).total,8); assert.equal(summary(s).valid,true);
  s = reviewConfiguration(s); s=change(s,"cycles",2); assert.equal(summary(s).total,16);
  assert.deepEqual(s.quantities, { novel: 2, repurpose: 0, persona: 6, story: 4, conversion: 4 });
  assert.equal(s.cyclesConfirmed,false); assert.equal(summary(s).previewCurrent,false);
  s = change(s,"cycles",0); assert.equal(summary(s).valid,false);
});
test("configuration inherits only the scoped customer and applicable approved speakers", () => {
  const customer={business_id:"fictional",display_name:"全虚构客户",business_persona_status:"approved",creation_ready:true,
    speakers:[{speaker_id:"approved",status:"approved",display_name:"虚构人物"},{speaker_id:"unapproved",status:"draft"}]};
  const data={customer_context:{business_id:"fictional"},customers:[customer]};
  const context=scopedConfigurationContext(data,"fictional"); assert.equal(context.speakerId,"approved");
  assert.throws(()=>scopedConfigurationContext(data,"foreign")); assert.throws(()=>scopedConfigurationContext(data,"fictional","unapproved"));
  assert.equal(scopedConfigurationContext({...data,customers:[{...customer,creation_ready:false}]},"fictional").blocked,true);
  assert.equal(scopedConfigurationContext({...data,customers:[]},"fictional").blocked,true);
  assert.match(configurationMarkup(createConfiguration(),context),/全虚构客户/);
});
test("only fresh customer creation links route to configuration; historical request links survive", () => {
  assert.equal(creationConfigurationUrl("/create?business_id=fictional","fictional"),"/create/config?business_id=fictional");
  for (const path of ["/create?business_id=foreign","/create?business_id=fictional&request_id=history","/customers/fictional/content"]) {
    assert.equal(creationConfigurationUrl(path,"fictional"),path);
  }
});

test("Native check binds saved operation/configuration; double-click and lost response retain one identity", async () => {
  const calls = []; let release;
  const session = createConfigurationSession(async (path, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null; calls.push({ path, body });
    if (options.method === "PUT") return { revision: 1, operation_id: "server_operation" };
    if (path.endsWith("batches/preview")) return { preview: { can_confirm: true, batch_id: "original_native_batch", actual_target: 2,
      new_content_target: 2, source_configuration_sha256: "a".repeat(64) } };
    if (path.endsWith("batches/confirm")) return await new Promise(resolve => { release = () => resolve({ result: { batch_id: "original_native_batch" } }); });
    return { revision: 0, draft: null };
  }, "fictional");
  const state = change(createConfiguration("free"), "persona", 2);
  await session.load(); await session.check(state, "speaker");
  assert.equal(session.isChecked(state, "speaker"), true);
  assert.equal(session.isChecked(change(state, "story", 1), "speaker"), false);
  assert.equal(session.isChecked(state, "other_speaker"), false);
  const pending = session.confirm(state, "speaker");
  assert.equal(await session.confirm(state, "speaker"), null);
  release(); assert.equal((await pending).batch_id, "original_native_batch");
  assert.equal(calls.filter(call => call.path.endsWith("resolve-sources")).length, 0);
  const confirmation = calls.find(call => call.path.endsWith("confirm")).body;
  assert.equal(confirmation.operation_id, "server_operation");
  assert.equal(confirmation.preflight_sha256, "a".repeat(64));
  assert.deepEqual(confirmation.configuration, state);
  session.invalidate(); await assert.rejects(() => session.confirm(state, "speaker"), /重新核对/);
  assert.equal(calls.filter(call => call.path.endsWith("confirm")).length, 1);
});

test('saved draft is not confirmation; native confirmation survives login reload and explicit new revision clears reuse', async () => {
  const state = change(createConfiguration('free'), 'novel', 1);
  const saved = { speaker_id: 'speaker', configuration: state };
  let actual = null;
  const session = createConfigurationSession(async () => ({ revision: 1, operation_id: 'same_operation', draft: saved, confirmed_batch: actual }), 'fictional');
  await session.load(); assert.equal(session.confirmedBatch(state, 'speaker'), null);
  actual = { batch_id: 'canonical_existing_batch', actual_target: 1, intent_ref: { owner: 'native-request-batch' } };
  await session.load(); assert.equal(session.confirmedBatch(state, 'speaker').batch_id, actual.batch_id);
  assert.equal(session.confirmedBatch(state, 'another_speaker'), null);
  assert.equal(session.confirmedBatch({ ...state, revision: state.revision + 1 }, 'speaker'), null);
});

test('news is one group with two quantity sources and no extra repurpose switch',()=>{
  const context=scopedConfigurationContext({customer_context:{business_id:'fictional'},customers:[{
    business_id:'fictional',display_name:'虚构客户',business_persona_status:'approved',creation_ready:true,
    speakers:[{speaker_id:'speaker',status:'approved',display_name:'虚构人物'}]}]},'fictional');
  const markup=configurationMarkup(createConfiguration('free'),context);
  assert.match(markup,/<legend>新闻体<\/legend>/);
  assert.match(markup,/创作新内容/);assert.match(markup,/改编已有内容/);
  assert.doesNotMatch(markup,/id="config-repurposeEnabled"/);
  assert.doesNotMatch(markup,/id="config-load-repurpose"/);
  assert.equal((markup.match(/data-quantity-step=/g)||[]).length,4);
});

test('three stages recommend Novel only; free is zero; finite cycle preserves explicit Repurpose edits',()=>{
  for(const [stage,novel] of [['launch',10],['trust',10],['steady',1]]){
    const state=createConfiguration('stage',stage);
    assert.equal(state.quantities.novel,novel);assert.equal(state.quantities.repurpose,0);
    assert.equal(state.repurposeEnabled,false);assert.deepEqual(state.repurposeSourceIds,[]);
  }
  assert.ok(Object.values(createConfiguration('free').quantities).every(n=>n===0));
  let state=change(createConfiguration('stage','steady'),'repurpose',1);
  state=change(state,'cycles',2);
  assert.equal(state.quantities.novel,2);assert.equal(state.quantities.repurpose,1);
  assert.equal(state.cyclesConfirmed,false);
});

test('Repurpose 3 to 2 requires explicit deselection; zero clears identity and one never restores it',()=>{
  let state=change(createConfiguration('free'),'repurpose',3);
  state=change(state,'repurposeSourceIds',['source-a','source-b','source-c']);
  assert.equal(state.repurposeEnabled,true);assert.equal(summary(state).valid,true);
  assert.equal(summary(state).newContentTarget,0);assert.equal(summary(state).repurposeTarget,3);
  state=reviewConfiguration(state);state=change(state,'repurpose',2);
  assert.deepEqual(state.repurposeSourceIds,['source-a','source-b','source-c']);
  assert.equal(summary(state).valid,false);assert.equal(summary(state).previewCurrent,false);
  state=change(state,'repurposeSourceIds',['source-a','source-c']);assert.equal(summary(state).valid,true);
  state=change(state,'repurpose',0);assert.deepEqual(state.repurposeSourceIds,[]);assert.equal(state.repurposeEnabled,false);
  state=change(state,'repurpose',1);assert.deepEqual(state.repurposeSourceIds,[]);assert.equal(summary(state).valid,false);
});

test('two new themes plus one explicit adaptation are three videos and two new semantic targets',()=>{
  let state=change(change(createConfiguration('free'),'novel',2),'repurpose',1);
  state=change(state,'repurposeSourceIds',['source-a']);
  assert.equal(summary(state).valid,true);assert.equal(summary(state).newsTotal,3);
  assert.equal(summary(state).newContentTarget,2);assert.equal(summary(state).repurposeTarget,1);
});

test('old drafts remain unchanged on read; ambiguous intent needs an explicit quantity edit',()=>{
  const old={...change(createConfiguration('free'),'repurpose',1),repurposeEnabled:false,repurposeSourceIds:['source-a']};
  const before=structuredClone(old);assert.equal(summary(old).valid,false);assert.deepEqual(old,before);
  assert.equal(summary(change(old,'repurpose',1)).valid,true);
  const staleZero={...createConfiguration('free'),repurposeSourceIds:['source-a']};
  assert.equal(summary(staleZero).valid,false);assert.deepEqual(change(staleZero,'repurpose',0).repurposeSourceIds,[]);
  const enabledZero={...change(createConfiguration('free'),'novel',1),repurposeEnabled:true};
  assert.equal(summary(enabledZero).valid,true); // Harmless legacy wire flag; zero creates no adaptation.
});
