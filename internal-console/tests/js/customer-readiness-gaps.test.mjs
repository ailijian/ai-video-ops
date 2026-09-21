import assert from "node:assert/strict";
import {
  customerFieldLabel,
  customerReadinessGaps,
} from "../../static/assets/customer-components.js";


const legacy = customerReadinessGaps(["core_audience", "customer_pains"]);
assert.deepEqual(legacy, ["customer_use_context"]);
assert.equal(
  customerFieldLabel(legacy[0]),
  "还缺少顾客或使用场景信息",
);
assert.deepEqual(
  customerReadinessGaps(["business_identity", "production_bearing_facts"]),
  ["business_identity", "production_bearing_facts"],
);
console.log("CUSTOMER_READINESS_GAPS_PASS");
