# I1 pure parser / preview

`app.case_excel_preview.preview_workbook(bytes)` is a local pure parsing API. No HTTP upload, persisted Batch/Row/Case, model dispatch, SQLite authority, Approval or Shared Publication is implemented. It reads one frozen JSON registry copied byte-identically from Founder input and verifies its SHA before parsing.

Only 案例清单 / 结构分段 / 来源与许可 yield untrusted previews. Five other sheets are completely excluded from business rows, while their ZIP/XML/formula safety is still checked. Exact8 sheet names and visible status, 使用说明!B3, row3 machine keys, row4 labels, exact key order, duplicate/missing/extra columns are checked. Row5+ is mapped through validated machine keys. H/I/J remain profile_hint/video_content_type_hint/other_type_note. DEMO- prefixes are rejected even in formal input rows. Empty rows are skipped.

Three modes use frozen conditional requirements. All 40 raw fields and row/file SHA are retained in preview; no notes become ASR/OCR/Frame/Shot/Proof. Story label is only a suggestion, `approved_video_type=null`. Profile/type conflict is a review issue, not auto-correction. Other requires description; unknown stays unclassified. No rights row or even an “已授权” declaration remains unknown/unverified, never granted.

Source URL checks reuse original Douyin stable-ID syntax reader, with safe host/scheme/port/credential checks and platform coherence. Short links remain pending without a network request. Other platforms need original Native source checking. Same stable video ID under different Excel keys is caught within the workbook; this parser never queries private Case/task indexes, so cannot disclose another user's submission. It does not claim global dedup or future permission checks passed.

Filename is only a basename; absolute, UNC, traversal, encoded slash, device and ADS forms are rejected. Valid names without an actual verified upload remain MEDIA_UPLOAD_BINDING_REQUIRED, unbound. I1 has no upload receipt input and cannot simulate media existence. Duplicate real media SHA/basename resolution is an I2 gate.

Segments require linked Case key, positive contiguous unique orders from1 and finite nonnegative time hints with end>start; end beyond declared hint flags error, but even an internally consistent hint is not verified media duration. Visual/time observations require the watched-basis declaration and remain unverified notes. Rights have at most one linked row. Orphans and duplicates receive row-specific errors.

Package safety rejects CRC failure, duplicate/unsafe/encrypted ZIP members, unsupported parts, formula/shared/array/DDE cells (including excluded sheets), active/macro/OLE/ActiveX/external links, DTD/entities/alternate XML encoding, hidden/unexpected sheets, bad cell/row identities and bounded-resource abuse. No XML/ZIP member is extracted to disk, no provider/network or subprocess is invoked.

Local defensive budgets: file5MiB; part8MiB; total32MiB;256 members; compression ratio100; XML250000 nodes/depth32; cell16000 characters; input row index<=2004. Rejection paths and representative normal inputs are tested. These are I1 defensive implementation budgets, **not validated production limits**, maximum customer capacity or performance promises. A real application upload policy and representative real-user workbook compatibility remain subject to I2 review.

Actual focused evidence executes the 16 original fictional vectors and additional security/relationship cases. X09–X13 persistence/upload/reviewer scenarios are not I1 feature PASS. They remain accurately deferred in TEST_DISPOSITION.json. The existing Native22 tests from B0 were historical evidence; they are not relabeled new I1 functionality. No synthetic video parsing or real model quality is claimed.

Original Excel/JSON bytes and old B0 ZIP/manifest/evidence remain unchanged. New navigation and current approval status are distinct from old historical snapshot status. I2 exact proposal is attached, no I2 writes or dispatch_groups call. Stop for independent review.
