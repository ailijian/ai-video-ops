# Test layers

The default test command is hermetic:

```powershell
python -m pytest
```

It runs unit/contract tests and repository-owned integration tests against
`fixtures/authority_baseline_v1`.  That baseline is synthetic and sanitized;
runtime code never falls back to it.

Exact historical checks that inspect the current production Authority are a
separate, read-only smoke layer.  They are excluded from the default command and
must be selected explicitly:

```powershell
$env:AIVO_LIVE_AUTHORITY_ROOT = 'E:\projects\ai-video-ops\ops-pipeline'
python -m pytest -m live_authority
```

Without an existing absolute `AIVO_LIVE_AUTHORITY_ROOT`, selected live tests
fail closed with a clear skip reason.  Live tests may read production artifacts
or copy them into temporary directories, but must never mutate the configured
Authority root.
