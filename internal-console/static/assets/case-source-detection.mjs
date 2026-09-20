// Display hint only. The server resolves and validates the final video identity.
const SUPPORTED_HOSTS = new Set([
  "douyin.com", "www.douyin.com", "v.douyin.com",
  "iesdouyin.com", "www.iesdouyin.com",
]);
const SOURCE_URL_PATTERN = /https?:\/\/(?:(?!https?:\/\/)[A-Za-z0-9._~:/?#@!$&'*+,;=%-])+/gi;

// Presentation-only extraction. The server remains the source identity resolver.
export function extractCaseSourceUrls(raw) {
  const candidates = [...String(raw || "").matchAll(SOURCE_URL_PATTERN)]
    .map(([match]) => match.replace(/[,.，。；;：:！!？?、"'」》】]+$/g, ""));
  const urls = [];
  for (const candidate of candidates) {
    try {
      const parsed = new URL(candidate);
      if (SUPPORTED_HOSTS.has(parsed.hostname.toLowerCase()) && !urls.includes(candidate)) urls.push(candidate);
    } catch { /* Server validates the final input. */ }
  }
  return urls;
}

export function detectCaseSourceInput(raw) {
  const value = String(raw || "").trim();
  if (!value) return { recognized: false, label: "输入内容后自动识别来源" };
  const urls = extractCaseSourceUrls(value);
  if (!urls.length) return { recognized: false, label: "当前未识别到支持的视频来源" };
  if (urls.length > 1) return { recognized: true, label: `已识别 ${urls.length} 个抖音链接，请逐条选择结构类型` };
  if (value !== urls[0]) {
    return { recognized: true, label: "已识别：抖音分享内容" };
  }
  return { recognized: true, label: new URL(urls[0]).hostname.toLowerCase() === "v.douyin.com" ? "已识别：抖音短链接" : "已识别：抖音视频" };
}
