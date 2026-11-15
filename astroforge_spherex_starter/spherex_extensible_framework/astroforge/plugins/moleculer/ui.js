export function mount(container, plugin, api, log) {
  let state = {
    folders: [],
    total_fits: 0,
    fits_filenames: [],
    label_history: [],
    gallery: [], // Stores all generated matplotlib visuals
    currentIndex: 0
  };

  container.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:16px; position:relative; font-family:inherit; color:var(--text, #e9ebf0); max-width:960px; margin:0 auto;">
      
      <!-- TITLE -->
      <div style="font-size:16px; font-weight:700; color:#fff; border-bottom:1px solid var(--line); padding-bottom:8px; display:flex; align-items:center; gap:8px;">
        <span>🧪 SPHEREx HITRAN Molecular Analysis & Spectral Graphics Panel</span>
      </div>

      <!-- TOP VISUAL DISPLAY AREA WITH CAROUSEL & ARROWS -->
      <div style="background:var(--code); padding:16px; border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:650; font-size:13px; color:#38bdf8; border-bottom:1px solid var(--line); padding-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
          <span>📊 Matplotlib Visualization Gallery & Carousel</span>
          <span id="sx-gallery-counter" style="font-size:11.5px; color:var(--muted);">0 / 0</span>
        </div>

        <div style="display:flex; align-items:center; gap:10px; background:var(--bg); padding:14px; border-radius:6px; border:1px solid var(--line); min-height:220px; position:relative;">
          <!-- Left Arrow -->
          <button id="btn-prev-slide" class="btn primary" style="padding:10px 14px; font-size:16px; font-weight:bold; cursor:pointer; background:#1e293b; border:1px solid var(--line); color:#38bdf8; border-radius:4px;">◀</button>
          
          <!-- Image Display Container -->
          <div id="sx-graphics-container" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; text-align:center;">
            <span style="color:var(--muted); font-size:12px;">No visuals generated yet. Load a folder and generate maps below.</span>
          </div>

          <!-- Right Arrow -->
          <button id="btn-next-slide" class="btn primary" style="padding:10px 14px; font-size:16px; font-weight:bold; cursor:pointer; background:#1e293b; border:1px solid var(--line); color:#38bdf8; border-radius:4px;">▶</button>
        </div>

        <!-- Quick Selector Dropdown for all generated plots -->
        <div style="display:flex; gap:8px; align-items:center;">
          <label style="font-size:11.5px; color:var(--muted);">Select Visual:</label>
          <select id="inp-gallery-select" style="flex:1; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; font-size:11.5px;">
            <option value="">No visuals available</option>
          </select>
        </div>
      </div>

      <!-- 1. List Downloaded Folders Card -->
      <div style="background:var(--code); padding:14px; border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:650; font-size:12.5px; color:#fff;">List Downloaded Folders</div>
        <button id="btn-list-folders" class="btn primary" style="width:100%; padding:8px; font-weight:600;">List Downloaded Folders</button>
        <div id="res-list-folders" style="font-family:monospace; font-size:11px; color:#38bdf8; background:var(--bg); padding:8px; border-radius:4px; display:none;"></div>
      </div>

      <!-- 2. Load Selected Folder Card -->
      <div style="background:var(--code); padding:14px; border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:650; font-size:12.5px; color:#fff;">Load Selected Folder</div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <label style="font-size:11.5px; color:var(--muted);">Observation Folder</label>
          <select id="inp-folder-name" style="background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; font-size:11.5px;">
            <option value="">Please list folders first</option>
          </select>
        </div>
        <button id="btn-load-folder" class="btn primary" style="width:100%; padding:8px; font-weight:600;">Load Selected Folder & Auto-Generate All Maps</button>
      </div>

      <!-- 3. Build Spectral WCS Card -->
      <div style="background:var(--code); padding:14px; border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:650; font-size:12.5px; color:#fff;">Build Spectral WCS</div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <label style="font-size:11.5px; color:var(--muted);">filename</label>
          <select id="inp-wcs-filename" style="background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; font-size:11.5px;">
            <option value="">Please load an observation folder first</option>
          </select>
        </div>
        <button id="btn-build-wcs" class="btn primary" style="width:100%; padding:8px; font-weight:600;">Build Spectral WCS</button>
      </div>

      <!-- 4. Generate Molecular Color Map Card -->
      <div style="background:var(--code); padding:14px; border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:650; font-size:12.5px; color:#fff;">Generate Molecular Color Map</div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <label style="font-size:11.5px; color:var(--muted);">filename</label>
          <select id="inp-map-filename" style="background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; font-size:11.5px;">
            <option value="">Please load an observation folder first</option>
          </select>
        </div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <label style="font-size:11.5px; color:var(--muted);">molecules (Select)</label>
          <div style="display:flex; gap:14px; background:var(--bg); padding:8px 10px; border-radius:6px; border:1px solid var(--line);" id="inp-molecules-checkboxes">
            <label style="font-size:11.5px; cursor:pointer;"><input type="checkbox" value="H2O" checked> H2O</label>
            <label style="font-size:11.5px; cursor:pointer;"><input type="checkbox" value="CO2" checked> CO2</label>
            <label style="font-size:11.5px; cursor:pointer;"><input type="checkbox" value="CO" checked> CO</label>
            <label style="font-size:11.5px; cursor:pointer;"><input type="checkbox" value="CH4" checked> CH4</label>
            <label style="font-size:11.5px; cursor:pointer;"><input type="checkbox" value="N2O" checked> N2O</label>
          </div>
        </div>
        <button id="btn-gen-map" class="btn primary" style="width:100%; padding:8px; font-weight:600;">Generate Molecular Color Map</button>
      </div>

      <!-- 5. Extract Observed Spectrum Card -->
      <div style="background:var(--code); padding:14px; border:1px solid var(--line); border-radius:8px; display:flex; flex-direction:column; gap:10px;">
        <div style="font-weight:650; font-size:12.5px; color:#fff;">Extract Observed Spectrum</div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <label style="font-size:11.5px; color:var(--muted);">object</label>
          <select id="inp-spec-object" style="background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; font-size:11.5px;">
            <option value="">No labeled objects found</option>
          </select>
        </div>
        <div style="display:flex; flex-direction:column; gap:4px;">
          <label style="font-size:11.5px; color:var(--muted);">radius_arcsec</label>
          <input type="number" id="inp-radius" value="3.0" step="0.5" style="background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; font-size:11.5px;">
        </div>
        <button id="btn-extract-spec" class="btn primary" style="width:100%; padding:8px; font-weight:600;">Extract Observed Spectrum</button>
      </div>

    </div>
  `;

  const graphicsContainer = container.querySelector("#sx-graphics-container");
  const counterSpan = container.querySelector("#sx-gallery-counter");
  const gallerySelect = container.querySelector("#inp-gallery-select");

  async function callAction(actionId, payload = {}) {
    try {
      const res = await api(`/api/plugins/${encodeURIComponent(plugin.id)}/actions/${actionId}`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
      return res.result;
    } catch (e) {
      console.error(e);
      log(`Action "${actionId}" failed: ${e.message}`, true);
      return null;
    }
  }

  function renderGallery() {
    if (state.gallery.length === 0) {
      graphicsContainer.innerHTML = `<span style="color:var(--muted); font-size:12px;">No visuals generated yet. Load a folder and generate maps below.</span>`;
      counterSpan.textContent = "0 / 0";
      gallerySelect.innerHTML = `<option value="">No visuals available</option>`;
      return;
    }

    if (state.currentIndex < 0) state.currentIndex = 0;
    if (state.currentIndex >= state.gallery.length) state.currentIndex = state.gallery.length - 1;

    const currentItem = state.gallery[state.currentIndex];
    counterSpan.textContent = `${state.currentIndex + 1} / ${state.gallery.length}`;

    graphicsContainer.innerHTML = `
      <div style="font-weight:600; font-size:12px; color:#38bdf8;">${currentItem.title}</div>
      <img src="data:image/png;base64,${currentItem.image}" style="max-width:100%; max-height:480px; border-radius:4px; border:1px solid var(--line);">
    `;

    gallerySelect.innerHTML = state.gallery.map((item, idx) => `
      <option value="${idx}" ${idx === state.currentIndex ? 'selected' : ''}>[${idx + 1}] ${item.title}</option>
    `).join("");
  }

  function addGraphic(title, base64Img) {
    state.gallery.push({ title, image: base64Img });
    state.currentIndex = state.gallery.length - 1;
    renderGallery();
  }

  // Navigation Arrows
  container.querySelector("#btn-prev-slide").onclick = () => {
    if (state.gallery.length === 0) return;
    state.currentIndex = (state.currentIndex - 1 + state.gallery.length) % state.gallery.length;
    renderGallery();
  };

  container.querySelector("#btn-next-slide").onclick = () => {
    if (state.gallery.length === 0) return;
    state.currentIndex = (state.currentIndex + 1) % state.gallery.length;
    renderGallery();
  };

  gallerySelect.onchange = (e) => {
    const idx = parseInt(e.target.value);
    if (!isNaN(idx)) {
      state.currentIndex = idx;
      renderGallery();
    }
  };

  // 1. List Folders
  container.querySelector("#btn-list-folders").onclick = async () => {
    log("Listing observation folders...");
    const res = await callAction("list_downloaded_folders");
    if (res && res.folders) {
      state.folders = res.folders;
      const folderSelect = container.querySelector("#inp-folder-name");
      folderSelect.innerHTML = state.folders.map(f => `<option value="${f}">${f}</option>`).join("");
      
      const resDiv = container.querySelector("#res-list-folders");
      resDiv.style.display = "block";
      resDiv.textContent = JSON.stringify(res, null, 2);
      log("Folders listed successfully.");
    }
  };

  // 2. Load Folder & Auto-Generate All Maps in Background
  container.querySelector("#btn-load-folder").onclick = async () => {
    const folderName = container.querySelector("#inp-folder-name").value;
    if (!folderName) { log("Please select a folder.", true); return; }
    log(`Loading folder: ${folderName}`);
    const res = await callAction("select_folder", { folder_name: folderName });
    if (res) {
      state.fits_filenames = res.fits_filenames || [];
      state.label_history = res.label_history || [];

      const wcsSelect = container.querySelector("#inp-wcs-filename");
      const mapSelect = container.querySelector("#inp-map-filename");
      const fileOptions = state.fits_filenames.length > 0
        ? state.fits_filenames.map(f => `<option value="${f}">${f}</option>`).join("")
        : `<option value="">No FITS files found</option>`;
      
      wcsSelect.innerHTML = fileOptions;
      mapSelect.innerHTML = fileOptions;

      const objSelect = container.querySelector("#inp-spec-object");
      objSelect.innerHTML = state.label_history.length > 0 
        ? state.label_history.map(obj => `<option value="${obj}">${obj}</option>`).join("")
        : `<option value="">No labeled objects found</option>`;

      log(`Folder loaded: ${folderName}. Auto-generating all molecular maps in background...`);
      
      // Auto-generate all maps in background
      const batchRes = await callAction("generate_all_maps");
      if (batchRes && batchRes.results && batchRes.results.length > 0) {
        batchRes.results.forEach(item => {
          state.gallery.push(item);
        });
        state.currentIndex = 0;
        renderGallery();
        log(`Successfully generated ${batchRes.results.length} maps in background!`);
      }
    }
  };

  // 3. Build WCS
  container.querySelector("#btn-build-wcs").onclick = async () => {
    const filename = container.querySelector("#inp-wcs-filename").value;
    if (!filename) { log("Please select a FITS file.", true); return; }
    log(`Building spectral WCS: ${filename}`);
    const res = await callAction("create_wcs", { filename });
    if (res && res.success) {
      log(`WCS successfully built: ${filename}`);
    }
  };

  // 4. Generate Molecular Color Map
  container.querySelector("#btn-gen-map").onclick = async () => {
    const filename = container.querySelector("#inp-map-filename").value;
    if (!filename) { log("Please select a FITS file.", true); return; }
    const checkboxes = container.querySelectorAll("#inp-molecules-checkboxes input:checked");
    const molecules = Array.from(checkboxes).map(cb => cb.value);
    if (molecules.length === 0) { log("You must select at least one molecule.", true); return; }

    log("Generating molecular color map...");
    const res = await callAction("create_color_map", { filename, molecules });
    if (res && res.image) {
      addGraphic(`Molecular Map (${res.band}) - ${filename}`, res.image);
      log("Molecular color map added to gallery.");
    }
  };

  // 5. Extract Spectrum
  container.querySelector("#btn-extract-spec").onclick = async () => {
    const obj = container.querySelector("#inp-spec-object").value;
    if (!obj) { log("Please select a target object.", true); return; }
    const radius_arcsec = parseFloat(container.querySelector("#inp-radius").value) || 3.0;

    log(`Extracting spectrum for '${obj}'...`);
    const res = await callAction("extract_spectrum", { object: obj, radius_arcsec });
    if (res && res.image) {
      addGraphic(`${obj} Spectrum (${res.points} points)`, res.image);
      log(`Spectrum graph added to gallery: ${obj}`);
    }
  };
}