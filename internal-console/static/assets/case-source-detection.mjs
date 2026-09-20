// Display hint only. The server resolves and validates the final video identity.
const SUPPORTED_HOSTS = new Set([
  "douyin.com", "www.douyin.com", "v.douyin.com",
  "iesdouyin.com", "www.iesdouyin.com",
]);

export function detectCaseSourceInput(raw) {
  const value = String(raw || "").trim();
  if (!value) return { recognized: false, label: "输入内容后自动识别来源" };
  const candidates = [...value.matchAll(/https?:\/\/(?:(?!https?:\/\/)[A-Za-z0-9._~:/?#@!$&'*+,;=%-])+/gi)]
    .map(([match]) => match.replace(/[,.，。；;：:！!？?、"'」》】]+$/g, ""));
  const urls = candidates.flatMap((candidate) => {
    try {
      const parsed = new URL(candidate);
      return SUPPORTED_HOSTS.has(parsed.hostname.toLowerCase()) ? [parsed] : [];
    } catch { return []; }
  });
  if (!urls.length) return { recognized: false, label: "当前未识别到支持的视频来源" };
  if (urls.length !== 1 || value !== urls[0].href) {
    return { recognized: true, label: "已识别：抖音分享内容" };
  }
  return { recognized: true, label: urls[0].hostname.toLowerCase() === "v.douyin.com" ? "已识别：抖音短链接" : "已识别：抖音视频" };
}
