import { sourceIdentity, validateFrame } from "./guards.mjs";

let starting = false;
let downloads = new Set();
const badge = (text, title) => Promise.all([
  chrome.action.setBadgeText({ text }), chrome.action.setTitle({ title }),
]);

// Only invoked in the active user-authorized page. No hidden API, cookie or
// browser-profile access. Mutations are ordinary pause/seek/play controls.
function videoState(action) {
  const videos = [...document.querySelectorAll("video")].filter(video => {
    const r = video.getBoundingClientRect();
    return r.width >= 64 && r.height >= 64 && r.right > 0 && r.bottom > 0
      && r.left < innerWidth && r.top < innerHeight && getComputedStyle(video).visibility !== "hidden";
  });
  if (videos.length !== 1) return { count: videos.length };
  const video = videos[0];
  if (action === "prepare") { video.pause(); video.loop = false; video.currentTime = 0; }
  if (action === "play") return video.play().then(() => true);
  if (action === "pause") video.pause();
  const rect = video.getBoundingClientRect();
  return { count: 1, href: location.href, duration: video.duration, currentTime: video.currentTime,
    ended: video.ended, seeking: video.seeking, paused: video.paused,
    videoWidth: video.videoWidth, videoHeight: video.videoHeight,
    viewportWidth: innerWidth, viewportHeight: innerHeight, objectFit: getComputedStyle(video).objectFit,
    rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
}

async function sample(tabId, action = "sample") {
  const results = await chrome.scripting.executeScript({ target: { tabId }, func: videoState, args: [action] });
  return results[0]?.result;
}

async function closeCapture(error = "") {
  if (await chrome.offscreen.hasDocument()) await chrome.offscreen.closeDocument();
  await badge(error ? "ERR" : "", error || "单条录制完成；请检查文件及来源后手动上传。");
}

chrome.action.onClicked.addListener(async tab => {
  if (starting) return;
  if (await chrome.offscreen.hasDocument()) {
    await chrome.runtime.sendMessage({ target: "recorder", type: "cancel" });
    return;
  }
  starting = true;
  try {
    const identity = sourceIdentity(tab.url);
    validateFrame(await sample(tab.id));
    await sample(tab.id, "prepare");
    await chrome.offscreen.createDocument({ url: "offscreen.html", reasons: ["USER_MEDIA", "BLOBS"],
      justification: "Record only the user-selected tab, with audio, until this single video ends." });
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
    const response = await chrome.runtime.sendMessage({ target: "recorder", type: "start", tabId: tab.id, streamId, identity });
    if (!response?.ok) throw new Error(response?.error || "无法初始化录制。");
    await badge("REC", "录制中：不要移动、滚动或缩放此页；再次点击取消。");
  } catch (error) { await closeCapture(error.message); }
  finally { starting = false; }
});

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target !== "worker" || sender.id !== chrome.runtime.id) return;
  (async () => {
    if (message.type === "sample" || message.type === "play" || message.type === "pause") {
      return sample(message.tabId, message.type);
    }
    if (message.type === "failed") { await closeCapture(message.error); return true; }
    if (message.type === "download") {
      downloads = new Set();
      for (const file of message.files) {
        if (!file.url.startsWith("blob:chrome-extension://") || !/^[0-9T_Z-]+\.(webm|json)$/.test(file.name)) {
          throw new Error("Invalid local recording artifact");
        }
        downloads.add(await chrome.downloads.download({ url: file.url,
          filename: `AI-Video-Ops-Capture/${file.name}`, conflictAction: "uniquify", saveAs: false }));
      }
      await badge("SAVE", "正在保存录制文件与来源记录。");
      return true;
    }
    throw new Error("Unsupported recorder message");
  })().then(result => respond({ ok: true, result }), error => respond({ ok: false, error: error.message }));
  return true;
});

chrome.downloads.onChanged.addListener(async delta => {
  if (!downloads.has(delta.id)) return;
  if (delta.state?.current === "interrupted") { downloads.clear(); await closeCapture("保存失败，请检查浏览器下载记录。"); }
  if (delta.state?.current === "complete") {
    downloads.delete(delta.id);
    if (!downloads.size) await closeCapture();
  }
});
