
from pathlib import Path
import json
import numpy as np
from astroforge.core.plugin import BasePlugin
from datetime import datetime

try:
    from astropy.io import fits
    from astropy.wcs import WCS
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False


class SphereXPlugin(BasePlugin):
    DISPLAY_SIZE = 300

    def setup(self):
        self.fits_files = []
        self.selections = {}
        self.current_folder = None
        self.current_index = 0
        self.context.logger.info("SPHEREx FITS Explorer ready.")

    def get_view(self):
        return {
            "type": "spherex_custom",
            "script": "/plugin-ui/spherex_viewer/ui.js"
        }

    def get_actions(self):
        return [
            {
                "id": "list_downloaded_folders",
                "name": "List Downloaded Folders",
                "inputs": []
            },
            {
                "id": "select_folder",
                "name": "Load Selected Folder",
                "inputs": [
                    {
                        "id": "folder_name",
                        "label": "Downloaded Observation Folder",
                        "type": "select",
                        "options": []
                    }
                ]
            },
            {
                "id": "get_frame",
                "name": "Get Frame",
                "inputs": [{"id": "index", "type": "number", "default": 0}]
            },
            {
                "id": "toggle_point",
                "name": "Toggle Coordinate Selection",
                "inputs": [
                    {"id": "index", "type": "number"},
                    {"id": "x", "type": "number"},
                    {"id": "y", "type": "number"},
                    {"id": "name", "type": "string"}
                ]
            },
            {
                "id": "clear_selections",
                "name": "Clear Selections",
                "inputs": [{"id": "index", "type": "number"}]
            },
            {
                "id": "export_labels",
                "name": "Export Labels to JSON",
                "inputs": []
            }
        ]

    def execute(self, action_id, payload):
        base_dir = Path("downloaded_fits")

        if not base_dir.exists():
            base_dir = self.context.root / "downloaded_fits"

        if action_id == "list_downloaded_folders":
            subfolders = []

            if base_dir.exists() and base_dir.is_dir():
                for p in base_dir.glob("**/*"):
                    if p.is_dir() and any(
                        f.suffix.lower() in (".fits", ".fit")
                        for f in p.iterdir()
                    ):
                        rel_path = str(p.relative_to(base_dir))
                        if rel_path not in subfolders:
                            subfolders.append(rel_path)

                for p in base_dir.iterdir():
                    if p.is_dir() and p.name not in subfolders:
                        subfolders.append(p.name)

            return {"folders": sorted(set(subfolders))}

        elif action_id == "select_folder":
            folder_name = payload.get("folder_name", "").strip()

            target_dir = (base_dir / folder_name).resolve()

            if base_dir.resolve() not in target_dir.parents:
                raise ValueError("Invalid folder path")

            self.current_folder = target_dir
            self.current_index = 0
            self.fits_files = []

            if target_dir.exists() and target_dir.is_dir():
                found_files = []

                for ext in ("*.fits", "*.FITS", "*.fit", "*.FIT"):
                    found_files.extend(target_dir.glob(ext))
                    found_files.extend(target_dir.glob(f"**/{ext}"))

                self.fits_files = sorted(
                    set(str(p) for p in found_files if p.is_file())
                )

            if self.fits_files:
                ordered_dict = self.order()
                self.fits_files = list(ordered_dict.keys())

            self.context.logger.info(
                f"Folder '{folder_name}' loaded: "
                f"{len(self.fits_files)} FITS file(s) found."
            )

            self.selections = {
                Path(f).name: [] for f in self.fits_files
            }

            return self._build_state_response(self.current_index)

        elif action_id == "get_frame":
            self.current_index = int(payload.get("index", 0))
            return self._build_state_response(self.current_index)

        elif action_id == "toggle_point":
            idx = int(payload.get("index", 0))
            self.current_index = idx

            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            point_name = payload.get("name", "").strip()

            if not self.fits_files:
                return self._build_state_response(self.current_index)

            idx = max(0, min(idx, len(self.fits_files) - 1))
            fname = Path(self.fits_files[idx]).name

            existing = self.selections.setdefault(fname, [])

            filtered = [
                p for p in existing
                if abs(p["x"] - x) > 12 or abs(p["y"] - y) > 12
            ]

            if len(filtered) < len(existing):
                self.selections[fname] = filtered

            else:
                if not point_name:
                    point_name = f"cisim_{len(existing) + 1}"

                if any(
                    p.get("name", "").lower() == point_name.lower()
                    for p in existing
                ):
                    self.context.logger.error(
                        f"Duplicate name '{point_name}' in frame {fname}"
                    )
                    return self._build_state_response(self.current_index)

                coordinates = self._pixel_to_wcs(
                    self.fits_files[idx], x, y
                )

                if coordinates is None:
                    self.context.logger.error(
                        f"WCS conversion failed for {fname}"
                    )
                    return self._build_state_response(self.current_index)

                existing.append({
                    "x": x,
                    "y": y,
                    **coordinates,
                    "name": point_name
                })

            return self._build_state_response(self.current_index)

        elif action_id == "clear_selections":
            idx = int(payload.get("index", 0))
            self.current_index = idx

            if self.fits_files:
                idx = max(0, min(idx, len(self.fits_files) - 1))
                fname = Path(self.fits_files[idx]).name
                self.selections[fname] = []

            return self._build_state_response(self.current_index)

        elif action_id == "export_labels":
            if self.current_folder and self.current_folder.exists():
                json_path = self.current_folder / "labels.json"

                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(
                        self.selections,
                        f,
                        indent=4,
                        ensure_ascii=False
                    )

                self.context.logger.info(
                    f"Labels successfully exported to {json_path}"
                )

            else:
                self.context.logger.error(
                    "No active observation folder selected for export."
                )

            return self._build_state_response(self.current_index)

        raise KeyError(f"Unknown action: {action_id}")

    def _find_image_hdu(self, hdul):
        for hdu in hdul:
            if hdu.data is not None and getattr(hdu.data, "ndim", 0) >= 2:
                return hdu

        return None

    def order(self):
        order_dict = {}

        for p in self.fits_files:
            try:
                with fits.open(p) as hdul:
                    header = hdul[1].header

                    date_obs = (
                        header.get("DATE-OBS")
                        or header.get("DATEOBS")
                    )

                    time_obs = (
                        header.get("TIME-OBS")
                        or header.get("TIMEOBS")
                    )

                    if date_obs:
                        date_str = str(date_obs).strip()

                        if "T" not in date_str and time_obs:
                            date_str = (
                                f"{date_str}T{str(time_obs).strip()}"
                            )
                        elif "T" not in date_str:
                            date_str = f"{date_str}T00:00:00"
                    else:
                        date_str = "1970-01-01T00:00:00"

                    order_dict[p] = date_str

            except Exception as e:
                self.context.logger.error(
                    f"Error reading header for {p}: {e}"
                )
                order_dict[p] = "1970-01-01T00:00:00"

        sorted_order = dict(
            sorted(
                order_dict.items(),
                key=lambda item: datetime.fromisoformat(item[1])
            )
        )

        return sorted_order

    def _pixel_to_wcs(self, filepath, x, y):
        if not HAS_ASTROPY or not Path(filepath).exists():
            return None

        try:
            with fits.open(filepath) as hdul:
                hdu = self._find_image_hdu(hdul)

                if hdu is None:
                    return None

                w = WCS(hdu.header).celestial

                ra, dec = w.all_pix2world(x, y, 0)

                ra = float(ra)
                dec = float(dec)

                return {
                    "ra": round(ra, 7),
                    "dec": round(dec, 7),
                    "ra_arcsec": round(ra * 3600, 4),
                    "dec_arcsec": round(dec * 3600, 4)
                }

        except Exception as e:
            self.context.logger.error(
                f"WCS conversion failed for {filepath}: {e}"
            )

        return None

    def _render_fits_base64(self, filepath):
        size = self.DISPLAY_SIZE
        orig_w, orig_h = size, size

        if HAS_ASTROPY and Path(filepath).exists():
            try:
                with fits.open(filepath) as hdul:
                    hdu = self._find_image_hdu(hdul)

                    if hdu is None:
                        raise ValueError("No 2D image HDU found in file")

                    data = np.nan_to_num(hdu.data.astype(float))

                    while data.ndim > 2:
                        data = data[0]

                    orig_h, orig_w = data.shape

                    vmin, vmax = np.percentile(data, [5, 99.5])

                    norm = np.clip(
                        (data - vmin) / (vmax - vmin + 1e-8),
                        0,
                        1
                    )

                    ys = np.linspace(0, orig_h - 1, size).astype(int)
                    xs = np.linspace(0, orig_w - 1, size).astype(int)

                    grid = (
                        norm[np.ix_(ys, xs)] * 255
                    ).astype(np.uint8)

                    return grid.tolist(), int(orig_w), int(orig_h)

            except Exception as e:
                self.context.logger.error(
                    f"Failed to render {filepath}: {e}"
                )

        return np.zeros((size, size), dtype=np.uint8).tolist(), orig_w, orig_h

    def _build_state_response(self, idx):
        total = len(self.fits_files)

        if total == 0:
            return {
                "current_index": 0,
                "filename": "No downloaded files found",
                "total_fits": 0,
                "selected_fits_count": 0,
                "current_points": [],
                "image_matrix": [],
                "orig_width": 300,
                "orig_height": 300,
                "label_history": []
            }

        selected_count = sum(
            1 for pts in self.selections.values() if len(pts) > 0
        )

        idx = max(0, min(idx, total - 1))

        filepath = self.fits_files[idx]
        fname = Path(filepath).name

        matrix, orig_w, orig_h = self._render_fits_base64(filepath)

        all_labels = sorted(list(set(
            p.get("name", "")
            for pts in self.selections.values()
            for p in pts
            if p.get("name")
        )))

        return {
            "current_index": idx,
            "filename": fname,
            "total_fits": total,
            "selected_fits_count": selected_count,
            "current_points": self.selections.get(fname, []),
            "image_matrix": matrix,
            "orig_width": orig_w,
            "orig_height": orig_h,
            "label_history": all_labels
        }
