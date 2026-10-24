export function createApiClient({ state, onUnauthorized, onPasswordRequired }) {
  function apiError(response, payload) {
    const detail = payload?.detail;
    const fieldMessages = {
      customer_name: "请填写客户名称。",
      materials: "请粘贴客户资料，或选择先保存客户。",
      industry: "请检查行业信息。",
      speaker_name: "请填写出镜人姓名。",
      public_role: "请填写出镜人的公开身份。",
    };
    const message = Array.isArray(detail)
      ? (fieldMessages[detail[0]?.loc?.at(-1)] || "请检查填写的信息后重试。")
      : (typeof detail === "string" ? detail : detail?.message);
    const error = new Error(message || "请求失败，请稍后重试。");
    error.status = response.status;
    error.detail = detail && !Array.isArray(detail) && typeof detail === "object"
      ? detail : { message: error.message };
    return error;
  }

  return async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const method = (options.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && state.csrfToken) {
      headers.set("X-CSRF-Token", state.csrfToken);
    }
    const response = await fetch(path, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: method === "GET" || method === "HEAD" ? "no-store" : options.cache,
    });
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (!response.ok) {
      if (response.status === 401 && !options.skipAuthRedirect) onUnauthorized();
      if (response.status === 403 && payload?.detail?.code === "PASSWORD_CHANGE_REQUIRED") {
        onPasswordRequired();
      }
      throw apiError(response, payload);
    }
    return payload;
  };
}
