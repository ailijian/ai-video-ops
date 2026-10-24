import { validateFrame, cropRectangle } from "./guards.mjs";

let session = null;
const ask = async (type, fields = {}) => {
  const reply = await chrome.runtime.sendMessage({ target: "worker", type, ...fields });
  if (!reply?.ok) throw new Error(reply?.error || "Browser capture connection lost");
  return reply.result;
};

async function cancel(reason) {
  const current = session;
  if (!current) return;
  session = null;
  clearTimeout(current.watchdog);
  clearTimeout(current.poll);
  clearInterval(current.draw);
  if (current.recorder?.state === "recording") current.recorder.stop();
  current.media?.getTracks().forEach(track => track.stop());
  current.output?.getTracks().forEach(track => track.stop());
  await current.audio?.close();
  await ask("pause", { tabId: current.tabId }).catch(() => {});
  await ask("failed", { error: reason });
}

async function start(message) {
  if (session) throw new Error("一次只能录制一个视频。");
  const current = { ...message, chunks: [], bytes: 0, complete: false, startedAt: Date.now() };
  session = current;
  current.watchdog = setTimeout(() => cancel("录制超过时限，已丢弃不完整结果。"), 210000);
  current.media = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: message.streamId } },
    video: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: message.streamId } },
  });
  if (!current.media.getAudioTracks().length) throw new Error("没有捕获到标签页音轨。");
  current.audio = new AudioContext();
  current.audio.createMediaStreamSource(current.media).connect(current.audio.destination);
  const monitor = document.querySelector("#monitor");
  monitor.srcObject = current.media;
  await monitor.play();
  const frame = validateFrame(await ask("sample", { tabId: current.tabId }));
  if (frame.seeking || frame.currentTime > 0.1) throw new Error("未回到视频起点，请等待视频加载后重试。");
  const crop = cropRectangle(frame, monitor.videoWidth, monitor.videoHeight);
  const canvas = document.querySelector("#canvas");
  canvas.width = Math.max(2, Math.round(crop[2] / 2) * 2);
  canvas.height = Math.max(2, Math.round(crop[3] / 2) * 2);
  const context = canvas.getContext("2d");
  const draw = () => context.drawImage(monitor, ...crop, 0, 0, canvas.width, canvas.height);
  draw();
  current.draw = setInterval(draw, 1000 / 30);
  current.output = new MediaStream([...canvas.captureStream(30).getVideoTracks(), ...current.media.getAudioTracks()]);
  const mimeType = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus"].find(t => MediaRecorder.isTypeSupported(t));
  if (!mimeType) throw new Error("浏览器不支持录制带音轨的 WebM。");
  current.recorder = new MediaRecorder(current.output, { mimeType, videoBitsPerSecond: 4000000, audioBitsPerSecond: 128000 });
  current.recorder.ondataavailable = event => {
    current.bytes += event.data.size;
    if (current.bytes > 96 * 1024 * 1024) { cancel("录制超过 96 MB，已取消。"); return; }
    if (event.data.size) current.chunks.push(event.data);
  };
  current.recorder.onerror = () => cancel("录制失败，未生成可上传文件。");
  current.recorder.onstop = async () => {
    if (!current.complete) return;
    try {
      const blob = new Blob(current.chunks, { type: mimeType });
      const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))]
        .map(value => value.toString(16).padStart(2, "0")).join("");
      const name = `${current.identity.caseId}_${new Date(current.startedAt).toISOString().replace(/[:.]/g, "-")}`;
      const receipt = { schema_version: "browser-capture-poc-v1", source_url: current.identity.sourceUrl,
        case_id: current.identity.caseId, completed: true, expected_duration: frame.duration,
        capture_duration: (Date.now() - current.startedAt) / 1000, audio_track_present: true,
        recording_sha256: hash, source_original_sha256: null, requires_human_completeness_review: true,
        viewport: { width: frame.viewportWidth, height: frame.viewportHeight }, crop,
        capture_method: "user_started_tab_capture", grants_media_reuse_rights: false };
      await ask("download", { files: [
        { url: URL.createObjectURL(blob), name: `${name}.webm` },
        { url: URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" })), name: `${name}.json` },
      ] });
    } catch (error) { await cancel(error.message); }
  };
  current.media.getVideoTracks()[0].onended = () => { if (!current.complete) cancel("标签页捕获已停止。"); };
  current.recorder.start(1000);
  await ask("play", { tabId: current.tabId });
  let lastTime = 0;
  let lastAdvanced = Date.now();
  const poll = async () => {
    if (session !== current) return;
    try {
      const next = validateFrame(await ask("sample", { tabId: current.tabId }), frame);
      if (next.currentTime + 0.15 < lastTime || next.currentTime - lastTime > 2.5) throw new Error("视频被跳转或重新播放，已取消。");
      if (next.currentTime > lastTime + 0.05) lastAdvanced = Date.now();
      if (Date.now() - lastAdvanced > 10000) throw new Error("播放暂停或网络卡住，已取消不完整录制。");
      lastTime = next.currentTime;
      if (next.ended && Math.abs(next.currentTime - frame.duration) <= 0.25) {
        current.complete = true;
        clearTimeout(current.watchdog);
        clearInterval(current.draw);
        current.recorder.stop();
        current.media.getTracks().forEach(track => track.stop());
        current.output.getTracks().forEach(track => track.stop());
        await current.audio.close();
        return;
      }
      current.poll = setTimeout(poll, 500);
    } catch (error) { await cancel(error.message); }
  };
  current.poll = setTimeout(poll, 500);
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target !== "recorder" || sender.id !== chrome.runtime.id) return;
  (message.type === "start" ? start(message) : cancel("用户取消，未保存录制结果。"))
    .then(() => respond({ ok: true }), async error => { respond({ ok: false, error: error.message }); await cancel(error.message); });
  return true;
});
