
export function mount(container, plugin, api, log) {

  const $ = (tag, props = {}, ...children) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children);
    return node;
  };

  const wrapper = $("div");
  wrapper.style.cssText =
    "display:flex;flex-direction:column;gap:12px;padding:6px;min-width:0;";

  const title = $("div", {
    textContent: "Heliocentric Orbit Viewer"
  });
  title.style.cssText = "font-size:16px;font-weight:700;";

  const folderLabel = $("label", {
    textContent: "Observation folder"
  });

  const folderSelect = $("select");

  const objectLabel = $("label", {
    textContent: "Solar System object"
  });

  const objectSelect = $("select");

  const spanLabel = $("label", {
    textContent: "Time span around observation date"
  });

  const spanSelect = $("select");

  spanSelect.innerHTML = `
    <option value="180">± 180 days</option>
    <option value="365" selected>± 1 year</option>
    <option value="1825">± 5 years</option>
    <option value="3650">± 10 years</option>
  `;

  for (const el of [folderSelect, objectSelect, spanSelect]) {
    el.style.cssText =
      "width:100%;padding:8px;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:5px;";
  }

  const button = $("button", {
    textContent: "Calculate Orbit"
  });

  button.className = "btn primary";
  button.style.cssText = "padding:9px 12px;align-self:flex-start;";

  const status = $("div", {
    textContent: "Loading folders..."
  });

  status.style.cssText =
    "font-size:12px;color:var(--muted);";

  const plot = $("div");

  plot.style.cssText =
    "width:100%;height:560px;min-height:420px;border:1px solid var(--line);border-radius:8px;overflow:hidden;";

  const info = $("div");

  info.style.cssText =
    "font-size:12px;line-height:1.7;color:var(--text);";

  wrapper.append(
    title,
    folderLabel,
    folderSelect,
    objectLabel,
    objectSelect,
    spanLabel,
    spanSelect,
    button,
    status,
    plot,
    info
  );

  container.append(wrapper);

  // --------------------------------------------------
  // API
  // --------------------------------------------------

  const endpoint = action =>
    `/api/plugins/${encodeURIComponent(plugin.id)}/actions/${action}`;

  async function call(action, payload = {}) {

    const response = await api(endpoint(action), {
      method: "POST",
      body: JSON.stringify(payload)
    });

    if (response?.error) {
      throw new Error(response.error);
    }

    const result = response?.result ?? response;

    if (!result || typeof result !== "object") {
      throw new Error("Invalid API response.");
    }

    return result;
  }

  // --------------------------------------------------
  // HELPERS
  // --------------------------------------------------

  function formatNumber(value, digits = 6) {

    const number = Number(value);

    if (!Number.isFinite(number)) {
      return "N/A";
    }

    return number.toFixed(digits);
  }

  function loadPlotly() {

    if (window.Plotly) {
      return Promise.resolve();
    }

    if (window.__astroforgePlotlyPromise) {
      return window.__astroforgePlotlyPromise;
    }

    window.__astroforgePlotlyPromise = new Promise(
      (resolve, reject) => {

        const script = document.createElement("script");

        script.src =
          "https://cdn.plot.ly/plotly-2.35.2.min.js";

        script.onload = resolve;

        script.onerror = () => {
          window.__astroforgePlotlyPromise = null;
          reject(new Error("Plotly CDN could not be loaded."));
        };

        document.head.appendChild(script);
      }
    );

    return window.__astroforgePlotlyPromise;
  }

  // --------------------------------------------------
  // LOAD OBJECTS
  // --------------------------------------------------

  async function loadObjects() {

    objectSelect.innerHTML = "";

    const folder = folderSelect.value;

    if (!folder) return;

    status.textContent = "Reading labels.json...";

    const result = await call(
      "list_orbit_objects",
      { folder }
    );

    const objects = result.objects || [];

    if (!objects.length) {

      objectSelect.append(
        $("option", {
          value: "",
          textContent: "No labelled objects"
        })
      );

      status.textContent =
        "No named objects found in labels.json.";

      return;
    }

    for (const obj of objects) {

      objectSelect.append(
        $("option", {
          value: obj.name,
          textContent:
            `${obj.name} (${obj.observations} observation(s))`
        })
      );
    }

    status.textContent =
      `${objects.length} labelled object(s) found.`;
  }

  // --------------------------------------------------
  // LOAD FOLDERS
  // --------------------------------------------------

  async function loadFolders() {

    try {

      const result = await call("list_fits_folders");

      const folders = result.folders || [];

      folderSelect.innerHTML = "";

      for (const name of folders) {

        folderSelect.append(
          $("option", {
            value: name,
            textContent: name
          })
        );
      }

      if (!folders.length) {

        status.textContent =
          "No folders found in downloaded_fits.";

        return;
      }

      await loadObjects();

    } catch (error) {

      status.textContent =
        `Folder loading error: ${error.message}`;

      log?.(error.message, true);
    }
  }

  folderSelect.addEventListener("change", () => {

    loadObjects().catch(error => {

      status.textContent = error.message;

      log?.(error.message, true);
    });
  });

  // --------------------------------------------------
  // CALCULATE ORBIT
  // --------------------------------------------------

  button.addEventListener("click", async () => {

    const folder = folderSelect.value;
    const object_name = objectSelect.value;

    if (!folder || !object_name) {

      status.textContent =
        "Select a folder and an object first.";

      return;
    }

    button.disabled = true;

    status.textContent =
      "Querying JPL Horizons and building the orbit...";

    info.textContent = "";

    try {

      const result = await call(
        "calculate_orbit",
        {
          folder,
          object_name,
          span_days: Number(spanSelect.value),
          samples: 360
        }
      );

      const orbit = result.orbit;

      if (!orbit) {
        throw new Error("Orbit data is missing from API response.");
      }

      const t = orbit.trajectory;
      const current = orbit.reference_position;

      if (!t || !current) {
        throw new Error("Trajectory or reference position is missing.");
      }

      // Validate trajectory arrays.

      if (
        !Array.isArray(t.x) ||
        !Array.isArray(t.y) ||
        !Array.isArray(t.z) ||
        t.x.length === 0 ||
        t.x.length !== t.y.length ||
        t.x.length !== t.z.length
      ) {
        throw new Error("Invalid trajectory coordinates.");
      }

      const x = t.x.map(Number);
      const y = t.y.map(Number);
      const z = t.z.map(Number);

      if (
        !x.every(Number.isFinite) ||
        !y.every(Number.isFinite) ||
        !z.every(Number.isFinite)
      ) {
        throw new Error("Trajectory contains invalid coordinates.");
      }

      const cx = Number(current.x);
      const cy = Number(current.y);
      const cz = Number(current.z);

      if (![cx, cy, cz].every(Number.isFinite)) {
        throw new Error("Invalid reference position coordinates.");
      }

      // Calculate distance locally if Python did not provide it.

      const distance = Number.isFinite(Number(current.distance_au))
        ? Number(current.distance_au)
        : Math.sqrt(cx * cx + cy * cy + cz * cz);

      await loadPlotly();

      // --------------------------------------------------
      // ORBIT TRACE
      // --------------------------------------------------

      const trace = {

        type: "scatter3d",

        mode: "lines",

        name: `${orbit.object_name} orbit`,

        x,
        y,
        z,

        line: {
          width: 5
        },

        hovertemplate:
          "X: %{x:.5f} AU<br>" +
          "Y: %{y:.5f} AU<br>" +
          "Z: %{z:.5f} AU" +
          "<extra></extra>"
      };

      // --------------------------------------------------
      // SUN
      // --------------------------------------------------

      const sun = {

        type: "scatter3d",

        mode: "markers+text",

        name: "Sun",

        x: [0],
        y: [0],
        z: [0],

        text: ["Sun"],

        textposition: "top center",

        marker: {
          size: 8,
          color: "#ffb000",
          symbol: "circle"
        },

        hovertemplate:
          "Sun (0, 0, 0)<extra></extra>"
      };

      // --------------------------------------------------
      // REFERENCE POSITION
      // --------------------------------------------------

      const marker = {

        type: "scatter3d",

        mode: "markers+text",

        name: "Reference position",

        x: [cx],
        y: [cy],
        z: [cz],

        text: [orbit.object_name],

        textposition: "top center",

        marker: {
          size: 6,
          color: "#ff4d6d"
        },

        hovertemplate:
          `${orbit.object_name}<br>` +
          `Distance: ${formatNumber(distance)} AU` +
          "<br>X: %{x:.5f} AU" +
          "<br>Y: %{y:.5f} AU" +
          "<br>Z: %{z:.5f} AU" +
          "<extra></extra>"
      };

      // --------------------------------------------------
      // LAYOUT
      // --------------------------------------------------

      const layout = {

        title: {
          text:
            `${orbit.object_name} — heliocentric trajectory`,
          font: {
            color: "var(--text)"
          }
        },

        paper_bgcolor: "rgba(0,0,0,0)",

        plot_bgcolor: "rgba(0,0,0,0)",

        font: {
          color: "var(--text)"
        },

        margin: {
          l: 0,
          r: 0,
          t: 50,
          b: 0
        },

        legend: {
          orientation: "h",
          y: -0.08
        },

        scene: {

          bgcolor: "rgba(0,0,0,0)",

          xaxis: {
            title: "X (AU)",
            gridcolor: "rgba(128,128,128,.25)",
            zerolinecolor: "gray"
          },

          yaxis: {
            title: "Y (AU)",
            gridcolor: "rgba(128,128,128,.25)",
            zerolinecolor: "gray"
          },

          zaxis: {
            title: "Z (AU)",
            gridcolor: "rgba(128,128,128,.25)",
            zerolinecolor: "gray"
          },

          aspectmode: "data",

          camera: {
            projection: {
              type: "perspective"
            }
          }
        },

        hovermode: "closest"
      };

      // --------------------------------------------------
      // DRAW
      // --------------------------------------------------

      await window.Plotly.newPlot(
        plot,
        [trace, sun, marker],
        layout,
        {
          responsive: true,
          scrollZoom: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["toImage"]
        }
      );

      // --------------------------------------------------
      // INFORMATION
      // --------------------------------------------------

      info.innerHTML = `
        <b>Reference epoch:</b>
        ${orbit.center_utc || "N/A"} UTC<br>

        <b>Reference distance from Sun:</b>
        ${formatNumber(distance)} AU<br>

        <b>Time span:</b>
        ±${formatNumber(orbit.span_days, 0)} days<br>

        <b>Coordinate frame:</b>
        Heliocentric · <b>Units:</b> AU<br>

        <b>Matched FITS observations:</b>
        ${Array.isArray(orbit.observations)
          ? orbit.observations.length
          : 0}<br>

        <span style="color:var(--muted)">
          Drag to rotate · Scroll to zoom ·
          Use the Plotly toolbar to reset the view.
        </span>
      `;

      status.textContent =
        "Orbit loaded. Drag the 3D plot to explore it.";

      log?.(`Orbit calculated: ${orbit.object_name}`);

    } catch (error) {

      status.textContent =
        `Orbit calculation failed: ${error.message}`;

      info.textContent = "";

      log?.(error.message, true);

    } finally {

      button.disabled = false;
    }
  });

  loadFolders();
}
