// Editable intent delegates admission to the original bounded Native Batch owner.
export function createConfigurationSession(api, businessId) {
  let revision = 0, operationId = null, checked = null, busy = false, confirmed = null, blocked = null;
  const fingerprint = (state, speakerId) => JSON.stringify({ speakerId, state });
  const path = `/api/create/configuration/${encodeURIComponent(businessId)}`;
  return {
    async load() {
      const result = await api(path); revision = result.revision; operationId = result.operation_id || null;
      blocked = result.confirmation_blocked || null;
      confirmed = result.confirmed_batch && result.draft ? { value: result.confirmed_batch,
        fingerprint: fingerprint({ ...result.draft.configuration, previewRevision: null }, result.draft.speaker_id) } : null;
      return result.draft;
    },
    invalidate() { checked = null; },
    isChecked(state, speakerId) { return checked?.fingerprint === fingerprint(state, speakerId); },
    checkedPreview() { return checked ? structuredClone(checked.preview) : null; },
    confirmedBatch(state, speakerId) { return confirmed?.fingerprint === fingerprint(state, speakerId) ? structuredClone(confirmed.value) : null; },
    originalConfirmation() { return confirmed ? structuredClone(confirmed.value) : null; },
    blockedConfirmation() { return blocked ? structuredClone(blocked) : null; },
    async save(state, speakerId) {
      const result = await api(path, { method: "PUT", body: JSON.stringify({ revision, payload: { speaker_id: speakerId, configuration: state } }) });
      revision = result.revision; operationId = result.operation_id;
      return result;
    },
    async check(state, speakerId) {
      checked = null;
      const captured = structuredClone(state), before = fingerprint(captured, speakerId);
      await this.save(captured, speakerId);
      const result = await api("/api/create/batches/preview", { method: "POST", body: JSON.stringify({ business_id: businessId, speaker_id: speakerId,
        operation_id: operationId, configuration: captured }) });
      const preflight = result.preview;
      if (preflight?.can_confirm !== true || !preflight.batch_id || !Number.isSafeInteger(preflight.actual_target) || preflight.actual_target < 1) {
        throw Error("当前资料尚不满足本批内容的原生创作资格，请核对客户资料、数量和创作来源。");
      }
      checked = { fingerprint: before, sha: preflight.source_configuration_sha256, preview: preflight, configuration: captured, operationId };
      return preflight;
    },
    async confirm(state, speakerId) {
      if (busy) return null;
      if (!this.isChecked(state, speakerId)) throw Error("配置已变化，请重新核对创作资格。");
      busy = true;
      try {
        const result = await api("/api/create/batches/confirm", { method: "POST", body: JSON.stringify({ business_id: businessId, speaker_id: speakerId,
          configuration: checked.configuration, operation_id: checked.operationId, preflight_sha256: checked.sha }) });
        if (!result.result?.batch_id || result.result.batch_id !== checked.preview.batch_id) throw Error("本批创作尚未确认，请保留当前配置并重试。");
        return result.result;
      } finally { busy = false; }
    },
  };
}
