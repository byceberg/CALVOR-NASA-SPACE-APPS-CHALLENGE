import base64
import io
import json
import pathlib
import threading

import numpy as np
import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from astropy.io import fits
from astropy.wcs import WCS
import astropy.units as u

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

try:
    import hapi
    HAPI_IMPORT_ERROR = None
except Exception as _exc:
    hapi = None
    HAPI_IMPORT_ERROR = _exc

from astroforge.core.plugin import BasePlugin

DB_NAME = "hitran_database"
FITS_SUFFIXES = (".fits", ".fit", ".fts", ".FITS", ".FIT", ".FTS")

BANDS = {
    "B1": (0.75, 1.09, 39),
    "B2": (1.10, 1.62, 41),
    "B3": (1.63, 2.41, 41),
    "B4": (2.42, 3.82, 35),
    "B5": (3.83, 4.41, 112),
    "B6": (4.42, 5.00, 128),
}


class HitranDatabaseManager:
    def __init__(self, db_dir):
        self.db_dir = pathlib.Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        try:
            hapi.db_begin(str(self.db_dir))
        except Exception:
            pass

    def fetch_molecule_table(self, name, molecule_id, isotopologue_id, start_wavenumber, end_wavenumber) -> dict:
        if name not in hapi.tableList():
            hapi.fetch(name, molecule_id, isotopologue_id, start_wavenumber, end_wavenumber)

        wavenumbers = hapi.getColumn(name, "nu")
        intensities = hapi.getColumn(name, "sw")
        einstein_a = hapi.getColumn(name, "a")

        air_width = hapi.getColumn(name, "gamma_air")
        self_width = hapi.getColumn(name, "gamma_self")

        lower_energy = hapi.getColumn(name, "elower")
        temprature_exponent = hapi.getColumn(name, "n_air")
        pressure_shift = hapi.getColumn(name, "delta_air")

        wavenumbers = np.asarray(wavenumbers, dtype=float)
        wavelengths = 10**4 / wavenumbers

        return {
            name: {
                "wavelength": wavelengths.tolist(),
                "nu": wavenumbers.tolist(),
                "sw": intensities,
                "a": einstein_a,
                "gamma_air": air_width,
                "gamma_self": self_width,
                "elower": lower_energy,
                "n_air": temprature_exponent,
                "delta_air": pressure_shift
            }
        }


class MoleculeAnalyzer:
    def __init__(self, db_dir, fits_fetcher_object=None):
        self.db_manager = HitranDatabaseManager(db_dir)
        self.fits_fetcher_object = fits_fetcher_object or FitsFetcher()

    def convert_length_to_number(self, length):
        return (10 ** 4) / length

    def band_wavenumber_range(self, band):
        lower, upper, res = self.fits_fetcher_object.bands[band]
        return self.convert_length_to_number(upper), self.convert_length_to_number(lower)


class FitsFetcher:
    def __init__(self):
        self.band = None
        self.bands = BANDS

    def _spectral_wcs(self, hdul):
        try:
            return WCS(hdul["IMAGE"].header, fobj=hdul, key="W")
        except Exception:
            try:
                return WCS(hdul["IMAGE"].header, fobj=hdul)
            except Exception:
                return WCS(hdul["IMAGE"].header)

    @staticmethod
    def _as_um(values):
        arr = values
        if hasattr(values, "unit"):
            try:
                arr = values.to(u.um, equivalencies=u.spectral()).value
            except Exception:
                arr = values.value
        return np.asarray(arr, dtype=np.float64)

    def wcs_file_path(self, fits_path, output_dir):
        fits_path = pathlib.Path(fits_path)
        return pathlib.Path(output_dir) / f"{fits_path.stem}_wcs.fits"

    def build_spectral_wcs_file(self, fits_path, output_dir="wcs_files", overwrite=False, chunk_rows=256):
        fits_path = pathlib.Path(fits_path)
        out_path = self.wcs_file_path(fits_path, output_dir)

        if out_path.exists() and not overwrite:
            return out_path

        out_path.parent.mkdir(parents=True, exist_ok=True)

        with fits.open(fits_path, memmap=False) as hdul:
            hdu_target = None
            for h in hdul:
                if h.data is not None and getattr(h.data, "ndim", 0) >= 2:
                    hdu_target = h
                    break
            if hdu_target is None:
                hdu_target = hdul[0]

            try:
                spec_wcs = self._spectral_wcs(hdul)
            except Exception:
                spec_wcs = WCS(hdu_target.header)

            ny, nx = hdu_target.data.shape[-2], hdu_target.data.shape[-1]
            obs_id = hdul[0].header.get("OBSID")

            cwave = np.full((ny, nx), np.nan, dtype=np.float64)
            cband = np.full((ny, nx), np.nan, dtype=np.float64)

            try:
                for y0 in range(0, ny, chunk_rows):
                    y1 = min(y0 + chunk_rows, ny)
                    yy, xx = np.mgrid[y0:y1, 0:nx]
                    result = spec_wcs.pixel_to_world(xx, yy)
                    if isinstance(result, (tuple, list)) and len(result) >= 2:
                        cwave[y0:y1] = self._as_um(result[0])
                        cband[y0:y1] = self._as_um(result[1])
            except Exception:
                pass

        for arr in (cwave, cband):
            if np.isfinite(arr).any() and np.nanmedian(np.abs(arr)) < 1e-3:
                arr *= 1e6

        if not np.isfinite(cwave).any():
            cwave.fill(1.25)
            cband.fill(0.1)

        primary = fits.PrimaryHDU()
        primary.header["SOURCE"] = fits_path.name
        if obs_id:
            primary.header["OBSID"] = obs_id

        hdu_w = fits.ImageHDU(cwave.astype(np.float32), name="CWAVE")
        hdu_w.header["BUNIT"] = "um"
        hdu_b = fits.ImageHDU(cband.astype(np.float32), name="CBAND")
        hdu_b.header["BUNIT"] = "um"

        fits.HDUList([primary, hdu_w, hdu_b]).writeto(out_path, overwrite=True)
        return out_path

    def load_spherex_data(self, image_path, spectral_wcs_path):
        image_path = pathlib.Path(image_path)
        spectral_wcs_path = pathlib.Path(spectral_wcs_path)

        with fits.open(image_path, memmap=False) as hdul:
            hdu_target = None
            for h in hdul:
                if h.data is not None and getattr(h.data, "ndim", 0) >= 2:
                    hdu_target = h
                    break
            if hdu_target is None:
                hdu_target = hdul[0]

            image = np.asarray(hdu_target.data, dtype=np.float32).copy()
            while image.ndim > 2:
                image = image[0]

            try:
                flags = np.asarray(hdul["FLAGS"].data, dtype=np.float32).copy()
                while flags.ndim > 2:
                    flags = flags[0]
            except Exception:
                flags = np.zeros_like(image)

            try:
                variance = np.asarray(hdul["VARIANCE"].data, dtype=np.float32).copy()
                while variance.ndim > 2:
                    variance = variance[0]
            except Exception:
                variance = np.ones_like(image)

            image_wcs = WCS(hdu_target.header).celestial
            metadata = {
                "observation_id": hdul[0].header.get("OBSID"),
                "image_shape": image.shape,
                "image_unit": hdu_target.header.get("BUNIT", "count"),
                "image_path": str(image_path)
            }

        with fits.open(spectral_wcs_path, memmap=False) as wcs_hdul:
            cwave = np.asarray(wcs_hdul["CWAVE"].data, dtype=np.float32).copy()
            cband = np.asarray(wcs_hdul["CBAND"].data, dtype=np.float32).copy()

        return {
            "image": image,
            "flags": flags,
            "variance": variance,
            "cwave": cwave,
            "cband": cband,
            "wcs": image_wcs,
            "metadata": metadata
        }

    def identify_band_from_wavelength(self, median_wl):
        if median_wl is None or not np.isfinite(median_wl):
            return "B1"
        for band, (lower, higher, _) in self.bands.items():
            if lower <= median_wl <= higher:
                return band
        return "B1"


class MolecularColorMapper:
    DEFAULT_MOLECULES = {
        "H2O": (1, 1, (0.15, 0.45, 1.00)),
        "CO2": (2, 1, (1.00, 0.20, 0.20)),
        "CO":  (5, 1, (0.20, 0.85, 0.30)),
        "CH4": (6, 1, (1.00, 0.80, 0.10)),
        "N2O": (4, 1, (0.85, 0.30, 0.95)),
    }

    def __init__(self, fetcher, molecule_analyzer, molecules=None):
        self.fetcher = fetcher
        self.molecule_analyzer = molecule_analyzer
        self.molecules = dict(molecules or self.DEFAULT_MOLECULES)
        self.line_lists = {}

    def load_line_lists(self, band, names):
        s_wn, e_wn = self.molecule_analyzer.band_wavenumber_range(band)
        loaded = []

        for mol in names:
            if (band, mol) in self.line_lists:
                loaded.append(mol)
                continue

            mol_id, iso_id, _ = self.molecules[mol]
            table_name = f"{mol}_{band}"

            try:
                data = self.molecule_analyzer.db_manager.fetch_molecule_table(table_name, mol_id, iso_id, s_wn, e_wn)
                table = data[table_name]
                wl = np.asarray(table["wavelength"], dtype=float)
                sw = np.asarray(table["sw"], dtype=float)
                ok = np.isfinite(wl) & np.isfinite(sw) & (wl > 0) & (sw > 0)
                wl, sw = wl[ok], sw[ok]

                if wl.size == 0:
                    continue

                order = np.argsort(wl)
                wl, sw = wl[order], sw[order]
                self.line_lists[(band, mol)] = {"wl": wl, "cum": np.concatenate([[0.0], np.cumsum(sw)])}
                loaded.append(mol)
            except Exception:
                pass

        return loaded

    def line_strength_map(self, band, mol, cwave, cband):
        ll = self.line_lists[(band, mol)]
        resolution = self.fetcher.bands[band][2]

        valid = np.isfinite(cwave) & (cwave > 0)
        width = np.where(np.isfinite(cband) & (cband > 0), cband, cwave / resolution)
        lo = np.where(valid, cwave - width / 2, 0.0)
        hi = np.where(valid, cwave + width / 2, 0.0)

        i0 = np.searchsorted(ll["wl"], lo, side="left")
        i1 = np.searchsorted(ll["wl"], hi, side="right")

        score = (ll["cum"][i1] - ll["cum"][i0]) / np.where(valid, width, 1.0)
        score[~valid] = 0.0
        return score.astype(np.float32)

    @staticmethod
    def normalize_scores(raw, mode="per_molecule"):
        logs = {}
        for mol, sc in raw.items():
            m = sc > 0
            lg = np.full(sc.shape, np.nan, dtype=np.float32)
            if m.any():
                lg[m] = np.log10(sc[m])
            logs[mol] = lg

        if mode == "global":
            allvals = np.concatenate([lg[np.isfinite(lg)] for lg in logs.values() if np.isfinite(lg).any()])
            glob = np.percentile(allvals, [5, 99]) if allvals.size else (0.0, 1.0)

        out = {}
        for mol, lg in logs.items():
            m = np.isfinite(lg)
            n = np.zeros(lg.shape, dtype=np.float32)
            if m.any():
                lo, hi = glob if mode == "global" else np.percentile(lg[m], [5, 99])
                n[m] = np.clip((lg[m] - lo) / (hi - lo + 1e-12), 0, 1)
            out[mol] = n
        return out

    @staticmethod
    def brightness_map(image, valid):
        if valid.any() and np.isfinite(image[valid]).any():
            lo, hi = np.percentile(image[valid][np.isfinite(image[valid])], [1, 99.5])
        else:
            lo, hi = 0.0, 1.0
        b = np.clip((np.nan_to_num(image) - lo) / (hi - lo + 1e-12), 0, 1)
        b = np.arcsinh(10 * b) / np.arcsinh(10)
        b[~valid] = 0.0
        return b.astype(np.float32)

    def compose_rgb(self, norm_scores, brightness, sharpness=3.0):
        mols = list(norm_scores)
        if not mols:
            return np.stack([brightness, brightness, brightness], axis=-1)

        S = np.stack([norm_scores[m] for m in mols], axis=0)
        colors = np.array([self.molecules[m][2] for m in mols], dtype=np.float32)

        S = np.maximum(S, 0.25)
        W = S ** sharpness
        mix = np.einsum("mhw,mc->hwc", W, colors) / (W.sum(axis=0)[..., None] + 1e-9)
        strength = S.max(axis=0)[..., None]

        rgb = brightness[..., None] * ((0.2 * (1.0 - strength)) + (0.8 + 0.2 * strength) * mix)
        gray = np.stack([brightness, brightness, brightness], axis=-1)
        return np.clip(np.where(strength > 0, rgb, gray), 0, 1)


class SphereXSpectralAnalyzer(BasePlugin):
    def __init__(self, context=None):
        super().__init__(context)
        self.root = pathlib.Path(getattr(context, "root", pathlib.Path.cwd()))
        
        self.base_dir = (self.root.parent.parent / "downloaded_fits").resolve()
        if not self.base_dir.exists():
            alt_path = (pathlib.Path.home() / "Desktop" / "astroforge_spherex_starter" / "downloaded_fits").resolve()
            if alt_path.exists():
                self.base_dir = alt_path

        self.wcs_dir = self.root / "wcs_files"
        self.output_dir = self.root / "spectral_analysis"
        self.hitran_db = self.root / "hitran_database"

        self.fits_files = []
        self.selections = {}
        self.current_folder = None

        self.fetcher = FitsFetcher()
        self.molecule_analyzer = MoleculeAnalyzer(self.hitran_db, self.fetcher)
        self.color_mapper = MolecularColorMapper(self.fetcher, self.molecule_analyzer)

        self._lock = threading.RLock()

    def setup(self):
        for folder in (self.wcs_dir, self.output_dir, self.hitran_db):
            folder.mkdir(parents=True, exist_ok=True)
        return True

    def get_view(self):
        plugin_id = self.manifest.get("id", "spherex_spectral_analyzer")
        return {"type": "spherex_custom", "script": f"/plugin-ui/{plugin_id}/ui.js"}

    def get_actions(self):
        return [
            {"id": "list_downloaded_folders", "name": "List Downloaded Folders", "inputs": []},
            {
                "id": "select_folder",
                "name": "Load Selected Folder",
                "inputs": [{"id": "folder_name", "label": "Observation Folder", "type": "string"}]
            },
            {"id": "create_wcs", "name": "Build Spectral WCS", "inputs": [{"id": "filename", "type": "string"}]},
            {
                "id": "create_color_map",
                "name": "Generate Molecular Color Map",
                "inputs": [
                    {"id": "filename", "type": "string"},
                    {"id": "molecules", "type": "array"}
                ]
            },
            {
                "id": "extract_spectrum",
                "name": "Extract Observed Spectrum",
                "inputs": [
                    {"id": "object", "type": "string"},
                    {"id": "radius_arcsec", "type": "number", "default": 3.0}
                ]
            },
            {"id": "generate_all_maps", "name": "Generate All Maps in Background", "inputs": []}
        ]

    def execute(self, action_id, payload=None):
        payload = payload or {}
        with self._lock:
            if action_id == "list_downloaded_folders":
                return self._action_list_downloaded_folders()
            elif action_id == "select_folder":
                return self._action_select_folder(payload)
            elif action_id == "create_wcs":
                return self._action_create_wcs(payload)
            elif action_id == "create_color_map":
                return self._action_create_color_map(payload)
            elif action_id == "extract_spectrum":
                return self._action_extract_spectrum(payload)
            elif action_id == "generate_all_maps":
                return self._action_generate_all_maps()
            else:
                raise KeyError(f"Unknown action: {action_id}")

    def _action_list_downloaded_folders(self):
        subfolders = []
        if self.base_dir.exists() and self.base_dir.is_dir():
            for p in self.base_dir.iterdir():
                if p.is_dir():
                    subfolders.append(p.name)
        return {"folders": sorted(set(subfolders))}

    def _action_select_folder(self, payload):
        folder_name = payload.get("folder_name", "").strip()
        if not folder_name:
            folders = self._action_list_downloaded_folders().get("folders", [])
            if folders:
                folder_name = folders[0]
        
        target_dir = (self.base_dir / folder_name).resolve()
        self.current_folder = target_dir
        self.fits_files = []

        if target_dir.exists() and target_dir.is_dir():
            found_files = []
            for ext in FITS_SUFFIXES:
                found_files.extend(target_dir.glob(f"*{ext}"))
                found_files.extend(target_dir.glob(f"**/*{ext}"))
            self.fits_files = sorted(set(str(p) for p in found_files if p.is_file()))

        json_path = target_dir / "labels.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    self.selections = json.load(f)
            except Exception:
                self.selections = {}
        else:
            self.selections = {}

        return self._build_state_response()

    def _build_state_response(self):
        fits_names = [pathlib.Path(f).name for f in self.fits_files]
        all_labels = sorted(list(set(
            p.get("name", "") for pts in self.selections.values() for p in pts if isinstance(p, dict) and p.get("name")
        )))

        return {
            "total_fits": len(self.fits_files),
            "fits_filenames": fits_names,
            "label_history": all_labels
        }

    def _resolve_file(self, filename):
        if not filename and self.fits_files:
            return pathlib.Path(self.fits_files[0])
        for f in self.fits_files:
            if pathlib.Path(f).name == filename:
                return pathlib.Path(f)
        if filename:
            for ext in FITS_SUFFIXES:
                match = next(self.base_dir.glob(f"**/{filename}"), None)
                if match:
                    return match
        if self.fits_files:
            return pathlib.Path(self.fits_files[0])
        raise FileNotFoundError(f"File not found: {filename}")

    def _action_create_wcs(self, payload):
        filename = payload.get("filename")
        path = self._resolve_file(filename)
        out_path = self.fetcher.build_spectral_wcs_file(path, self.wcs_dir)
        return {"success": True, "path": str(out_path), "cached": True}

    def _action_create_color_map(self, payload):
        filename = payload.get("filename")
        raw_mols = payload.get("molecules")
        
        if isinstance(raw_mols, str):
            try:
                parsed = json.loads(raw_mols)
                molecules = parsed if isinstance(parsed, list) else [m.strip() for m in raw_mols.replace(",", " ").split() if m.strip()]
            except Exception:
                molecules = [m.strip() for m in raw_mols.replace(",", " ").split() if m.strip()]
        elif isinstance(raw_mols, list):
            molecules = raw_mols
        else:
            molecules = list(self.color_mapper.molecules.keys())

        path = self._resolve_file(filename)
        wcs_path = self.fetcher.build_spectral_wcs_file(path, self.wcs_dir)

        data = self.fetcher.load_spherex_data(path, wcs_path)
        image, cwave, cband = data["image"], data["cwave"], data["cband"]

        valid = (np.isfinite(image) & np.isfinite(cwave) & (cwave > 0))
        if not valid.any():
            valid = np.isfinite(image)

        valid_cwave = cwave[valid & np.isfinite(cwave)]
        median_wl = float(np.nanmedian(valid_cwave)) if valid_cwave.size > 0 else 1.25
        band = self.fetcher.identify_band_from_wavelength(median_wl)

        loaded = self.color_mapper.load_line_lists(band, molecules)
        raw = {m: self.color_mapper.line_strength_map(band, m, cwave, cband) for m in loaded}
        norm = self.color_mapper.normalize_scores(raw, "per_molecule")
        for m in norm:
            norm[m][~valid] = 0.0

        brightness = self.color_mapper.brightness_map(image, valid)
        rgb = self.color_mapper.compose_rgb(norm, brightness, sharpness=3.0)

        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        im0 = axes[0].imshow(brightness, cmap="inferno", origin="lower")
        axes[0].set_title(f"SPHEREx Image ({band}) - {path.name}", fontsize=10)
        fig.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04, label="Flux / Intensity (Norm)")

        axes[1].imshow(rgb, origin="lower")
        axes[1].set_title("Molecular Color Map (HITRAN Line Strength)", fontsize=10)
        axes[1].legend(
            handles=[Patch(color=self.color_mapper.molecules[m][2], label=m) for m in loaded],
            loc="upper right", framealpha=0.85
        )

        for ax in axes:
            ax.set_xlabel("x (pixel)", fontsize=9)
            ax.set_ylabel("y (pixel)", fontsize=9)
        fig.tight_layout()

        img_b64 = figure_to_base64(fig)
        plt.close(fig)

        return {"success": True, "image": img_b64, "band": band, "filename": path.name, "molecules": loaded}

    def _action_generate_all_maps(self):
        """Batch generates color maps for all loaded FITS files in the background."""
        results = []
        default_mols = list(self.color_mapper.molecules.keys())
        for fpath in self.fits_files:
            fname = pathlib.Path(fpath).name
            try:
                res = self._action_create_color_map({"filename": fname, "molecules": default_mols})
                if res and res.get("success"):
                    results.append({
                        "title": f"Molecular Map ({res.get('band', 'B1')}) - {fname}",
                        "image": res.get("image")
                    })
            except Exception as e:
                print(f"Error generating map for {fname}: {e}")
        return {"success": True, "results": results}

    def _action_extract_spectrum(self, payload):
        obj_name = payload.get("object")
        radius_arcsec = _num(payload.get("radius_arcsec", 3.0)) or 3.0
        rows = []

        if not self.selections and self.current_folder and (self.current_folder / "labels.json").exists():
            try:
                with open(self.current_folder / "labels.json", "r", encoding="utf-8") as f:
                    self.selections = json.load(f)
            except Exception:
                pass

        for filepath in self.fits_files:
            fname = pathlib.Path(filepath).name
            pts = self.selections.get(fname, [])
            target = next((p for p in pts if isinstance(p, dict) and p.get("name") == obj_name), None)
            if not target:
                continue
            try:
                wcs_path = self.fetcher.build_spectral_wcs_file(filepath, self.wcs_dir)
                data = self.fetcher.load_spherex_data(filepath, wcs_path)
                image = data["image"]

                x, y = int(target["x"]), int(target["y"])
                r = int(radius_arcsec) + 1
                y0, y1 = max(0, y - r), min(image.shape[0], y + r + 1)
                x0, x1 = max(0, x - r), min(image.shape[1], x + r + 1)
                patch = image[y0:y1, x0:x1]
                if patch.size > 0:
                    flux = float(np.nanmean(patch))
                    rows.append({
                        "filename": fname,
                        "flux": flux,
                        "wavelength": 1.25,
                        "ra": target.get("ra", 0.0),
                        "dec": target.get("dec", 0.0)
                    })
            except Exception:
                pass

        fig = Figure(figsize=(9, 4.5))
        ax = fig.subplots()
        if rows:
            fluxes = [r["flux"] for r in rows]
            ax.plot(range(len(fluxes)), fluxes, marker="o", color="#38bdf8", lw=2)
            ax.set_title(f"Extracted Spectrum for {obj_name} ({len(rows)} frames)", fontsize=10, color="#fff")
            ax.set_xlabel("Frame Index", fontsize=9)
            ax.set_ylabel("Flux", fontsize=9)
            ax.grid(True, linestyle="--", alpha=0.3)
        else:
            ax.text(0.5, 0.5, f"No matching points found for '{obj_name}'", color="white", ha="center", va="center")
            ax.set_title(f"Extracted Spectrum for {obj_name}", fontsize=10, color="#fff")
        fig.tight_layout()

        img_b64 = figure_to_base64(fig)
        plt.close(fig)

        return {
            "success": True,
            "object": obj_name,
            "points": len(rows),
            "rows": rows,
            "image": img_b64
        }


def figure_to_base64(fig, dpi=110, tight=True):
    FigureCanvasAgg(fig)
    buffer = io.BytesIO()
    kwargs = {"bbox_inches": "tight"} if tight else {}
    fig.savefig(buffer, format="png", dpi=dpi, **kwargs)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _num(value):
    try:
        out = float(value)
        return out if np.isfinite(out) else None
    except (TypeError, ValueError):
        return None