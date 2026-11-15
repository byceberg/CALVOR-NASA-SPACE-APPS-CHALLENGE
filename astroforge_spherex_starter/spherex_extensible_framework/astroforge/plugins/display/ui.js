export function mount(container, plugin, api, log) {
  let state = {
    current_index: 0,
    total_fits: 0,
    selected_fits_count: 0,
    filename: "",
    current_points: [],
    image_matrix: [],
    orig_width: 450,
    orig_height: 450,
    zoom: 1.0,
    panX: 0,
    panY: 0,
    label_history: []
  };

  container.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:12px; position:relative;">
      <!-- DOWNLOADED FOLDER SELECTION BAR -->
      <div style="display:flex; gap:8px; align-items:center; background:var(--code); padding:8px 12px; border:1px solid var(--line); border-radius:4px;">
        <span style="font-size:11px; color:var(--muted); font-weight:600;">Downloaded Observation:</span>
        <select id="sx-folder-select" style="flex:1; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:3px; padding:4px 8px; font:inherit;">
          <option value="">Scanning folders...</option>
        </select>
        <button id="sx-refresh-folders" class="btn ghost" style="padding:4px 8px; font-size:10px;">⟳ Refresh</button>
        <button id="sx-load-btn" class="btn primary" style="padding:4px 12px; font-size:11px;">Open Observation</button>
      </div>

      <!-- MAIN WORKSPACE -->
      <div style="display:flex; gap:14px; align-items:flex-start; flex-wrap:wrap;">
        <!-- LEFT: CANVAS AND BOTTOM NAVIGATION -->
        <div style="flex:1; min-width:470px; display:flex; flex-direction:column; align-items:center; background:var(--code); padding:10px; border:1px solid var(--line); border-radius:4px;">
          <div style="width:100%; display:flex; justify-content:space-between; margin-bottom:6px; font-size:11px; color:var(--muted);">
            <span id="sx-fname">Please select an observation</span>
            <span id="sx-idx-badge">0 / 0</span>
          </div>

          <!-- Canvas (450x450) -->
          <canvas id="sx-canvas" width="450" height="450" style="border:1px solid var(--line); cursor:crosshair; background:#000;"></canvas>

          <!-- BOTTOM CONTROLS -->
          <div style="display:flex; align-items:center; gap:8px; margin-top:10px; flex-wrap:wrap; justify-content:center;">
            <button id="sx-prev" class="btn primary" style="padding:5px 12px;">◀ Previous</button>
            <span id="sx-step-text" style="font-weight:600; min-width:60px; text-align:center;">- / -</span>
            <button id="sx-next" class="btn primary" style="padding:5px 12px;">Next ▶</button>
            <button id="sx-clear" class="btn ghost" style="padding:5px 10px; color:#f87171; border-color:#f87171;">Clear Selection</button>
          </div>
          <div style="font-size:10px; color:var(--muted); margin-top:6px; text-align:center;">
            Use mouse wheel to zoom into cursor. Click to mark source (Original Size: <span id="sx-dim-info">450x450</span>)
          </div>
        </div>

        <!-- RIGHT: STATISTICS & ZOOM CONTROLS -->
        <div style="width:240px; background:var(--code); padding:12px; border:1px solid var(--line); border-radius:4px; display:flex; flex-direction:column; gap:10px;">
          <div style="font-weight:600; color:#fff; border-bottom:1px solid var(--line); padding-bottom:5px;">
            Observation Summary
          </div>

          <div style="display:flex; justify-content:space-between; font-size:11px;">
            <span style="color:var(--muted);">Total FITS Frames:</span>
            <strong id="sx-total" style="color:#fff;">0</strong>
          </div>

          <div style="display:flex; justify-content:space-between; font-size:11px;">
            <span style="color:var(--muted);">Processed FITS:</span>
            <strong id="sx-selected-count" style="color:#38bdf8;">0 / 0</strong>
          </div>

          <div class="progress-bar" style="margin-top:2px;">
            <div id="sx-sel-bar" class="progress-fill" style="width:0%;"></div>
          </div>

          <!-- EXPORT LABELS BUTTON -->
          <button id="sx-export-btn" class="btn primary" style="width:100%; padding:6px; font-size:11px; margin-top:4px;">Export Labels (JSON)</button>

          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); padding-bottom:5px; margin-top:6px;">
            <span style="font-weight:600; color:#fff;">Zoom Level</span>
            <button id="sx-reset-zoom" class="btn ghost" style="padding:2px 6px; font-size:9px; color:#38bdf8; border-color:#38bdf8;">Reset</button>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <input type="range" id="sx-zoom-slider" min="1" max="4" step="0.25" value="1" style="flex:1; accent-color:#38bdf8; cursor:pointer;">
            <span id="sx-zoom-val" style="font-size:11px; color:#38bdf8; min-width:35px; text-align:right;">1.00x</span>
          </div>

          <div style="font-weight:600; color:#fff; border-bottom:1px solid var(--line); padding-bottom:5px; margin-top:6px;">
            Selected Coordinates
          </div>
          <div id="sx-coords-list" style="font-family:monospace; font-size:10px; color:#38bdf8; max-height:110px; overflow-y:auto;">
            No selections yet.
          </div>
        </div>
      </div>

      <!-- LABEL INPUT MODAL (LabelImg style autocomplete) -->
      <div id="sx-modal" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%, -50%); background:var(--code); border:1px solid var(--line); padding:16px; border-radius:6px; z-index:1000; box-shadow:0 4px 16px rgba(0,0,0,0.6);">
        <div style="font-weight:600; margin-bottom:8px; color:#fff;">Cisim Adı Belirle</div>
        <input type="text" id="sx-modal-input" list="sx-history-list" style="background:var(--bg); color:var(--text); border:1px solid var(--line); padding:6px 10px; border-radius:4px; width:220px; font:inherit;" placeholder="örn. cisim1">
        <datalist id="sx-history-list"></datalist>
        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px;">
          <button id="sx-modal-cancel" class="btn ghost" style="padding:4px 10px; font-size:11px;">İptal</button>
          <button id="sx-modal-ok" class="btn primary" style="padding:4px 12px; font-size:11px;">Kaydet</button>
        </div>
      </div>
    </div>
  `;

  const canvas = container.querySelector("#sx-canvas");
  const ctx = canvas.getContext("2d");
  const folderSelect = container.querySelector("#sx-folder-select");
  const zoomSlider = container.querySelector("#sx-zoom-slider");
  const zoomVal = container.querySelector("#sx-zoom-val");
  const resetZoomBtn = container.querySelector("#sx-reset-zoom");
  const exportBtn = container.querySelector("#sx-export-btn");

  const modal = container.querySelector("#sx-modal");
  const modalInput = container.querySelector("#sx-modal-input");
  const historyList = container.querySelector("#sx-history-list");
  const modalOk = container.querySelector("#sx-modal-ok");
  const modalCancel = container.querySelector("#sx-modal-cancel");

  function resetZoomState() {
    state.zoom = 1.0;
    state.panX = 0;
    state.panY = 0;
    zoomSlider.value = 1.0;
    zoomVal.textContent = "1.00x";
    drawCanvas();
  }

  resetZoomBtn.onclick = () => {
    resetZoomState();
  };

  exportBtn.onclick = async () => {
    if (!folderSelect.value) {
      log("Lütfen önce bir gözlem klasörü seçin.", true);
      return;
    }
    await callAction("export_labels", {});
    log(`Etiketler başarıyla '${folderSelect.value}/labels.json' dosyasına aktarıldı.`);
  };

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (state.total_fits === 0) return;

    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    let newZoom = state.zoom * zoomFactor;
    newZoom = Math.max(1.0, Math.min(4.0, newZoom));

    if (newZoom === state.zoom) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left) * (canvas.width / rect.width);
    const mouseY = (e.clientY - rect.top) * (canvas.height / rect.height);

    state.panX = mouseX - (mouseX - state.panX) * (newZoom / state.zoom);
    state.panY = mouseY - (mouseY - state.panY) * (newZoom / state.zoom);
    state.zoom = newZoom;

    zoomSlider.value = state.zoom;
    zoomVal.textContent = state.zoom.toFixed(2) + "x";

    drawCanvas();
  }, { passive: false });

  zoomSlider.oninput = (e) => {
    const newZoom = parseFloat(e.target.value);
    if (newZoom === state.zoom) return;

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

    state.panX = centerX - (centerX - state.panX) * (newZoom / state.zoom);
    state.panY = centerY - (centerY - state.panY) * (newZoom / state.zoom);
    state.zoom = newZoom;

    zoomVal.textContent = state.zoom.toFixed(2) + "x";
    drawCanvas();
  };

  function showModal(defaultName, callback) {
    modalInput.value = defaultName;
    modal.style.display = "block";
    modalInput.focus();
    modalInput.select();

    const handleOk = () => {
      const val = modalInput.value.trim();
      cleanup();
      callback(val);
    };

    const handleCancel = () => {
      cleanup();
      callback(null);
    };

    const handleKeyDown = (e) => {
      if (e.key === "Enter") {
        handleOk();
      } else if (e.key === "Escape") {
        handleCancel();
      }
    };

    function cleanup() {
      modal.style.display = "none";
      modalOk.onclick = null;
      modalCancel.onclick = null;
      modalInput.onkeydown = null;
    }

    modalOk.onclick = handleOk;
    modalCancel.onclick = handleCancel;
    modalInput.onkeydown = handleKeyDown;
  }

  async function callAction(actionId, payload = {}) {
    try {
      const res = await api(`/api/plugins/${encodeURIComponent(plugin.id)}/actions/${actionId}`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      state = { ...state, ...res.result };
      if (typeof state.zoom !== "number" || isNaN(state.zoom)) state.zoom = 1.0;
      if (typeof state.panX !== "number") state.panX = 0;
      if (typeof state.panY !== "number") state.panY = 0;

      zoomSlider.value = state.zoom;
      zoomVal.textContent = state.zoom.toFixed(2) + "x";
      renderAll();
    } catch (e) {
      console.error(e);
      log(`Action "${actionId}" failed: ${e.message}`, true);
    }
  }

  async function fetchDownloadedFolders() {
    const previous = folderSelect.value; 
    try {
      const res = await api(`/api/plugins/${encodeURIComponent(plugin.id)}/actions/list_downloaded_folders`, {
        method: "POST",
        body: JSON.stringify({})
      });
      const folders = res.result.folders || [];
      if (folders.length === 0) {
        folderSelect.innerHTML = `<option value="">No folders under downloaded_fits/</option>`;
        return;
      }
      folderSelect.innerHTML =
        `<option value="">-- Select an observation --</option>` +
        folders.map(f => `<option value="${f}">${f}</option>`).join("");

      if (previous && folders.includes(previous)) {
        folderSelect.value = previous;
      }
    } catch (e) {
      console.error(e);
      log("Failed to list downloaded folders: " + e.message, true);
    }
  }

  async function loadSelectedFolder(folderName) {
    if (!folderName) {
      log("Please select an observation folder first.", true);
      return;
    }
    log(`Opening downloaded observation folder: ${folderName}`);
    resetZoomState();
    await callAction("select_folder", { folder_name: folderName });
  }

  container.querySelector("#sx-load-btn").onclick = () => {
    loadSelectedFolder(folderSelect.value);
  };

  container.querySelector("#sx-refresh-folders").onclick = () => {
    fetchDownloadedFolders();
  };

  function renderAll() {
    container.querySelector("#sx-fname").textContent = state.filename || "No file";
    container.querySelector("#sx-idx-badge").textContent = `Frame #${state.current_index + 1}`;
    container.querySelector("#sx-step-text").textContent = `${state.current_index + 1} / ${state.total_fits}`;
    container.querySelector("#sx-dim-info").textContent = `${state.orig_width}x${state.orig_height}`;

    container.querySelector("#sx-total").textContent = state.total_fits;
    container.querySelector("#sx-selected-count").textContent = `${state.selected_fits_count} / ${state.total_fits}`;
    const pct = state.total_fits ? Math.round((state.selected_fits_count / state.total_fits) * 100) : 0;
    container.querySelector("#sx-sel-bar").style.width = `${pct}%`;

    historyList.innerHTML = (state.label_history || []).map(lbl => `<option value="${lbl}">`).join("");

    const listEl = container.querySelector("#sx-coords-list");
    if (!state.current_points || state.current_points.length === 0) {
      listEl.innerHTML = `<span style="color:var(--muted);">No markings in this frame.</span>`;
    } else {
      listEl.innerHTML = state.current_points.map((p, i) =>
        `<div style="padding:4px 0; border-bottom:1px dashed var(--line);">
          <strong>${p.name || ('#' + (i + 1))}</strong> px(${p.x}, ${p.y})<br>
          <span style="color:#a1a1aa;">RA: ${p.ra}° | Dec: ${p.dec}°</span>
        </div>`
      ).join("");
    }

    drawCanvas();
  }

  function drawCanvas() {
    const mat = state.image_matrix;
    if (!mat || !mat.length) {
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      return;
    }
    const h = mat.length, w = mat[0].length;
    const imgData = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const val = mat[y][x];
        const idx = (y * w + x) * 4;
        imgData.data[idx] = val;
        imgData.data[idx + 1] = val;
        imgData.data[idx + 2] = Math.min(255, val + 20);
        imgData.data[idx + 3] = 255;
      }
    }

    const tempCanvas = document.createElement("canvas");
    tempCanvas.width = w;
    tempCanvas.height = h;
    tempCanvas.getContext("2d").putImageData(imgData, 0, 0);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();

    ctx.translate(state.panX, state.panY);
    ctx.scale(state.zoom, state.zoom);

    ctx.drawImage(tempCanvas, 0, 0, canvas.width, canvas.height);

    const scaleX = canvas.width / (state.orig_width || canvas.width);
    const scaleY = canvas.height / (state.orig_height || canvas.height);

    (state.current_points || []).forEach((pt, idx) => {
      const cx = pt.x * scaleX;
      const cy = pt.y * scaleY;

      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1.5 / state.zoom;
      ctx.beginPath();
      ctx.arc(cx, cy, 9 / state.zoom, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = "#38bdf8";
      ctx.font = `${10 / state.zoom}px monospace`;
      const labelText = pt.name || `#${idx + 1}`;
      ctx.fillText(labelText, cx + (11 / state.zoom), cy + (3 / state.zoom));
    });

    ctx.restore();
  }

  canvas.onclick = (e) => {
    if (state.total_fits === 0) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = (e.clientX - rect.left) * (canvas.width / rect.width);
    const clickY = (e.clientY - rect.top) * (canvas.height / rect.height);

    const imgCanvasX = (clickX - state.panX) / state.zoom;
    const imgCanvasY = (clickY - state.panY) / state.zoom;

    const ratioX = (state.orig_width || canvas.width) / canvas.width;
    const ratioY = (state.orig_height || canvas.height) / canvas.height;

    const x = Math.round(imgCanvasX * ratioX);
    const y = Math.round(imgCanvasY * ratioY);

    const scaleX = canvas.width / (state.orig_width || canvas.width);
    const scaleY = canvas.height / (state.orig_height || canvas.height);

    const clickedPoint = (state.current_points || []).find(p => {
      const px = p.x * scaleX;
      const py = p.y * scaleY;
      return Math.hypot(px - imgCanvasX, py - imgCanvasY) <= (12 / state.zoom);
    });

    if (clickedPoint) {
      callAction("toggle_point", { index: state.current_index, x: clickedPoint.x, y: clickedPoint.y });
    } else {
      showModal(`obj${(state.current_points || []).length + 1}`, (name) => {
        if (name !== null) {
          const nameExists = (state.current_points || []).some(
            p => p.name && p.name.toLowerCase() === name.toLowerCase()
          );
          if (nameExists) {
            log(`Hata: "${name}" ismi bu karede zaten kullanılıyor!`, true);
            return;
          }

          callAction("toggle_point", { index: state.current_index, x: clickedPoint ? clickedPoint.x : x, y: clickedPoint ? clickedPoint.y : y, name: name });
        }
      });
    }
  };

  container.querySelector("#sx-prev").onclick = () => {
    if (state.current_index > 0) callAction("get_frame", { index: state.current_index - 1 });
  };
  container.querySelector("#sx-next").onclick = () => {
    if (state.current_index < state.total_fits - 1) callAction("get_frame", { index: state.current_index + 1 });
  };

  container.querySelector("#sx-clear").onclick = () => {
    callAction("clear_selections", { index: state.current_index });
  };

  window.addEventListener("keydown", (e) => {
    if (!document.body.contains(canvas)) return;
    if (e.key === "ArrowLeft" && state.current_index > 0) {
      callAction("get_frame", { index: state.current_index - 1 });
    } else if (e.key === "ArrowRight" && state.current_index < state.total_fits - 1) {
      callAction("get_frame", { index: state.current_index + 1 });
    }
  });

  fetchDownloadedFolders();
}