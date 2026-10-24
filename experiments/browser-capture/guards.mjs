export function sourceIdentity(raw) {
  const url = new URL(raw);
  const match = /^\/video\/(\d{10,24})\/?$/.exec(url.pathname);
  if (url.protocol !== "https:" || !["www.douyin.com", "douyin.com"].includes(url.hostname)
      || url.port || url.username || url.password || !match) throw new Error("请在抖音打开单个视频的完整页面。");
  return { caseId: match[1], sourceUrl: `https://www.douyin.com/video/${match[1]}` };
}

export function validateFrame(frame, expected = null) {
  if (!frame || frame.count !== 1 || !Number.isFinite(frame.duration) || frame.duration <= 0
      || frame.duration > 180 || !frame.videoWidth || !frame.videoHeight) {
    throw new Error("需有且仅有一个可见、已加载的视频，时长不超过 3 分钟。");
  }
  const { x, y, width, height } = frame.rect;
  if (![x, y, width, height, frame.viewportWidth, frame.viewportHeight].every(Number.isFinite)
      || x < 0 || y < 0 || width < 64 || height < 64
      || x + width > frame.viewportWidth + 1 || y + height > frame.viewportHeight + 1) {
    throw new Error("视频画面不完整，请先调整浏览器使完整视频可见。");
  }
  if (frame.objectFit !== "contain") throw new Error("播放器可能裁切画面；本次不录制，请使用完整画面模式。");
  if (expected && (frame.href !== expected.href || Math.abs(frame.duration - expected.duration) > 0.1
      || ["x", "y", "width", "height"].some(k => Math.abs(frame.rect[k] - expected.rect[k]) > 1)
      || frame.viewportWidth !== expected.viewportWidth || frame.viewportHeight !== expected.viewportHeight
      || frame.videoWidth !== expected.videoWidth || frame.videoHeight !== expected.videoHeight)) {
    throw new Error("来源或画面位置发生变化，已取消，避免生成错误来源或裁切视频。");
  }
  return frame;
}

export function cropRectangle(frame, captureWidth, captureHeight) {
  validateFrame(frame);
  const sx = captureWidth / frame.viewportWidth;
  const sy = captureHeight / frame.viewportHeight;
  if (!sx || !sy || Math.abs(sx - sy) > 0.05) throw new Error("捕获画面比例与网页不一致。");
  return [frame.rect.x * sx, frame.rect.y * sy, frame.rect.width * sx, frame.rect.height * sy];
}
