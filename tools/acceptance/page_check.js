// SMI 页面侧验收探针（P4）：在部署/预览站点页面执行，检查 9 大模块面板渲染状态。
// 用法：Chrome MCP evaluate_script 或控制台直接调用 window.__smiPageCheck()。
window.__smiPageCheck = () => {
  const cards = [...document.querySelectorAll(".card")];
  const find = (title) => cards.find((c) => (c.querySelector("h3")?.innerText || "").includes(title));
  const panel = (title) => {
    const c = find(title);
    if (!c) return { panel: title, ok: false, detail: "panel_missing" };
    const text = c.innerText || "";
    const empty = /暂无赛道数据|加载失败|不可用：暂无数据/.test(text) && !/季度持仓|已停止披露|T\+1|参考/.test(text);
    return { panel: title, ok: text.trim().length > 30 && !empty, detail: text.slice(0, 60).replace(/\s+/g, " ") };
  };
  const results = [
    panel("宽基指数"),
    panel("两市成交量"),
    panel("市场情绪"),
    panel("板块行情"),
    panel("主力资金"),
    panel("北向资金"),
    panel("两融数据"),
    panel("主赛道每日监测"),
    panel("今日结论"),
  ];
  const dateLabel = document.querySelector(".date-nav select")?.value || "";
  const statusLine = document.querySelector(".status-line")?.innerText || "";
  return {
    date: dateLabel,
    statusLine: statusLine.replace(/\s+/g, " ").slice(0, 120),
    passCount: results.filter((r) => r.ok).length,
    total: results.length,
    panels: results,
    overall: results.every((r) => r.ok) ? "PASS" : "FAIL",
  };
};
window.__smiPageCheck();
