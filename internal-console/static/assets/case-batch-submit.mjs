const CAPACITY_CODES = new Set(["TASK_QUEUE_FULL", "GPU_PENDING_LIMIT_REACHED"]);
const STOP_CODES = new Set(["SOURCE_PROVIDER_NOT_CONFIGURED", "SOURCE_UPLOAD_REQUIRED"]);

// Each item uses the existing single-case endpoint and its durable duplicate/queue guards.
export async function submitCaseBatch(items, submit, onResult = () => {}) {
  const results = [];
  const pending = [];
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    try {
      const response = await submit(item);
      if (!response?.duplicate && !response?.task?.task_id) {
        throw new Error("未取得任务编号，请到任务记录确认提交状态后重试。");
      }
      const result = { item, response, error: null };
      results.push(result);
      onResult(result, index + 1, items.length);
    } catch (error) {
      if (error.name === "AbortError") throw error;
      const result = { item, response: null, error };
      results.push(result);
      pending.push(item);
      onResult(result, index + 1, items.length);
      if (CAPACITY_CODES.has(error.detail?.code) || STOP_CODES.has(error.detail?.code) || error.status === 401) {
        pending.push(...items.slice(index + 1));
        break;
      }
    }
  }
  return { results, pending };
}
