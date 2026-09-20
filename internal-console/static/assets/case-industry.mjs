export const CASE_INDUSTRIES = [
  "餐饮", "本地生活", "零售", "烘焙甜品", "美容", "教培", "服装", "饰品", "通用行业",
];

export const CUSTOM_INDUSTRY = "__custom__";

export function industryOptions(value = "") {
  const choice = CASE_INDUSTRIES.includes(value) ? value : value ? CUSTOM_INDUSTRY : "";
  return `<option value="" ${choice ? "" : "selected"}>选择行业</option>${CASE_INDUSTRIES.map((item) =>
    `<option value="${item}" ${choice === item ? "selected" : ""}>${item}</option>`
  ).join("")}<option value="${CUSTOM_INDUSTRY}" ${choice === CUSTOM_INDUSTRY ? "selected" : ""}>自定义</option>`;
}

export function industryValue(select, customInput) {
  return (select.value === CUSTOM_INDUSTRY ? customInput.value : select.value).trim();
}

export function setIndustryValue(select, customInput, value = "") {
  const normalized = String(value || "").trim();
  select.value = CASE_INDUSTRIES.includes(normalized) ? normalized : normalized ? CUSTOM_INDUSTRY : "";
  customInput.value = select.value === CUSTOM_INDUSTRY ? normalized : "";
  syncCustomIndustry(select, customInput);
}

export function syncCustomIndustry(select, customInput) {
  const custom = select.value === CUSTOM_INDUSTRY;
  customInput.hidden = !custom;
  customInput.disabled = !custom || select.disabled;
}
