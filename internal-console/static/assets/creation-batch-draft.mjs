// Browser-only, unsubmitted choices. Native previews and commands own authority.
export function createBatchReviewDraft(storage, batchId) {
  const key = `creation-batch-choices:${batchId}`;
  const read = () => { try { const value = JSON.parse(storage.getItem(key) || '{}'); return value?.version === 1 ? value : { version: 1 }; } catch { return { version: 1 }; } };
  const write = value => { try { storage.setItem(key, JSON.stringify(value)); } catch { /* The current view still works without persistence. */ } };
  const valid = (item, scope, value) => scope === 'publish_copy_confirmation' ? value === true :
    value === 'approve' || item.native_kind === 'mix' && value === 'reject';
  return {
    restore(preview) {
      const saved = read()[preview.scope];
      const same = saved?.source_sha256 === preview.source_sha256;
      return { choices: preview.items.map(item => same && valid(item, preview.scope, saved.choices?.[item.slot_id]) ? saved.choices[item.slot_id] : ''),
        activeSlot: saved?.activeSlot || '', invalidated: !!saved && !same && Object.values(saved.choices || {}).some(Boolean) };
    },
    save(preview, choices, activeSlot) {
      const state = read();
      state[preview.scope] = { source_sha256: preview.source_sha256, activeSlot,
        choices: Object.fromEntries(preview.items.flatMap((item, index) => valid(item, preview.scope, choices[index]) ? [[item.slot_id, choices[index]]] : [])) };
      write(state);
    },
    clear(scope) { const state = read(); delete state[scope]; write(state); },
    position(value) { const state = read(); if (value) { state.position = value; write(state); } return state.position || null; },
  };
}

export function batchDeliveryScope(projection, legalSlots) {
  const all = (projection.groups || []).flatMap(group => group.slots || []);
  return { scope: legalSlots.length === all.length ? 'complete_target' : 'explicit_legal_subset', slot_ids: legalSlots.map(slot => slot.slot_id) };
}
