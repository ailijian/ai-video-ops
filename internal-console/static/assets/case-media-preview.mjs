// The official player uses fixed layouts, including its controls and footer.
// Resize the whole frame; shrinking its viewport crops that internal layout.
export const DOUYIN_PLAYER_VIEWPORTS = Object.freeze({
  portrait: Object.freeze({ width: 324, height: 720 }),
  landscape: Object.freeze({ width: 1280, height: 755 }),
});

export function bindCaseMediaPreview(root) {
  const frames = [...root.querySelectorAll(".douyin-review-player")];
  if (!frames.length) return () => {};

  const resize = (frame, width, height) => {
    if (width <= 0 || height <= 0) return;
    const scale = Math.min(1, width / frame.width, height / frame.height);
    frame.style.transform = `scale(${scale})`;
  };
  const byHost = new Map(frames.map((frame) => [frame.parentElement, frame]));
  const observer = new ResizeObserver((entries) => {
    for (const { target, contentRect } of entries) {
      const frame = byHost.get(target);
      if (frame) resize(frame, contentRect.width, contentRect.height);
    }
  });
  for (const [host, frame] of byHost) {
    // CSSOM properties work with the Console's strict style-src policy;
    // interpolated style attributes in HTML are intentionally not permitted.
    host.style.setProperty("--player-width", String(frame.width));
    host.style.setProperty("--player-height", String(frame.height));
    host.style.setProperty("--player-ratio", String(frame.width / frame.height));
    const { width, height } = host.getBoundingClientRect();
    resize(frame, width, height);
    observer.observe(host);
  }
  return () => observer.disconnect();
}
