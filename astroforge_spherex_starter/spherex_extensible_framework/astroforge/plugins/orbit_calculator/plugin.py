from pathlib import Path
from astroforge.core.plugin import BasePlugin
from .orbit_calculator import OrbitCalculator


class FitsConfigPlugin(BasePlugin):

    def get_view(self):
        plugin_id = self.manifest.get("id", "fits_config")
        return {
            "type": "spherex_custom",
            "script": f"/plugin-ui/{plugin_id}/ui.js"
        }

    def _fits_root(self):
        root = Path(getattr(self.context, "root", Path.cwd()))
        candidates = [
            (root.parent.parent / "downloaded_fits").resolve(),
            Path("C:/Users/ATA/Desktop/astroforge_spherex_starter/downloaded_fits").resolve()
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return candidates[0]

    def _folder_path(self, folder):
        if not folder:
            raise ValueError("FITS folder is required.")
        root = self._fits_root()
        target = (root / str(folder)).resolve()
        if root != target and root not in target.parents:
            raise ValueError("Invalid FITS folder path.")
        if not target.is_dir():
            raise FileNotFoundError(f"FITS folder not found: {target}")
        return target

    def get_actions(self):
        return [
            {"id": "list_downloaded_folders", "name": "List Downloaded Folders"},
            {"id": "list_fits_folders", "name": "List FITS Folders"},
            {"id": "select_folder", "name": "Select Folder"},
            {"id": "list_orbit_objects", "name": "List Orbit Objects"},
            {"id": "calculate_orbit", "name": "Calculate Heliocentric Orbit"}
        ]

    def execute(self, action_id, payload):
        payload = payload or {}
        root = self._fits_root()

        if action_id in ("list_downloaded_folders", "list_fits_folders"):
            folders = sorted([p.name for p in root.iterdir() if p.is_dir()]) if root.exists() else []
            return {"folders": folders}

        if action_id == "select_folder":
            folder_name = payload.get("folder_name", "").strip()
            folder_path = self._folder_path(folder_name)
            fits_files = sorted([p.name for p in folder_path.glob("*.fits")])
            
            labels_path = folder_path / "labels.json"
            label_history = []
            if labels_path.exists():
                import json
                with open(labels_path, "r", encoding="utf-8") as f:
                    labels_data = json.load(f)
                    label_history = sorted(list(set(
                        pt.get("name", "") for pts in labels_data.values() for pt in pts if isinstance(pt, dict) and pt.get("name")
                    )))

            return {
                "total_fits": len(fits_files),
                "fits_filenames": fits_files,
                "label_history": label_history
            }

        if action_id == "list_orbit_objects":
            folder = payload.get("folder", "").strip()
            calculator = OrbitCalculator(self._folder_path(folder))
            return {"objects": calculator.list_objects()}

        if action_id == "calculate_orbit":
            folder = payload.get("folder", "").strip()
            object_name = payload.get("object_name", "").strip()
            if not object_name:
                raise ValueError("Object name is required.")
            calculator = OrbitCalculator(self._folder_path(folder))
            result = calculator.calculate(object_name=object_name)
            return {"orbit": result}

        raise KeyError(f"Unknown action: {action_id}")