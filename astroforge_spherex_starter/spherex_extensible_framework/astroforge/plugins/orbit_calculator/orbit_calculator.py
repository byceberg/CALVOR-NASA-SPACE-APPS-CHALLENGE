
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord
from astropy import units as u


class OrbitCalculator:

    def __init__(self, observation_folder):
        self.folder = Path(observation_folder).resolve()
        self.labels_path = self.folder / "labels.json"
        self.output_path = self.folder / "orbit_data.json"

    def _read_labels(self):

        if not self.labels_path.exists():
            raise FileNotFoundError(
                f"labels.json not found: {self.labels_path}"
            )

        with self.labels_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Invalid labels.json format.")
        return data
    def list_objects(self):
        labels = self._read_labels()
        found = {}
        for filename, points in labels.items():
            if not isinstance(points, list):
                continue
            for point in points:
                if not isinstance(point, dict):
                    continue
                name = str(point.get("name", "")).strip()
                if not name:
                    continue
                found.setdefault(name, set()).add(filename)
        return [
            {
                "name": name,
                "observations": len(files)
            }
            for name, files in sorted(
                found.items(),
                key=lambda item: item[0].lower()
            )
        ]
    @staticmethod
    def _observation_time(fits_path):
        with fits.open(fits_path, memmap=False) as hdul:
            for hdu in hdul:
                header = hdu.header

                date_obs = (
                    header.get("DATE-OBS")
                    or header.get("DATEOBS")
                )
                time_obs = (
                    header.get("TIME-OBS")
                    or header.get("TIMEOBS")
                )
                if not date_obs:
                    continue

                date_str = str(date_obs).strip()

                if "T" not in date_str:

                    if time_obs:
                        date_str += "T" + str(time_obs).strip()
                    else:
                        date_str += "T00:00:00"

                return Time(date_str, scale="utc")

        return None
    @staticmethod
    def _to_3d(ra_values, dec_values):

        coordinates = SkyCoord(
            ra=np.asarray(ra_values) * u.deg,
            dec=np.asarray(dec_values) * u.deg,
            frame="icrs"
        )
        cartesian =coordinates.cartesian
        return (
            cartesian.x.value.tolist(),
            cartesian.y.value.tolist(),
            cartesian.z.value.tolist()
        )
    def calculate(self, object_name, **kwargs):
        object_name = str(object_name).strip()
        if not object_name:
            raise ValueError("Object name is required.")
        labels = self._read_labels()
        observations = []
        for filename, points in labels.items():

            if not isinstance(points, list):
                continue
            fits_path = self.folder / filename
            for point in points:

                if not isinstance(point, dict):
                    continue

                name = str(
                    point.get("name", "")
                ).strip()

                if name != object_name:
                    continue

                ra = point.get("ra")
                dec = point.get("dec")

                if ra is None or dec is None:
                    continue

                if not fits_path.exists():
                    continue
                try:
                    observation_time = self._observation_time(
                        fits_path
                    )

                    if observation_time is None:
                        continue

                    observations.append({
                        "filename": filename,
                        "jd": float(observation_time.jd),
                        "utc": observation_time.isot,
                        "ra": float(ra),
                        "dec": float(dec),
                        "x_pixel": point.get("x"),
                        "y_pixel": point.get("y")
                    })

                except Exception:
                    continue

        if not observations:
            raise ValueError(
                f"No valid dated observations found for '{object_name}'."
            )
        observations.sort(key=lambda item: item["jd"])
        unique = {}

        for item in observations:
            key = (item["filename"], item["jd"])
            unique[key] = item

        observations = sorted(
            unique.values(),
            key=lambda item: item["jd"]
        )

        ra = [item["ra"] for item in observations]
        dec = [item["dec"] for item in observations]
        jd = [item["jd"] for item in observations]
        x, y, z = self._to_3d(ra, dec)
        reference = SkyCoord(
            ra=ra[0] * u.deg,
            dec=dec[0] * u.deg,
            frame="icrs"
        )

        current = SkyCoord(
            ra=np.asarray(ra) * u.deg,
            dec=np.asarray(dec) * u.deg,
            frame="icrs"
        )

        angular_separation = (
            reference.separation(current).arcsec.tolist()
        )

        result = {
            "object_name": object_name,
            "coordinate_system": "ICRS",
            "frame": "celestial_direction",
            "units": {
                "position": "unit_vector",
                "ra": "degree",
                "dec": "degree",
                "angular_separation": "arcsec"
            },

            "trajectory": {
                "jd": jd,
                "utc": [
                    item["utc"] for item in observations
                ],
                "ra": ra,
                "dec": dec,
                "x": x,
                "y": y,
                "z": z,
                "angular_separation": angular_separation
            },

            "reference_position": {
                "ra": ra[0],
                "dec": dec[0],
                "x": x[0],
                "y": y[0],
                "z": z[0]

            },
            "observations": observations,
            "observation_count": len(observations)

        }
        self.output_path.write_text(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
                allow_nan=False
            ),
            encoding="utf-8"
        )
        return result
