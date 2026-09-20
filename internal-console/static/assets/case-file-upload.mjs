export const CASE_FILE_MAX_BYTES = 256 * 1024 * 1024;

export function validateCaseFile(file) {
  if (!file) return "请选择与来源链接对应的视频文件。";
  if (!/\.(mp4|mov|m4v|webm)$/i.test(file.name)) return "请选择 MP4、MOV、M4V 或 WebM 视频文件。";
  if (!file.size || file.size > CASE_FILE_MAX_BYTES) return "请选择非空且不超过 256 MB 的视频。";
  return null;
}

export async function uploadCaseFile(api, { file, sourceUrl, signal }) {
  const params = new URLSearchParams({
    url: sourceUrl, suffix: file.name.slice(file.name.lastIndexOf(".")).toLowerCase(),
    rights_confirmed: "true", source_match_confirmed: "true",
  });
  return api(`/api/cases/source-files?${params}`, {
    method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file, signal,
  });
}
