/* Keep this loader independent of the application module tree: even syntax or
 * import failures must leave an actionable screen. CSP remains same-origin. */
(() => {
  const entry = document.currentScript.dataset.appEntry;
  const controller = new AbortController();
  let ready = false;
  let failed = false;
  const fail = error => {
    if (failed) return;
    failed = true;
    clearTimeout(deadline);
    controller.abort();
    console.error("Workbench startup failed", error);
    const panel = document.createElement("main");
    panel.className = "boot-screen";
    panel.setAttribute("role", "alert");
    const title = document.createElement("h1");
    title.textContent = "工作台暂时无法打开";
    const detail = document.createElement("p");
    detail.textContent = error?.status === 403
      ? "当前账号暂时无法访问，请联系管理员核对权限。"
      : error?.name === "TimeoutError"
        ? "连接超时，请检查网络后重试。"
        : "页面资源或登录状态读取失败，请重新加载；若仍失败，请联系管理员。";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "btn btn-primary";
    retry.textContent = "重新加载";
    retry.addEventListener("click", () => location.reload());
    panel.append(title, detail, retry);
    document.querySelector("#app").replaceChildren(panel);
  };
  const deadline = setTimeout(() => {
    if (!ready) fail(new DOMException("Startup deadline exceeded", "TimeoutError"));
  }, 15000);
  import(entry).then(module => {
    // A late module must not start session reads after the deadline.
    if (controller.signal.aborted) return;
    return module.bootstrap({
      signal: controller.signal,
      onReady: () => { ready = true; clearTimeout(deadline); },
    });
  }).catch(fail);
})();
