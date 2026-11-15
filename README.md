# AstroForge

AstroForge is a local, browser-based scientific workspace for exploring NASA SPHEREx observations. It combines a lightweight Python plugin framework with a web interface for retrieving FITS observations, inspecting astronomical images, recording sky-coordinate selections, and exploring molecular spectral information using HITRAN reference data.

The application is designed to keep its scientific workflows modular: the core framework manages the local application and plugin lifecycle, while individual plugins provide the astronomy-focused tools.

## Key Features

### SPHEREx Observation Retrieval
- Search the SPHEREx DR1 collection through the IRSA Simple Image Access service.
- Specify a sky position using right ascension and declination, together with a search radius.
- Select an observation date range and one of the six SPHEREx spectral bands (B1–B6).
- Download matching FITS observations into a named local folder using concurrent workers.

### FITS Image Exploration
- Browse downloaded observation folders and move between FITS frames.
- Display astronomical image data in the browser.
- Select and label points directly on an image.
- Convert selected pixel positions into celestial coordinates using the image's WCS information.
- Export the selected-object labels and coordinate metadata to `labels.json`.

### Spectral WCS and Molecular Mapping
- Read SPHEREx FITS image data and its spectral WCS information.
- Generate pixel-level wavelength (`CWAVE`) and bandwidth (`CBAND`) maps and store them in a derived FITS file.
- Retrieve molecular transition data from HITRAN through HAPI.
- Evaluate HITRAN line strengths within the wavelength intervals represented by SPHEREx pixels.
- Generate molecular color maps alongside the corresponding SPHEREx image, with selectable molecular species.

The molecular maps visualize the correspondence between reference transition strengths and the wavelength intervals represented in the image. They provide a way to explore spectral coverage and molecular-line locations; the color overlays should not be interpreted on their own as confirmed molecular detections.

### FITS Header Inspection
- Inspect the primary header of a local FITS file.
- Review the file's HDU count and header metadata.

### Extensible Plugin Framework
- Discover and load plugins from their individual `plugin.json` manifests.
- Support functional, visual, and hybrid plugin types.
- Expose plugin actions through a local JSON API.
- Serve the main web interface and plugin-specific JavaScript assets from the same local application.

## Technology Stack

| Area | Technologies |
|---|---|
| Core application | Python, `http.server`, JSON |
| Web interface | HTML, CSS, JavaScript |
| Astronomical data | Astropy, Astroquery, FITS, WCS |
| Numerical processing | NumPy |
| Scientific visualization | Matplotlib |
| Molecular reference data | HITRAN / HAPI |
| TLS certificate integration | truststore |

## Project Structure

```text
astroforge_spherex_starter/
├── downloaded_fits/                 # Example and downloaded SPHEREx FITS observations
│   ├── barnardStar/
│   ├── epsilon_Indi_B/
│   ├── rw_aurigae/
│   ├── r_draconis/
│   └── wise_0855/
│
└── spherex_extensible_framework/
    ├── astroforge/
    │   ├── core/                    # Application, plugin lifecycle, events, config, logging
    │   ├── plugins/
    │   │   ├── display/             # SPHEREx FITS image explorer and coordinate selection
    │   │   ├── download_obs/        # IRSA query and FITS download
    │   │   ├── fits_inspector/      # FITS header inspection
    │   │   ├── moleculer/           # Spectral WCS and HITRAN molecular mapping
    │   │   └── orbit_calculator/    # Observation-label based coordinate analysis
    │   └── web/                     # Main browser interface
    ├── config.json                 # Local server configuration
    ├── data/                       # Application data directory
    ├── run.py                      # Application entry point
    ├── hitran_database/            # Local HITRAN/HAPI database
    ├── logs/                       # Runtime logs
    ├── spectral_analysis/           # Spectral analysis output directory
    └── wcs_files/                   # Generated spectral WCS FITS files
```

## Requirements

- Python 3.10 or newer
- Internet access for querying IRSA, downloading SPHEREx observations, and retrieving HITRAN reference data

Install the Python dependencies:

```bash
python -m pip install numpy matplotlib astropy astroquery hitran-api truststore
```

## Installation and Launch

1. Download or clone the project.
2. Open a terminal in the `spherex_extensible_framework` directory.
3. Install the dependencies listed above.
4. Start AstroForge:

```bash
python run.py
```

5. Open the local application in your browser:

```text
http://127.0.0.1:8763
```

The host and port are configured in `config.json`:

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8763
  }
}
```

AstroForge binds to the local loopback interface, so the application is intended to be accessed from the same computer.

## Typical Workflow

1. **Retrieve observations:** Open the SPHEREx download tool, enter the target coordinates and search radius, choose a date range and spectral band, and provide an output folder name.
2. **Explore FITS frames:** Open the FITS explorer and load an observation folder. Browse the available frames and select points of interest on the images.
3. **Save coordinate labels:** Assign names to selected points and export the selections to `labels.json`.
4. **Build spectral WCS maps:** In the spectral analyzer, select an observation and generate its pixel-level wavelength and bandwidth maps.
5. **Explore molecular transitions:** Choose molecular species and generate a color-coded map based on HITRAN transition strengths in the pixel wavelength intervals.
6. **Inspect FITS metadata:** Use the FITS header inspector when you need to review the metadata stored in a local FITS file.

## SPHEREx Spectral Bands

The application uses the following wavelength intervals for its band selection and molecular-line analysis:

| Band | Wavelength Range (µm) | Resolving Power |
|---|---:|---:|
| B1 | 0.75–1.09 | 39 |
| B2 | 1.10–1.62 | 41 |
| B3 | 1.63–2.41 | 41 |
| B4 | 2.42–3.82 | 35 |
| B5 | 3.83–4.41 | 112 |
| B6 | 4.42–5.00 | 128 |

## Plugin Architecture

Each plugin resides in its own directory under `astroforge/plugins/` and is described by a `plugin.json` manifest. The manifest identifies the plugin, its type, and its Python entry point.

The framework supports three plugin types:

- **Functional:** exposes backend actions.
- **Visual:** provides a browser-based view.
- **Hybrid:** combines backend actions with a custom view.

The plugin manager discovers manifests at startup, loads the corresponding Python classes, and makes their actions available through the local API. This structure allows new scientific tools to be added without placing their implementation inside the application core.

## Local API

The application provides a small JSON API for health checks, plugin discovery, and plugin actions:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Check whether the application is running |
| `GET` | `/api/plugins` | List discovered plugins and their available actions |
| `POST` | `/api/plugins/{plugin_id}/actions/{action_id}` | Execute a plugin action |

Plugin action requests use JSON request bodies.

## Data and Generated Files

- `downloaded_fits/` stores observation folders and FITS files.
- `labels.json` stores named image selections and their pixel/celestial coordinates.
- `wcs_files/` stores derived FITS files containing `CWAVE` and `CBAND` image extensions.
- `hitran_database/` stores the local molecular reference tables managed through HAPI.
- `logs/` stores application logs.

Keep downloaded observations and generated analysis data available when reopening a project session that depends on them.

## Acknowledgements

AstroForge builds on the public SPHEREx archive services provided through IRSA, astronomical data tools from the Astropy ecosystem, and molecular spectroscopic reference data from HITRAN.
