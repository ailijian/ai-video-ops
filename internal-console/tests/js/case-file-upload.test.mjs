import test from "node:test";
import assert from "node:assert/strict";
import { validateCaseFile, uploadCaseFile, CASE_FILE_MAX_BYTES } from "../../static/assets/case-file-upload.mjs";

test("a supported non-empty video file is required without checkbox confirmation", () => {
  const file = { name: "source.MP4", size: 100 };
  assert.equal(validateCaseFile(file), null);
  assert.ok(validateCaseFile(null));
  assert.ok(validateCaseFile({ name: "remote.m3u8", size: 10 }));
  assert.ok(validateCaseFile({ name: "empty.mp4", size: 0 }));
  assert.ok(validateCaseFile({ ...file, size: CASE_FILE_MAX_BYTES + 1 }));
});

test("uploads raw bytes, preserves full source input and does not start analysis", async () => {
  const calls = [];
  const file = { name: "not-a-server-path.mp4", size: 50 };
  const result = await uploadCaseFile(async (...args) => { calls.push(args); return { upload_id: "u" }; }, {
    file, sourceUrl: "复制打开抖音 https://www.douyin.com/video/7999999999999999811",
  });
  assert.equal(result.upload_id, "u");
  assert.equal(calls.length, 1);
  const url = new URL(calls[0][0], "http://localhost");
  assert.equal(url.pathname, "/api/cases/source-files");
  assert.ok(url.searchParams.get("url").startsWith("复制打开抖音"));
  assert.equal(url.searchParams.get("rights_confirmed"), "true");
  assert.equal(url.searchParams.get("source_match_confirmed"), "true");
  assert.equal(calls[0][1].body, file);
  assert.equal(calls[0][1].headers["Content-Type"], "application/octet-stream");
});
