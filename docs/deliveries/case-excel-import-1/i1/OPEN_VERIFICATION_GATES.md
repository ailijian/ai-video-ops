# I1 verification scope and open gates

Final pure-parser focused78 checks passed on the final source. No HTTP upload, candidate save, global duplicate lookup, formal reviewer or partial-write behavior exists in I1, so those I2/I3 tests are deferred.

Canonical affected route fell back to full. Actual final results: `[{"target": "pipeline", "status": "passed", "exit_code": 0, "counts": {"tests": 740, "failures": 0, "errors": 0, "skipped": 0, "skip_reasons": [], "passed": 740}, "seconds": 63.977}, {"target": "authority-release", "status": "passed", "exit_code": 0, "counts": {"tests": 12, "failures": 0, "errors": 0, "skipped": 0, "skip_reasons": [], "passed": 12}, "seconds": 6.377}, {"target": "frp-guard", "status": "passed", "exit_code": 0, "counts": {"tests": 30, "passed": 30, "skipped": 0}, "seconds": 3.692}, {"target": "verification", "status": "passed", "exit_code": 0, "counts": {"tests": 27, "passed": 27, "skipped": 0}, "seconds": 10.905}, {"target": "console", "status": "failed", "exit_code": 124, "counts": {}, "seconds": 900.431}, {"target": "console", "status": "failed", "exit_code": 124, "counts": {}, "seconds": 900.423}, {"target": "console", "status": "failed", "exit_code": 124, "counts": {}, "seconds": 900.405}]`.

Full regression status: **FAILED**. Timed-out Console shards do not establish complete regression PASS. Review readiness covers the bounded parser/preview and disclosed limits; independent I1 acceptance and A1/A2/A3/CC-01/CC-02 gates remain. Real-office saved workbook compatibility and production budgets are not validated.

Earlier cxi run5173f0ca was deliberately stopped before final parser corrections and is not PASS evidence. Final code was then re-run from the explicit base.
