import assert from "node:assert/strict";
import test from "node:test";
import { boundaryReviewPanel, progressPanel } from "../../static/assets/case-components.js";

const review = {
  shot_sha256: "a".repeat(64),
  source_url: "https://www.douyin.com/video/7687296010611280827",
  items: [
    { frame_id: "frame_000003000ms.jpg", issues: [{ type: "short_shot", start: 3, end: 3.333 }] },
    { frame_id: "frame_000008000ms.jpg", issues: [{ type: "short_shot", start: 8, end: 8.491 }] },
  ],
};

test("pending human boundary review offers two explicit decisions", () => {
  const html = boundaryReviewPanel(review);
  assert.match(html, /保留分镜/);
  assert.match(html, /合并相邻分镜/);
  assert.match(html, /3\.00–3\.33 秒/);
  assert.match(html, /8\.00–8\.49 秒/);
  assert.match(html, /在抖音打开原视频/);
  assert.equal((html.match(/<fieldset/g) || []).length, 2);
});

test("90 percent manual gate is not presented as a generic failed download", () => {
  const html = progressPanel({
    task_type: "case_analysis", task_id: "case-fixture", subject_ref: "7687296010611280827",
    status: "failed", progress: 90, stage: "分析失败", error_message: "shot boundaries manual review is not closed",
  }, { boundaryReview: review });
  assert.match(html, /分镜需要确认/);
  assert.doesNotMatch(html, /返回添加案例/);
});
