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

// Flash 提示：页面加载即从 URL 清掉 flash/err，防刷新重显；
// flash 元素已渲染，CSS 动画照常播完消失。
(() => {
  const u = new URL(location.href);
  let changed = false;
  for (const k of ["flash", "err"]) {
    if (u.searchParams.has(k)) {
      u.searchParams.delete(k);
      changed = true;
    }
  }
  if (changed) history.replaceState(null, "", u);
})();

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

// 提交素材附件区：点选 / 拖拽多文件，列表可移除（原型 renderSubmit）
(() => {
  const dz = document.querySelector("[data-dropzone]");
  if (!dz) return;
  const input = dz.querySelector("input[type=file]");
  const list = document.querySelector("[data-filelist]");
  const dt = new DataTransfer();
  const render = () => {
    input.files = dt.files;
    list.innerHTML = "";
    [...dt.files].forEach((f, i) => {
      const row = document.createElement("div");
      row.className = "filerow";
      const icon = document.createElement("span");
      icon.className = "muted";
      icon.textContent = "📎";
      const name = document.createElement("span");
      name.textContent = f.name;
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.textContent = "音频";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn small";
      btn.textContent = "移除";
      btn.addEventListener("click", () => {
        dt.items.remove(i);
        render();
      });
      row.append(icon, name, pill, btn);
      list.appendChild(row);
    });
  };
  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    [...input.files].forEach((f) => dt.items.add(f));
    input.value = "";
    render();
  });
  dz.addEventListener("dragover", (e) => e.preventDefault());
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    [...e.dataTransfer.files].forEach((f) => dt.items.add(f));
    render();
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

// 录入素材页：转写/抽取中素材的已等待计时 + 状态轮询自动刷新
(() => {
  const rows = [...document.querySelectorAll("[data-material-id]")];
  if (!rows.length) return;
  const inFlight = () =>
    rows.filter((r) => ["processing", "extracting"].includes(r.dataset.status));
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const tick = () => {
    const now = Math.floor(Date.now() / 1000);
    for (const r of inFlight()) {
      const since = Number(r.dataset.since) || now;
      const el = r.querySelector("[data-elapsed]");
      if (el) el.textContent = `已等待 ${fmt(now - since)}`;
    }
  };
  tick();
  setInterval(tick, 1000);

  if (!inFlight().length) return;
  const baseline = Object.fromEntries(rows.map((r) => [r.dataset.materialId, r.dataset.status]));
  setInterval(async () => {
    try {
      const res = await fetch("/submissions/status");
      if (!res.ok) return;
      const states = await res.json();
      if (states.some((s) => baseline[s.id] && baseline[s.id] !== s.status)) location.reload();
    } catch {
      /* 瞬时网络失败忽略，下轮重试 */
    }
  }, 20000);
})();

// 待确认信源相似名查重（IIH-06.01 ②）：点近似提示 → 把该既有信源名填入同行 srcname
// 输入框，用户再点确认走既有并入路径（不自动归并）。
document.querySelectorAll(".srcrow .srcfill").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    const row = a.closest(".srcrow");
    const input = row?.querySelector("input.srcname");
    if (input) {
      input.value = a.dataset.name;
      input.focus();
    }
  });
});
