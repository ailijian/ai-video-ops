import assert from "node:assert/strict";
import {test} from "node:test";
import {formatConsoleTime,accountLabel} from "../../static/assets/ui-format.mjs";
test("console time is stable across the UTC/business-day boundary",()=>{
  assert.match(formatConsoleTime("2026-09-30T15:59:00Z"),/2026\/09\/30 23:59/);
  assert.match(formatConsoleTime("2026-09-30T16:00:00Z"),/2026\/10\/01 00:00/);
});
test("unknown time is not a fabricated timestamp",()=>{
  for(const value of [null,undefined,"","invalid"])assert.equal(formatConsoleTime(value),"");
});
test("displayed phone is masked without inventing or changing reviewer identity",()=>{
  assert.equal(accountLabel("13900000001"),"139****0001");
  assert.equal(accountLabel("console:13900000001"),"console:139****0001");
  assert.equal(accountLabel("offline-reviewer-C"),"offline-reviewer-C");
  assert.equal(accountLabel(null),"");
});
