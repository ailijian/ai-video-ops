export function startTaskPolling({ api, taskId, onUpdate, onDone, onError }) {
  let stopped = false;
  let timer = null;
  async function poll() {
    if (stopped) return;
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
      const task = payload.task;
      onUpdate(task);
      if (["awaiting_review", "completed", "failed"].includes(task.status)) {
        onDone?.(task);
        return;
      }
      timer = window.setTimeout(poll, 1200);
    } catch (error) {
      onError?.(error);
      timer = window.setTimeout(poll, 2500);
    }
  }
  poll();
  return () => {
    stopped = true;
    if (timer) window.clearTimeout(timer);
  };
}
