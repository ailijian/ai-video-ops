import assert from "node:assert/strict";
import {
  CASE_INDUSTRIES, CUSTOM_INDUSTRY, industryOptions,
  industryValue, setIndustryValue, syncCustomIndustry,
} from "../../static/assets/case-industry.mjs";

for (const label of ["美容", "教培", "服装", "饰品", "通用行业"]) {
  assert.ok(CASE_INDUSTRIES.includes(label));
  assert.match(industryOptions(), new RegExp(label));
}
assert.match(industryOptions(), /自定义/);
assert.match(industryOptions("教培"), /value="教培" selected/);
assert.match(industryOptions("宠物服务"), new RegExp(`value="${CUSTOM_INDUSTRY}" selected`));

const select = { value: "", disabled: false };
const custom = { value: "", hidden: true, disabled: true };
setIndustryValue(select, custom, "美容");
assert.equal(industryValue(select, custom), "美容");
assert.equal(custom.hidden, true);
setIndustryValue(select, custom, "宠物服务");
assert.equal(select.value, CUSTOM_INDUSTRY);
assert.equal(custom.hidden, false);
assert.equal(industryValue(select, custom), "宠物服务");
custom.value = "宠物美容";
assert.equal(industryValue(select, custom), "宠物美容", "custom value remains editable");
select.disabled = true;
syncCustomIndustry(select, custom);
assert.equal(custom.disabled, true);
console.log("CASE_INDUSTRY_OPTIONS_PASS");
