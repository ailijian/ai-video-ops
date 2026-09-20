import assert from "node:assert/strict";
import { bindCaseMediaPreview, DOUYIN_PLAYER_VIEWPORTS } from "../../static/assets/case-media-preview.mjs";
import { caseReviewContent } from "../../static/assets/case-components.js";

// A frame must keep the provider's complete layout while only its visual size
// changes. Test both shrinking and growing the host, including rounding.
let callback;
let disconnected = false;
const observed = [];
globalThis.ResizeObserver = class {
  constructor(fn) { callback = fn; }
  observe(host) { observed.push(host); }
  disconnect() { disconnected = true; }
};
const frames = Object.values(DOUYIN_PLAYER_VIEWPORTS).map(({ width, height }) => {
  const properties = new Map();
  const host = {
    style: { setProperty: (key, value) => properties.set(key, value) },
    getBoundingClientRect: () => ({ width: 220, height: 500 }),
    properties,
  };
  return { width, height, style: {}, parentElement: host };
});
const dispose = bindCaseMediaPreview({ querySelectorAll: () => frames });
assert.equal(observed.length, 2);
for (const frame of frames) {
  assert.equal(frame.parentElement.properties.get("--player-width"), String(frame.width));
  for (const size of [{ width: 227.875, height: 506.375 }, { width: 300, height: 666.666 }, { width: 640, height: 377.5 }, { width: 156, height: 346.65 }]) {
    callback([{ target: frame.parentElement, contentRect: size }]);
    const scale = Number(frame.style.transform.match(/^scale\((.+)\)$/)[1]);
    assert.ok(scale > 0 && scale <= 1);
    assert.ok(frame.width * scale <= size.width + 0.001, "right edge must remain visible");
    assert.ok(frame.height * scale <= size.height + 0.001, "bottom controls must remain visible");
    assert.ok(Math.abs(frame.width * scale - size.width) < 0.001 || Math.abs(frame.height * scale - size.height) < 0.001);
  }
  const previous = frame.style.transform;
  callback([{ target: frame.parentElement, contentRect: { width: 0, height: 0 } }]);
  assert.equal(frame.style.transform, previous, "hidden pages must not divide by zero");
}
dispose();
assert.ok(disconnected, "route cleanup must release the observer");
bindCaseMediaPreview({ querySelectorAll: () => [] })();

const base = { title: "预览测试", review_media: { local_available: false, remote_embed_url: "https://open.douyin.com/player/video?vid=1234567890123456", source_url: "https://www.douyin.com/video/1234567890123456" } };
const portrait = caseReviewContent(base, () => "");
assert.match(portrait, /iframe[^>]+width="324" height="720"/);
assert.match(portrait, /review-media-player portrait remote/);
assert.doesNotMatch(portrait, /style="/, "strict CSP must not depend on inline style attributes");
const landscape = caseReviewContent({ ...base, review_media: { ...base.review_media, source_width: 1920, source_height: 1080 } }, () => "");
assert.match(landscape, /iframe[^>]+width="1280" height="755"/);
assert.match(landscape, /review-media-player landscape remote/);
const local = caseReviewContent({ ...base, review_media: { ...base.review_media, local_available: true, local_url: "/api/cases/1234567890123456/media" } }, () => "");
assert.match(local, /<video controls playsinline/);
assert.doesNotMatch(local, /<iframe|portrait remote/);
console.log("CASE_MEDIA_FULL_FRAME_RESIZE_PASS");
