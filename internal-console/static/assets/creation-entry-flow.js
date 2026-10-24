// Presentation orchestration only. Existing native writers own each gate,
// immutable artifact and replay decision; this module never grants Authority.
export function pinNewsRequestLocation({ requestId, businessId, speakerId, newsMode }, target = window) {
  if (!['novel_content', 'cross_profile_repurpose'].includes(newsMode)
      || !/^(gen|news)_[A-Za-z0-9]+$/.test(requestId || '')) {
    throw new Error('原创作请求无法准确恢复，请保留当前页面并核对。');
  }
  const route = new URL(target.location.href);
  if (route.pathname !== '/create') throw new Error('创作页面已变化，请刷新查看原操作。');
  route.searchParams.set('request_id', requestId);
  route.searchParams.set('profile', 'news');
  route.searchParams.set('news_mode', newsMode);
  if (businessId) route.searchParams.set('business_id', businessId);
  if (speakerId) route.searchParams.set('speaker_id', speakerId);
  target.history.replaceState(target.history.state, '', route.pathname + route.search + route.hash);
  return route;
}

export function createPreparationOperation({ api, confirmation, active = null, isCurrent = () => true, onStage = () => {} }) {
  const payload = Object.freeze({ ...confirmation });
  let requestId = active?.request_id || null;
  let handoffReady = active?.handoff_ready !== false;
  let running = null;

  async function continueOriginal() {
    if (!isCurrent()) return false;
    if (!requestId || !handoffReady) {
      onStage(requestId ? "正在恢复原创作请求" : "正在建立本次创作");
      const response = await api("/api/create/confirm", { method: "POST", body: JSON.stringify(payload) });
      const resolved = response.result?.request_id;
      if (!resolved || (requestId && resolved !== requestId)) throw new Error("原创作请求无法准确恢复，请保留当前页面并核对。");
      requestId = resolved;
      handoffReady = true;
    }
    if (!isCurrent()) return false;
    onStage("正在核对创作依据");
    await api(`/api/create/${encodeURIComponent(requestId)}/resolve-sources`, { method: "POST" });
    return isCurrent();
  }

  return {
    get requestId() { return requestId; },
    // Double clicks share the same in-flight operation. An explicit continuation
    // reuses its exact confirmation key, payload and established Request.
    continue() {
      if (!running) running = continueOriginal().finally(() => { running = null; });
      return running;
    },
  };
}
