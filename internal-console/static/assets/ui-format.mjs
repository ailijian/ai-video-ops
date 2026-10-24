/* Presentation only: the recorded actor and timestamp remain unchanged. */
export function formatConsoleTime(value, options = {}) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false,...options}).format(new Date(value));
}

export function accountLabel(value) {
  return String(value ?? "").replace(/\b(\d{3})\d{4}(\d{4})\b/g,"$1****$2");
}
