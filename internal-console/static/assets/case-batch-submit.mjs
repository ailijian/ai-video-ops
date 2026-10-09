// Presentation only; canonical tasks own every business state.
export function intakeItemState(item) {
  if (item.state === "input_duplicate") return "input_duplicate";
  if (item.case?.status === "approved") return "approved";
  if (item.error_code || item.task?.status === "failed") return "failed";
  if (item.case && item.classification?.status === "confirmed") return "confirmed";
  if (item.case || item.task?.status === "awaiting_review") return "needs_confirmation";
  if (item.task?.status === "completed") return "completed";
  return "analyzing";
}
export function intakeCounts(items) {
  const counts = { total: 0, analyzing: 0, needs_confirmation: 0, confirmed: 0, failed: 0, completed: 0, approved: 0, duplicates: 0 };
  for (const item of items) {
    const state = intakeItemState(item);
    if (state === "input_duplicate") { counts.duplicates += 1; continue; }
    counts.total += 1;
    counts[state] += 1;
  }
  return counts;
}

// Explicit uncertainty is a field choice, distinct from an untouched field.
export const UNCERTAIN_INDUSTRY = "__uncertain__";
export function classificationDraft(classification) {
  const { human, suggestion } = classification;
  return { industry: human ? (human.industry ?? UNCERTAIN_INDUSTRY) : (suggestion?.industry || ""),
    profile: human?.profile || suggestion?.observed_source_profile || "", checked: false, reminded: false };
}
export function classificationSubmittable(draft, { batch = false } = {}) {
  return Boolean(draft?.industry && ["mix", "news", "hybrid", "uncertain"].includes(draft.profile)
    && (!batch || (draft.industry !== UNCERTAIN_INDUSTRY && draft.profile !== "uncertain")));
}
export function classificationDiffers(draft, suggestion) {
  return classificationSubmittable(draft) && Boolean(suggestion)
    && ((draft.industry === UNCERTAIN_INDUSTRY ? null : draft.industry) !== suggestion.industry
      || draft.profile !== suggestion.observed_source_profile);
}
export function batchConfirmableItems(items, drafts) {
  return items.filter(item => intakeItemState(item) === "needs_confirmation" && item.classification?.can_confirm
    && drafts.get(item.position)?.checked && classificationSubmittable(drafts.get(item.position), { batch: true }));
}
export function confirmedClassificationLabel(human) {
  const industryUnknown = !human?.industry || human.industry === UNCERTAIN_INDUSTRY;
  const profileUnknown = !human?.profile || human.profile === "uncertain";
  if (industryUnknown && profileUnknown) return "已确认，分类暂未确定";
  if (industryUnknown || profileUnknown) return "分类已确认，部分信息待确定";
  return "分类已确认";
}
export function intakeStage(item) {
  const state = intakeItemState(item);
  if (state === "input_duplicate") return "本批重复，已合并";
  if (state === "needs_confirmation") return "等待人工确认";
  if (state === "confirmed") return confirmedClassificationLabel(item.classification.human);
  if (state === "approved") return "已加入正式案例库";
  if (state === "completed") return "本次任务已结束，请查看任务记录";
  if (state === "failed") return "解析未完成";
  if (!item.task) return "读取链接 / 等待入队";
  if (item.task.status === "queued") return "等候解析";
  return /获取|下载/.test(item.task.stage || "") ? "获取视频" : /审核|结果/.test(item.task.stage || "") ? "推荐行业与视频结构" : "分析视频内容";
}
