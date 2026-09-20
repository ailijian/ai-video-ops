import assert from "node:assert/strict";
import { detectCaseSourceInput } from "../../static/assets/case-source-detection.mjs";

assert.equal(detectCaseSourceInput("https://www.douyin.com/video/7999999999999999901").label, "已识别：抖音视频");
assert.equal(detectCaseSourceInput("https://v.douyin.com/OUUqMAZ3SvY/").label, "已识别：抖音短链接");
assert.equal(detectCaseSourceInput("复制打开抖音 https://v.douyin.com/OUUqMAZ3SvY/ RXZ:/").label, "已识别：抖音分享内容");
assert.equal(detectCaseSourceInput("复制https://v.douyin.com/OUUqMAZ3SvY/查看视频").label, "已识别：抖音分享内容");
assert.equal(detectCaseSourceInput("https://not-douyin.com/video/7999999999999999901").recognized, false);
assert.equal(detectCaseSourceInput("").recognized, false);
console.log("case source detection PASS");
