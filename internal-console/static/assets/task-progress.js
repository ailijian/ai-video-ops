export function startTaskPolling({ api, taskId, onUpdate, onDone, onError }) {
  let stopped = false;
  let finished = false;
  let inFlight = false;
  let refreshPending = false;
  let timer = null;

  const clearTimer = () => {
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
  };
  const schedule = (delay) => {
    clearTimer();
    if (!stopped && !finished && document.visibilityState !== "hidden") {
      timer = window.setTimeout(poll, delay);
    }
  };
  const removeListeners = () => {
    document.removeEventListener("visibilitychange", resume);
    window.removeEventListener("pageshow", resume);
  };

  async function poll() {
    if (stopped || finished || document.visibilityState === "hidden") return;
    if (inFlight) { refreshPending = true; return; }
    clearTimer();
    inFlight = true;
    let nextDelay = 1200;
    try {
      const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
      if (stopped) return;
      const task = payload.task;
      onUpdate(task);
      if (["awaiting_review", "completed", "failed"].includes(task.status)) {
        finished = true;
        removeListeners();
        onDone?.(task);
      }
    } catch (error) {
      if (!stopped) onError?.(error);
      nextDelay = 2500;
    } finally {
      inFlight = false;
      if (refreshPending) {
        refreshPending = false;
        schedule(0);
      } else {
        schedule(nextDelay);
      }
    }
  }

  const resume = () => {
    if (document.visibilityState === "hidden") { clearTimer(); return; }
    clearTimer();
    poll();
  };
  document.addEventListener("visibilitychange", resume);
  window.addEventListener("pageshow", resume);
  poll();
  return () => {
    stopped = true;
    clearTimer();
    removeListeners();
  };
}
