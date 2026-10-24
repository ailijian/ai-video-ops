// Editable configuration only. Native owners establish eligibility and production identity.
export const CONFIG_TYPES = [
  ["novel", "新闻体·创作新内容"], ["repurpose", "新闻体·改编已有内容"],
  ["persona", "人设型"], ["story", "故事型"], ["conversion", "高转化型"],
];
export const OPERATING_STAGES = {
  launch: { label: "第 1～10 天 · 快速起号期", news: 10, persona: 5, story: 5, combined: 10 },
  trust: { label: "第 11～30 天 · 信任积累期", news: 10, persona: 15, story: 15, combined: 30 },
  steady: { label: "第 31 天起 · 稳定转化期" },
};
const blank = () => Object.fromEntries(CONFIG_TYPES.map(([key]) => [key, 0]));
const count = value => value === "" || value === null ? null : Number(value);
const integer = value => Number.isSafeInteger(value) && value >= 0;
export function createConfiguration(mode = "stage", stage = "launch", revision = 0) {
  const quantities = blank();
  if (mode === "stage") {
    const preset = OPERATING_STAGES[stage];
    if (!preset) throw Error("未知运营阶段");
    if (stage === "steady") Object.assign(quantities, { novel: 1, persona: 3, story: 2, conversion: 2 });
    else Object.assign(quantities, { novel: preset.news, persona: preset.persona, story: preset.story });
  }
  return { mode, stage, quantities, combinedTarget: OPERATING_STAGES[stage]?.combined ?? null,
    cycles: 1, cyclesConfirmed: false, repurposeEnabled: false, repurposeSourceIds: [], revision, previewRevision: null };
}
export function changeConfiguration(state, field, value) {
  const next = { ...state, quantities: { ...state.quantities }, revision: state.revision + 1, previewRevision: null };
  if (field === "mode") return createConfiguration(value, state.stage, next.revision);
  if (field === "stage") return createConfiguration("stage", value, next.revision);
  if (field === "cycles") {
    next.cycles = count(value); next.cyclesConfirmed = false;
    for (const [key, multiplier] of [["novel", 1], ["persona", 3], ["story", 2], ["conversion", 2]]) {
      next.quantities[key] = integer(next.cycles) && next.cycles > 0 && Number.isSafeInteger(next.cycles * multiplier) ? next.cycles * multiplier : null;
    }
  } else if (field === "cyclesConfirmed") next.cyclesConfirmed = value === true;
  else if (field === "combinedTarget") next.combinedTarget = count(value);
  else if (field === "repurposeEnabled") {
    next.repurposeEnabled = value === true;
    if (!next.repurposeEnabled) { next.quantities.repurpose = 0; next.repurposeSourceIds = []; }
  } else if (field === "repurposeSourceIds") {
    if (!Array.isArray(value) || value.some(id => typeof id !== "string" || !id)) throw Error("请选择准确的历史内容来源");
    next.repurposeSourceIds = [...new Set(value)];
  } else if (Object.hasOwn(next.quantities, field)) {
    next.quantities[field] = count(value);
    if (field === "repurpose") {
      // Retain the existing Native wire field; explicit quantity editing is
      // now the intent. Never reinterpret saved configurations on read.
      next.repurposeEnabled = next.quantities.repurpose > 0;
      if (next.quantities.repurpose === 0) next.repurposeSourceIds = [];
    }
  }
  else throw Error("未知配置字段");
  return next;
}
export function configurationSummary(state) {
  const errors = [];
  for (const [key, label] of CONFIG_TYPES) {
    if (!integer(state.quantities[key])) errors.push({ field: key, message: `${label}需要明确填写非负整数，允许为 0。` });
  }
  if (!state.repurposeEnabled && state.quantities.repurpose > 0) errors.push({ field: "repurpose", message: "旧草稿的改编意图与数量不一致，请明确重新确认改编数量。" });
  const sources = state.repurposeSourceIds || [];
  if (!Array.isArray(sources) || new Set(sources).size !== sources.length || sources.length !== state.quantities.repurpose) {
    errors.push({ field: "repurpose", message: `本次需要选择 ${state.quantities.repurpose ?? "待填写"} 条不同的已有内容，当前已选 ${sources.length} 条；请明确调整，不会自动补足或替换。` });
  }
  const split = state.mode === "stage" && state.stage !== "steady";
  if (split && (!integer(state.combinedTarget) || state.quantities.persona + state.quantities.story !== state.combinedTarget || state.quantities.persona === null || state.quantities.story === null)) {
    errors.push({ field: "persona", message: "请调整人设与故事数量，使两项之和等于本次合计目标。" });
  }
  if (state.mode === "stage" && state.stage === "steady" && (!integer(state.cycles) || state.cycles < 1 || state.cycles > 5 || !state.cyclesConfirmed)) {
    errors.push({ field: "cyclesConfirmed", message: "请明确确认本次 1～5 个有限的四天周期。" });
  }
  const total = Object.values(state.quantities).reduce((sum, value) => sum + (integer(value) ? value : 0), 0);
  const planned = split && integer(state.combinedTarget)
    ? (state.quantities.novel ?? 0) + (state.quantities.repurpose ?? 0) + state.combinedTarget + (state.quantities.conversion ?? 0) : total;
  if (!Number.isSafeInteger(total) || !Number.isSafeInteger(planned)) errors.push({ field: "novel", message: "数量合计超出可准确计算的范围。" });
  if (total === 0) errors.push({ field: "novel", message: "总量为 0，请至少选择一条内容。" });
  if (total > 40) errors.push({ field: "novel", message: "当前隔离验证范围每批最多 40 条，请减少本次数量。" });
  return { errors, valid: errors.length === 0, planned, total,
    newsTotal: integer(state.quantities.novel) && integer(state.quantities.repurpose) ? state.quantities.novel + state.quantities.repurpose : null,
    repurposeTarget: integer(state.quantities.repurpose) ? state.quantities.repurpose : null,
    newContentTarget: total - (state.quantities.repurpose ?? 0),
    expectedDelivery: null, actualNewSemanticCount: null,
    previewCurrent: state.previewRevision === state.revision };
}
export function reviewConfiguration(state) {
  return configurationSummary(state).valid ? { ...state, previewRevision: state.revision } : state;
}
export function creationConfigurationUrl(raw, businessId) {
  if (!String(raw || "").startsWith("/create?")) return raw;
  const url = new URL(raw, "https://configuration.invalid");
  if (url.searchParams.get("business_id") !== businessId || url.searchParams.has("request_id")) return raw;
  url.pathname = "/create/config";
  return url.pathname + url.search;
}
