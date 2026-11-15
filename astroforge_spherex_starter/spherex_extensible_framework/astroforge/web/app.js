const $ = s => document.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  n.append(...kids);
  return n;
};

const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
};

let plugins = [], errors = {};
let state = store.get("af-state", { layout: "single", open: [], active: null });
const save = () => store.set("af-state", state);

/* ---------- API + console ---------- */

async function api(path, options = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || "Request failed");
  return d;
}

function log(msg, isErr = false) {
  const t = new Date().toLocaleTimeString("en-US");
  const line = el("div", { className: isErr ? "log-err" : "", textContent: `[${t}] ${msg}` });
  const box = $("#console-log");
  box.append(line);
  box.scrollTop = box.scrollHeight;
}

/* ---------- Plugin manifest helpers ---------- */

const uiOf = p => ({ modes: ["page", "panel"], default: "panel", ...(p.ui || {}) });

function openPlugin(id) {
  const p = plugins.find(x => x.id === id);
  if (!p) return;
  if (!state.open.includes(id)) state.open.push(id);
  state.active = id;
  state.layout = "single";
  save(); render();
}

function closePlugin(id) {
  state.open = state.open.filter(x => x !== id);
  if (state.active === id) state.active = state.open.at(-1) ?? null;
  save(); render();
}

/* ---------- Sidebar & Properties ---------- */

function renderNav() {
  const nav = $("#plugin-nav");
  nav.replaceChildren();
  plugins.forEach(p => {
    const isOpen = state.open.includes(p.id) && state.active === p.id;
    const b = el("button", { className: "item" + (isOpen ? " open" : "") },
      el("span", { className: "dot" }), el("span", { textContent: p.name }));
    b.title = p.description || "";
    b.onclick = () => openPlugin(p.id);
    nav.append(b);
  });
  Object.entries(errors).forEach(([id, msg]) => {
    const b = el("div", { className: "item failed", textContent: id + " // ERROR" });
    b.title = msg;
    nav.append(b);
  });
}

function updateProperties(p) {
  const nameInput = $("#prop-name-input");
  const verDisplay = $("#prop-version-display");
  if (p) {
    nameInput.value = p.name || "";
    verDisplay.textContent = p.version || "1.0.0";
  } else {
    nameInput.value = "AstroForge Workspace";
    verDisplay.textContent = "2.6.0";
  }
}

function updateTabs() {
  const group = $("#workspace-tabs");
  group.replaceChildren();
  
  const wsTab = el("button", { className: "tab-item" + (!state.active ? " active" : ""), textContent: "Workspace" });
  wsTab.onclick = () => { state.active = null; save(); render(); };
  group.append(wsTab);

  state.open.forEach(id => {
    const p = plugins.find(x => x.id === id);
    if (!p) return;
    const t = el("button", { className: "tab-item" + (state.active === id ? " active" : ""), textContent: p.name });
    t.onclick = () => { state.active = id; save(); render(); };
    group.append(t);
  });
}

/* ---------- Workspace ---------- */

function render() {
  renderNav();
  updateTabs();

  const ws = $("#workspace");
  ws.replaceChildren();

  const activePlugin = plugins.find(p => p.id === state.active);
  updateProperties(activePlugin);

  if (!activePlugin) {
    ws.append(el("p", { className: "empty", textContent: ">> SELECT AN EXTENSION FROM THE LEFT PANEL TO START THE WORKSPACE <<" }));
    return;
  }
  ws.append(buildPanel(activePlugin));
}

function buildPanel(p) {
  const tools = el("div", { className: "panel-tools" });
  const close = el("button", { textContent: "✕ Close", title: "Close module" });
  close.onclick = () => closePlugin(p.id);
  tools.append(close);

  const head = el("div", { className: "panel-head" },
    el("div", {}, el("h2", { textContent: p.name, style: "display:inline" }),
      el("small", { textContent: " v" + p.version })),
    tools);

  const body = el("div", { className: "panel-body" });
  if (p.description) body.append(el("p", { textContent: p.description }));

  if (p.view) body.append(renderView(p));
  const hasFormView = p.view && p.view.components;
  if (!hasFormView) (p.actions || []).forEach(a => body.append(renderAction(p, a)));

  return el("article", { className: "panel" }, head, body);
}

/* ---------- Actions ---------- */

function field(input) {
  const name = input.name || input.id;
  let f;
  if (input.type === "select" || input.options) {
    f = el("select");
    (input.options || []).forEach(o => {
      const v = typeof o === "object" ? o.value : o;
      f.append(el("option", { value: v, textContent: typeof o === "object" ? o.label : o }));
    });
  } else {
    f = el("input", { type: ["number", "date"].includes(input.type || input.input_type)
      ? (input.type || input.input_type) : "text" });
    ["min", "max", "step", "placeholder"].forEach(k => { if (input[k] !== undefined) f[k] = input[k]; });
  }
  f.name = name;
  if (input.default !== undefined) f.value = input.default;
  if (input.required) f.required = true;
  return el("div", { className: "field" }, el("label", { textContent: input.label || name }), f);
}

function collect(root) {
  const payload = {};
  for (const f of root.querySelectorAll("input, select")) {
    const v = f.value.trim();
    if (f.required && !v) { f.focus(); return null; }
    payload[f.name] = f.type === "number" ? (v === "" ? null : Number(v)) : v;
  }
  return payload;
}

function renderAction(p, action, inputs = action.inputs || []) {
  const out = el("pre", { className: "result hidden" });
  const btn = el("button", { className: "btn primary", textContent: action.name || "RUN" });
  
  // Progress bar elements
  const progressContainer = el("div", { className: "progress-container hidden" });
  const progressBar = el("div", { className: "progress-bar" }, el("div", { className: "progress-fill" }));
  const progressInfo = el("div", { className: "progress-info" }, 
    el("span", { className: "progress-status", textContent: "Processing..." }),
    el("span", { className: "progress-pct", textContent: "0%" })
  );
  progressContainer.append(progressBar, progressInfo);

  const box = el("div", { className: "action" });
  if (action.name) box.append(el("h3", { textContent: action.name }));
  inputs.forEach(i => box.append(field(i)));
  box.append(btn, progressContainer, out);

  btn.onclick = async () => {
    const payload = collect(box);
    if (!payload) return log("Required parameters are missing.", true);
    btn.disabled = true;
    out.classList.remove("hidden");
    out.textContent = "Computing / Processing…";
    
    // Show progress bar & animate
    progressContainer.classList.remove("hidden");
    const fill = progressContainer.querySelector(".progress-fill");
    const pctText = progressContainer.querySelector(".progress-pct");
    const statusText = progressContainer.querySelector(".progress-status");
    
    fill.style.background = "var(--accent)";
    let currentProgress = 15;
    fill.style.width = currentProgress + "%";
    pctText.textContent = currentProgress + "%";
    statusText.textContent = "Connecting to IRSA & downloading FITS files...";

    // Simulate smooth progress while waiting for backend response
    const interval = setInterval(() => {
      if (currentProgress < 90) {
        currentProgress += Math.floor(Math.random() * 6) + 2;
        if (currentProgress > 90) currentProgress = 90;
        fill.style.width = currentProgress + "%";
        pctText.textContent = currentProgress + "%";
      }
    }, 400);

    log(`${p.name} › ${action.id} started`);
    try {
      const d = await api(`/api/plugins/${encodeURIComponent(p.id)}/actions/${encodeURIComponent(action.id)}`,
        { method: "POST", body: JSON.stringify(payload) });
      
      clearInterval(interval);
      fill.style.width = "100%";
      pctText.textContent = "100%";
      statusText.textContent = "Completed successfully";

      out.textContent = JSON.stringify(d.result, null, 2);
      log(`${p.name} › ${action.id} completed successfully`);
    } catch (e) {
      clearInterval(interval);
      fill.style.width = "100%";
      fill.style.background = "var(--err)";
      pctText.textContent = "ERROR";
      statusText.textContent = "Process failed";

      out.textContent = "Error: " + e.message;
      log(`${p.name} › ${action.id}: ${e.message}`, true);
    } finally { 
      btn.disabled = false; 
    }
  };
  return box;
}

/* ---------- Views ---------- */

function renderView(p) {
  const v = p.view;
  if (v.type === "spectrum") return spectrum(v);

  if (v.type === "spherex_custom" && v.script) {
    return mountCustomScriptView(p, v.script);
  }
  if (v.type === "spectrum") return spectrum(v);
  if (v.components) {
    const inputs = v.components.filter(c => c.type === "input" || c.type === "select")
      .map(c => ({ ...c, name: c.id }));
    const btn = v.components.find(c => c.type === "button");
    const action = { id: btn?.action || "run", name: btn?.label || "RUN" };
    return renderAction(p, action, inputs);
  }
  return el("p", { textContent: v.message || "" });
}

function spectrum(view) {
  const ns = "http://www.w3.org/2000/svg", w = 650, h = 180, pad = 38;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", "chart");
  const pts = view.points || [];
  if (!pts.length) return svg;

  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const X = v => pad + (v - x0) / (x1 - x0 || 1) * (w - 2 * pad);
  const Y = v => h - pad - (v - y0) / (y1 - y0 || 1) * (h - 2 * pad);

  const path = (d, cls) => {
    const n = document.createElementNS(ns, "path");
    n.setAttribute("d", d); n.setAttribute("class", cls); svg.append(n);
  };
  const text = (t, x, y) => {
    const n = document.createElementNS(ns, "text");
    n.textContent = t; n.setAttribute("x", x); n.setAttribute("y", y);
    n.setAttribute("text-anchor", "middle"); svg.append(n);
  };
  path(`M${pad},${pad}V${h - pad}H${w - pad}`, "axis");
  path(pts.map((p, i) => (i ? "L" : "M") + X(p.x) + "," + Y(p.y)).join(" "), "line");
  text(view.x_label || "X", w / 2, h - 5);
  text(view.y_label || "Y", pad, 14);
  return svg;
}

/* ---------- Wiring ---------- */

$("#toggle-console").onclick = () => {
  const c = $("#console"); c.classList.toggle("hidden");
  store.set("af-console", !c.classList.contains("hidden"));
};
$("#clear-console").onclick = () => $("#console-log").replaceChildren();
$("#refresh").onclick = loadPlugins;

async function loadPlugins() {
  try {
    const d = await api("/api/plugins");
    plugins = d.plugins; errors = d.errors || {};
    state.open = state.open.filter(id => plugins.some(p => p.id === id));
    if (!plugins.some(p => p.id === state.active)) state.active = state.open[0] ?? null;
    render();
    log(`${plugins.length} modules loaded into system`);
  } catch (e) { log(e.message, true); }
}

if (store.get("af-console", false)) $("#console").classList.remove("hidden");
loadPlugins();

function mountCustomScriptView(plugin, scriptUrl) {
  const container = el("div", { className: "custom-plugin-mount" });
  import(scriptUrl + "?t=" + Date.now())
    .then(mod => mod.mount(container, plugin, api, log))
    .catch(err => {
      container.textContent = "Arayüz yüklenemedi: " + err.message;
      log(err.message, true);
    });
  return container;
}