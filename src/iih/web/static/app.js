// 工具栏按钮开合模态弹窗（原生 dialog：ESC/点遮罩关闭，校验失败自动重开）
document.querySelectorAll("[data-panel]").forEach((btn) => {
  const dlg = document.getElementById(btn.dataset.panel);
  if (dlg) btn.addEventListener("click", () => dlg.showModal());
});
document.querySelectorAll("dialog.modal").forEach((dlg) => {
  if (dlg.dataset.open !== undefined) dlg.showModal();
  dlg.querySelector("[data-close]")?.addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg) dlg.close();
  });
});

// 表格列宽拖拽（data-resize 表格）：冻结初始列宽后可拖，宽度按页面路径记 localStorage
(() => {
  document.querySelectorAll("table[data-resize]").forEach((table) => {
    const ths = [...table.rows[0].cells];
    if (!ths.length) return;
    const key = "iih:colw:" + location.pathname;
    const initial = ths.map((th) => th.offsetWidth);
    table.style.tableLayout = "fixed";
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(key) || "null");
    } catch {
      saved = null;
    }
    ths.forEach((th, i) => {
      th.style.width = (saved?.[i] || initial[i]) + "px";
      const handle = document.createElement("div");
      handle.className = "colhandle";
      handle.title = "拖拽调整列宽";
      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startW = th.offsetWidth;
        const move = (ev) => {
          th.style.width = Math.max(40, startW + ev.clientX - startX) + "px";
        };
        const up = () => {
          document.removeEventListener("mousemove", move);
          document.removeEventListener("mouseup", up);
          localStorage.setItem(key, JSON.stringify(ths.map((t) => t.offsetWidth)));
        };
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
      });
      th.appendChild(handle);
    });
  });
})();

// 反馈单表单：选「事实错误」时理由转必填并切换提示（后端校验为准）
(() => {
  const form = document.querySelector("form[data-feedback]");
  if (!form) return;
  const ta = form.querySelector("textarea[name=reason]");
  const label = form.querySelector("[data-reason-label]");
  const sync = () => {
    const fe =
      form.querySelector("input[name=feedback_type]:checked")?.value === "factual_error";
    ta.required = fe;
    ta.placeholder = fe ? "必填：请说明事实错误的依据" : "理由（可选）";
    if (label) label.textContent = fe ? "理由（必填）" : "理由（可选）";
  };
  form.querySelectorAll("input[name=feedback_type]").forEach((r) =>
    r.addEventListener("change", sync)
  );
  sync();
})();
