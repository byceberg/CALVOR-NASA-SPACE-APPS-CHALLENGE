import truststore
truststore.inject_into_ssl()

import matplotlib.pyplot as plt
from astropy.io import fits
from matplotlib.colors import LogNorm, LinearSegmentedColormap
from matplotlib.patches import Patch
import pathlib
from datetime import datetime
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
import numpy as np
import hapi
import json

DB_NAME = "hitran_database"

hapi.db_begin(DB_NAME)

def get_coord():
    raise NotImplementedError("!!!???")


class HitranDatabaseManager():
    def __init__(self):
        self.existing_data = {}

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
            name : {
                "wavelength" : wavelengths.tolist(),
                "nu" : wavenumbers.tolist(),
                "sw" : intensities,
                "a" : einstein_a,
                "gamma_air" : air_width,
                "gamma_self" : self_width,
                "elower" : lower_energy,
                "n_air" : temprature_exponent,
                "delta_air" : pressure_shift
            }
        }


class MoleculeAnalyzer():
    def __init__(self, fits_fetcher_object=None):
        print("Molecule Analyzer Awake")

        self.db_manager = HitranDatabaseManager()
        self.fits_fetcher_object = fits_fetcher_object or FitsFetcher()

    def convert_length_to_number(self, length):
        return (10 ** 4) / length

    def band_wavenumber_range(self, band):
        lower, upper, res = self.fits_fetcher_object.bands[band]
        return self.convert_length_to_number(upper), self.convert_length_to_number(lower)

    def fetch_and_insert(self, name, band, molecule_id, isotopologue_id):
        full_name = f"{name}_{band}"
        start_wavenumber, end_wavenumber = self.band_wavenumber_range(band)

        data = self.db_manager.fetch_molecule_table(full_name, molecule_id, isotopologue_id, start_wavenumber, end_wavenumber)

        print("Valid") if self.check_is_valid(data, full_name) else print("Invalid")

    def check_is_valid(self, data, full_name):
        table = data[full_name]

        wavelengths = np.asarray(table["wavelength"], dtype=float)
        intensities = np.asarray(table["sw"], dtype=float)
        valid = (np.isfinite(wavelengths) & np.isfinite(intensities) & (wavelengths > 0) & (intensities > 0))

        self.wavelengths = wavelengths[valid]
        self.intensities = intensities[valid]

        return False if len(self.wavelengths) <= 0 or len(self.intensities) <= 0 else True

    def calculate_voigt_spectrum(self, full_name, start_wavenumber, end_wavenumber, temprature, pressure, wavenumber_step, column_density):
        wavenumbers, cross_section = (hapi.absorptionCoefficient_Voigt(
            SourceTables=full_name,
            Environment={"T": temprature, "p" : pressure},
            OmegaRange=(start_wavenumber, end_wavenumber),
            OmegaStep=wavenumber_step,
            GammaL="gamma_air",
            HITRAN_units=True
        ))

        wavenumbers = np.asarray(wavenumbers, dtype=float)
        cross_section = np.asarray(cross_section, dtype=float)

        wavelengths = self.convert_length_to_number(wavenumbers)
        optical_depth = cross_section * column_density
        transmittance = np.exp(-optical_depth)
        order = np.argsort(wavelengths)

        return {
            "wavelength" : wavelengths[order],
            "wavenumber" : wavenumbers[order],
            "cross_section" : cross_section[order],
            "optical_depth" : optical_depth[order],
            "transmittance" : transmittance[order]
        }

    def plot_molecular_lines(self, molecule, band):
        order = np.argsort(self.wavelengths)

        self.wavelengths = self.wavelengths[order]
        self.intensities = self.intensities[order]

        plt.figure(figsize=(14, 6))
        plt.scatter(self.wavelengths, self.intensities, s=8)
        plt.yscale("log")
        plt.xlabel("Wavelength (µm)")
        plt.ylabel("HITRAN Line Intensity (cm/molecule)")
        plt.title(f"{molecule} Molecular Absorption Lines - {band}")
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.show()

    def plot_spectrum(self, molecule, band, temp, pressure, wn_step, col_den):
        # dalga sayısı aralığı artık dosyanın gerçek bandından hesaplanıyor
        s_wn, e_wn = self.band_wavenumber_range(band)
        spectrum = self.calculate_voigt_spectrum(f"{molecule}_{band}", s_wn, e_wn, temp, pressure, wn_step, col_den)

        plt.figure(figsize=(14, 6))

        plt.plot(
            spectrum["wavelength"],
            spectrum["transmittance"]
        )

        plt.xlabel("Wavelength (µm)")
        plt.ylabel("Transmittance")

        plt.title(f"{molecule} Theoretical Voigt Absorption Spectrum - {band}")

        plt.ylim(0, 1.05)
        plt.grid(alpha=0.3)
        plt.tight_layout()

        plt.show()

        return spectrum

    def analyze_spectrum(self, spectrum):
        pass


class FitsFetcher():
    def __init__(self):
        print("Fits Fetcher Awake")

        self.band = None
        self.bands = {
            "B1":(0.75, 1.09, 39),
            "B2":(1.10, 1.62, 41),
            "B3":(1.63, 2.41, 41),
            "B4":(2.42, 3.82, 35),
            "B5":(3.83, 4.41, 112),
            "B6":(4.42, 5.00, 128)
        }

    def _spectral_wcs(self, hdul):
        return WCS(hdul["IMAGE"].header, fobj=hdul, key="W")

    @staticmethod
    def _as_um(values):
        arr = values
        if hasattr(values, "unit"):
            try:
                arr = values.to(u.um, equivalencies=u.spectral()).value
            except Exception:
                arr = values.value
        return np.asarray(arr, dtype=np.float64)

    def wcs_file_path(self, fits_path, output_dir="wcs_files"):
        fits_path = pathlib.Path(fits_path)
        return pathlib.Path(output_dir) / f"{fits_path.stem}_wcs.fits"

    def build_spectral_wcs_file(self, fits_path, output_dir="wcs_files", overwrite=False, chunk_rows=256):

        fits_path = pathlib.Path(fits_path)
        out_path = self.wcs_file_path(fits_path, output_dir)

        if out_path.exists() and not overwrite:
            print(f"WCS dosyası zaten var: {out_path}")
            return out_path

        out_path.parent.mkdir(parents=True, exist_ok=True)

        with fits.open(fits_path) as hdul:
            if "WCS-WAVE" not in hdul:
                raise ValueError(f"{fits_path.name}: WCS-WAVE uzantısı yok, spektral WCS üretilemez.")

            spec_wcs = self._spectral_wcs(hdul)
            header = hdul["IMAGE"].header
            ny, nx = int(header["NAXIS2"]), int(header["NAXIS1"])
            obs_id = hdul[0].header.get("OBSID")

            cwave = np.full((ny, nx), np.nan, dtype=np.float64)
            cband = np.full((ny, nx), np.nan, dtype=np.float64)

            for y0 in range(0, ny, chunk_rows):
                y1 = min(y0 + chunk_rows, ny)
                yy, xx = np.mgrid[y0:y1, 0:nx]
                result = spec_wcs.pixel_to_world(xx, yy)

                if not isinstance(result, (tuple, list)) or len(result) < 2:
                    raise ValueError("Spektral WCS (dalga boyu, bant genişliği) çifti döndürmedi.")

                cwave[y0:y1] = self._as_um(result[0])
                cband[y0:y1] = self._as_um(result[1])
        for arr in (cwave, cband):
            if np.isfinite(arr).any() and np.nanmedian(np.abs(arr)) < 1e-3:
                arr *= 1e6

        primary = fits.PrimaryHDU()
        primary.header["SOURCE"] = fits_path.name
        if obs_id:
            primary.header["OBSID"] = obs_id

        hdu_w = fits.ImageHDU(cwave.astype(np.float32), name="CWAVE")
        hdu_w.header["BUNIT"] = "um"
        hdu_b = fits.ImageHDU(cband.astype(np.float32), name="CBAND")
        hdu_b.header["BUNIT"] = "um"

        fits.HDUList([primary, hdu_w, hdu_b]).writeto(out_path, overwrite=True)
        print(f"WCS dosyası yazıldı: {out_path}  (dalga boyu {np.nanmin(cwave):.3f}-{np.nanmax(cwave):.3f} um)")
        return out_path

    def load_wcs(self, filename, hdu="IMAGE", verbose=False, check=False):
        """
        Bir FITS dosyasından 2B gök (celestial) WCS yükler.
        SPHEREx'te gökyüzü WCS'i primary HDU'da değil IMAGE uzantısındadır;
        hdu bulunamazsa primary HDU denenir.
        """
        with fits.open(filename) as hdulist:
            try:
                header = hdulist[hdu].header
            except (KeyError, IndexError):
                header = hdulist[0].header
            w = WCS(header).celestial

        if verbose:
            print(w.wcs.name)
            w.wcs.print_contents()

        if check:
            self.check_wcs_roundtrip(w)

        return w

    @staticmethod
    def check_wcs_roundtrip(w, tol=1e-6, verbose=True):
        """Piksel -> dünya -> piksel dönüşümünün tutarlılığını ve origin (0/1 tabanlı) eşdeğerliğini doğrular."""
        pixcrd = np.array([[0, 0], [24, 38], [45, 98]], dtype=np.float64)

        world = w.wcs_pix2world(pixcrd, 0)
        pixcrd2 = w.wcs_world2pix(world, 0)
        max_err = float(np.max(np.abs(pixcrd - pixcrd2)))

        w0 = np.asarray(w.wcs_pix2world(0, 0, 0))
        w1 = np.asarray(w.wcs_pix2world(1, 1, 1))
        origin_ok = bool(np.allclose(w0, w1))

        ok = (max_err < tol) and origin_ok
        if verbose:
            print(f"WCS check: max_err={max_err:.2e} px, origin_ok={origin_ok} -> {'OK' if ok else 'FAIL'}")
        return ok

    def load_spherex_data(self, image_path, spectral_wcs_path):
        image_path = pathlib.Path(image_path)
        spectral_wcs_path = pathlib.Path(spectral_wcs_path)

        with fits.open(image_path, memmap=True) as hdul:
            image = np.asarray(hdul["IMAGE"].data, dtype=np.float32).copy()
            flags = np.asarray(hdul["FLAGS"].data).copy()
            variance = np.asarray(hdul["VARIANCE"].data, dtype=np.float32).copy()
            zodi = np.asarray(hdul["ZODI"].data, dtype=np.float32).copy()
            image_wcs = WCS(hdul["IMAGE"].header).celestial
            metadata = {
                "observation_id" : hdul[0].header.get("OBSID"),
                "image_shape" : image.shape,
                "image_unit" : hdul["IMAGE"].header.get("BUNIT"),
                "image_path" : str(image_path)
            }

        with fits.open(spectral_wcs_path, memmap=True) as wcs_hdul:
            cwave = np.asarray(wcs_hdul["CWAVE"].data, dtype=np.float32).copy()
            cband = np.asarray(wcs_hdul["CBAND"].data, dtype=np.float32).copy()

        if image.shape != variance.shape: raise ValueError("IMAGE and VARIANCE shapes differ.")
        if image.shape != flags.shape: raise ValueError("IMAGE and FLAGS shapes differ.")
        if image.shape != cwave.shape: raise ValueError("IMAGE and CWAVE shapes differ.")
        if image.shape != cband.shape: raise ValueError("IMAGE and CBAND shapes differ.")

        return {
            "image" : image,
            "flags" : flags,
            "variance" : variance,
            "zodi" : zodi,
            "cwave" : cwave,
            "cband" : cband,
            "wcs" : image_wcs,
            "metadata" : metadata
        }

    def open_fits(self, fits_path, will_be_shown=False, will_be_saved=False):
        try:
            with fits.open(fits_path) as hdul:
                self.band = None
                hdul.info()

                self.identify_band(hdul)
                print(f"BAND : {self.band}")

                for i, hdu in enumerate(hdul):
                    print(f"\n--- HDU {i} : {hdu.name}---")

                    for key in ["FILTER", "WAVELNTH", "BAND", "EXTNAME", "NAXIS"]:
                        if key in hdu.header:
                            print(f"{key} : {hdu.header[key]}")

                try:
                    self.ir_data = hdul[1].data

                except Exception as e:
                    print(f"Exception : {e}")
                    self.ir_data = hdul[0].data[102, :, :]

                self.show_graph(will_be_saved) if will_be_shown else print("")

        except FileNotFoundError:
            print("File couldn't be founded. File path might be wrong.")

    def show_graph(self, save):
        date = str(datetime.now().hour) + "-" + str(datetime.now().minute) + "-" + str(datetime.now().second) + "-" + str(datetime.now().microsecond)
        plt.figure(figsize=(8, 8))
        plt.imshow(self.ir_data, cmap='inferno', origin='lower', norm=LogNorm())
        plt.colorbar(label='Flux / Intensity')
        plt.title('102 Infrared Band Data')

        plt.savefig(fr"C:\Users\ahmet\Desktop\spherex_extensible_framework\spherex_extensible_framework\astroforge\images_plot\plotfig-{date}.png") if save else print("")

        plt.show()

    def identify_band(self, hdul):
        if "WCS-WAVE" in hdul:
            wave_hdu = hdul["WCS-WAVE"]

            wave_data = wave_hdu.data
            values = np.asarray(wave_data["VALUES"][0]).reshape(-1, 2)

            wavelnths = values[:, 0]
            wavelnths = wavelnths[np.isfinite(wavelnths) & (wavelnths > 0)]

            if len(wavelnths) == 0: raise ValueError("No valid wavelnth values")
            median = np.median(wavelnths)

            for band, (lower, higher, res) in self.bands.items():
                if lower <= median <= higher:
                    self.band = band


class SpectralExtractor():
    DEFAULT_BAD_BITS = (0, 1, 2, 6, 7, 9, 10, 11, 12, 15)

    def __init__(self, fetcher, get_coord=None, bad_bits=DEFAULT_BAD_BITS, min_good_pixels=3,
                 radius_unit=u.arcsec, default_radius_pix=1.5):
        self.fetcher = fetcher
        self.get_coord = get_coord 
        self.radius_unit = radius_unit
        self.default_radius_pix = default_radius_pix
        self.bad_mask = self._bits_to_mask(bad_bits)
        self.min_good_pixels = min_good_pixels
        self.last_spectrum = None

    @staticmethod
    def _bits_to_mask(bits):
        mask = 0
        for b in bits:
            mask |= (1 << b)
        return mask

    def resolve_coord(self, ra=None, dec=None, radius=None):
        if ra is None or dec is None or radius is None:
            if self.get_coord is None:
                if ra is None or dec is None:
                    raise ValueError("ra/dec verilmedi ve get_coord tanımlı değil.")
            else:
                result = self.get_coord()

                if isinstance(result, SkyCoord):
                    result = (result,)
                elif isinstance(result, (tuple, list)) and isinstance(result[0], SkyCoord):
                    result = tuple(result)
                else:
                    result = tuple(result)

                if isinstance(result[0], SkyCoord):
                    c_ra, c_dec = float(result[0].icrs.ra.deg), float(result[0].icrs.dec.deg)
                    c_rad = result[1] if len(result) > 1 else None
                else:
                    c_ra, c_dec = float(result[0]), float(result[1])
                    c_rad = result[2] if len(result) > 2 else None

                ra = c_ra if ra is None else ra
                dec = c_dec if dec is None else dec
                radius = c_rad if radius is None else radius

        radius_arcsec = None
        if radius is not None:
            if isinstance(radius, u.Quantity):
                radius_arcsec = float(radius.to(u.arcsec).value)
            else:
                radius_arcsec = float((float(radius) * self.radius_unit).to(u.arcsec).value)

        return float(ra), float(dec), radius_arcsec

    def extract_single(self, data, ra, dec, radius_arcsec=None):
        coord = SkyCoord(ra * u.deg, dec * u.deg, frame="icrs")
        x0, y0 = data["wcs"].world_to_pixel(coord)

        if not (np.isfinite(x0) and np.isfinite(y0)):
            return None, "pixel_nan"

        # yarıçapı bu gözlemin piksel ölçeğine göre pikselere
        if radius_arcsec is None:
            radius_pix = self.default_radius_pix
        else:
            arcsec_per_pix = float(np.mean(proj_plane_pixel_scales(data["wcs"]))) * 3600.0
            radius_pix = radius_arcsec / arcsec_per_pix

        ny, nx = data["image"].shape
        if x0 < 0 or y0 < 0 or x0 > nx - 1 or y0 > ny - 1:
            return None, "outside_image"

        r = int(np.ceil(radius_pix)) + 1
        xs = slice(max(int(x0) - r, 0), min(int(x0) + r + 1, nx))
        ys = slice(max(int(y0) - r, 0), min(int(y0) + r + 1, ny))

        yy, xx = np.mgrid[ys, xs]
        in_aperture = (xx - x0) ** 2 + (yy - y0) ** 2 <= radius_pix ** 2

        img = data["image"][ys, xs]
        var = data["variance"][ys, xs]
        flg = data["flags"][ys, xs].astype(np.int64)
        cw = data["cwave"][ys, xs]
        cb = data["cband"][ys, xs]

        good = (
            in_aperture
            & np.isfinite(img) & np.isfinite(var) & (var > 0)
            & np.isfinite(cw) & (cw > 0)
            & ((flg & self.bad_mask) == 0)
        )

        n_good = int(good.sum())
        if n_good < self.min_good_pixels:
            return None, f"too_few_good_pixels({n_good}/{int(in_aperture.sum())})"

        w = 1.0 / var[good]
        flux = np.sum(img[good] * w) / np.sum(w)
        flux_err = np.sqrt(1.0 / np.sum(w))
        return {
            "wavelength": float(np.mean(cw[good])),
            "bandwidth": float(np.nanmean(cb[good])),
            "flux": float(flux),
            "flux_err": float(flux_err),
            "n_good": n_good,
            "x": float(x0),
            "y": float(y0),
            "radius_pix": float(radius_pix),
        }, "ok"

    def extract_spectrum(self, observations, ra=None, dec=None, radius=None, verbose=True):
        ra, dec, radius_arcsec = self.resolve_coord(ra, dec, radius)
        if verbose:
            rtxt = f"{radius_arcsec:.2f} arcsec" if radius_arcsec is not None else f"varsayılan {self.default_radius_pix} piksel"
            print(f"Hedef konum: RA={ra:.6f}, Dec={dec:.6f}, yarıçap={rtxt}")

        rows, skipped = [], []

        for image_path, wcs_path in observations:
            try:
                data = self.fetcher.load_spherex_data(image_path, wcs_path)
            except Exception as e:
                skipped.append((str(image_path), f"load_error: {e}"))
                continue

            point, reason = self.extract_single(data, ra, dec, radius_arcsec)

            if point is None:
                skipped.append((str(image_path), reason))
                continue

            point["obs_id"] = data["metadata"]["observation_id"]
            point["unit"] = data["metadata"]["image_unit"]
            rows.append(point)

        if verbose:
            print(f"{len(rows)} nokta çıkarıldı, {len(skipped)} gözlem atlandı.")
            for path, reason in skipped:
                print(f"  atlandı: {path} -> {reason}")

        if not rows:
            self.last_spectrum = None
            return None

        order = np.argsort([r["wavelength"] for r in rows])
        rows = [rows[i] for i in order]

        self.last_spectrum = {
            "wavelength": np.array([r["wavelength"] for r in rows]),
            "bandwidth": np.array([r["bandwidth"] for r in rows]),
            "flux": np.array([r["flux"] for r in rows]),
            "flux_err": np.array([r["flux_err"] for r in rows]),
            "n_good": np.array([r["n_good"] for r in rows]),
            "obs_id": [r["obs_id"] for r in rows],
            "unit": rows[0]["unit"],
            "ra": ra,
            "dec": dec,
            "radius_arcsec": radius_arcsec,
            "radius_pix": np.array([r["radius_pix"] for r in rows]),
        }
        return self.last_spectrum

    def plot_spectrum(self, spectrum=None, title=None):
        s = spectrum or self.last_spectrum
        if s is None:
            print("Çizilecek spektrum yok.")
            return

        plt.figure(figsize=(14, 6))
        plt.errorbar(
            s["wavelength"], s["flux"],
            yerr=s["flux_err"], xerr=s["bandwidth"] / 2,
            fmt="o", ms=3, lw=0.8, capsize=0
        )
        plt.xlabel("Wavelength (µm)")
        plt.ylabel(f"Surface brightness ({s['unit']})")
        plt.title(title or f"SPHEREx observed spectrum  RA={s['ra']:.4f} Dec={s['dec']:.4f}")
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.show()

    def save_csv(self, path, spectrum=None):
        s = spectrum or self.last_spectrum
        if s is None:
            print("Kaydedilecek spektrum yok.")
            return
        table = np.column_stack([s["wavelength"], s["bandwidth"], s["flux"], s["flux_err"], s["n_good"]])
        np.savetxt(path, table, delimiter=",",
                   header="wavelength_um,bandwidth_um,flux,flux_err,n_good", comments="")


class MolecularColorMapper():

    DEFAULT_MOLECULES = {
        "H2O": (1, 1, (0.15, 0.45, 1.00)),
        "CO2": (2, 1, (1.00, 0.20, 0.20)),
        "CO":  (5, 1, (0.20, 0.85, 0.30)),
        "CH4": (6, 1, (1.00, 0.80, 0.10)),
        "N2O": (4, 1, (0.85, 0.30, 0.95)),
    }

    def __init__(self, fetcher, molecule_analyzer, molecules=None, bad_bits=SpectralExtractor.DEFAULT_BAD_BITS):
        self.fetcher = fetcher
        self.molecule_analyzer = molecule_analyzer
        self.molecules = dict(molecules or self.DEFAULT_MOLECULES)
        self.bad_mask = SpectralExtractor._bits_to_mask(bad_bits)
        self.line_lists = {}

    # ------------------------------------------------------------------
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
            except Exception as e:
                print(f"{mol}: HITRAN tablosu alınamadı, atlandı ({e})")
                continue

            table = data[table_name]
            wl = np.asarray(table["wavelength"], dtype=float)
            sw = np.asarray(table["sw"], dtype=float)
            ok = np.isfinite(wl) & np.isfinite(sw) & (wl > 0) & (sw > 0)
            wl, sw = wl[ok], sw[ok]

            if wl.size == 0:
                print(f"{mol}: {band} aralığında hat yok, atlandı.")
                continue

            order = np.argsort(wl)
            wl, sw = wl[order], sw[order]
            self.line_lists[(band, mol)] = {"wl": wl, "cum": np.concatenate([[0.0], np.cumsum(sw)])}
            loaded.append(mol)
            print(f"{mol}: {wl.size} hat yüklendi.")

        return loaded

    def line_strength_map(self, band, mol, cwave, cband):
        """Her pikselin dalga boyu penceresindeki toplam HITRAN hat şiddeti (pencere genişliğine bölünmüş)."""
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
        """
        Hat şiddetlerini log ölçekte 0-1'e çeker.
        per_molecule: her molekül kendi dağılımına göre (hepsi görünür olur)
        global      : ortak ölçek (zayıf moleküller sönük kalır, fiziksel olarak daha dürüst)
        """
        logs = {}
        for mol, sc in raw.items():
            m = sc > 0
            lg = np.full(sc.shape, np.nan, dtype=np.float32)
            lg[m] = np.log10(sc[m])
            logs[mol] = lg

        if mode == "global":
            allvals = np.concatenate([lg[np.isfinite(lg)] for lg in logs.values()])
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
        """Görüntü parlaklığı: yüzdelik kırpma + arcsinh gerilmesi."""
        lo, hi = np.percentile(image[valid], [1, 99.5])
        b = np.clip((np.nan_to_num(image) - lo) / (hi - lo + 1e-12), 0, 1)
        b = np.arcsinh(10 * b) / np.arcsinh(10)
        b[~valid] = 0.0
        return b.astype(np.float32)

    def compose_rgb(self, norm_scores, brightness, sharpness=3.0):
        """
        Piksel rengi: moleküllerin renklerinin skorlarla ağırlıklı karışımı.
        Güçlü hat olmayan pikseller gri kalır, parlaklık görüntüden gelir.
        """
        mols = list(norm_scores)
        S = np.stack([norm_scores[m] for m in mols], axis=0)
        colors = np.array([self.molecules[m][2] for m in mols], dtype=np.float32)

        W = S ** sharpness
        mix = np.einsum("mhw,mc->hwc", W, colors) / (W.sum(axis=0)[..., None] + 1e-9)
        strength = S.max(axis=0)[..., None]

        rgb = brightness[..., None] * ((1.0 - strength) + strength * mix)
        return np.clip(rgb, 0, 1)

    def plot(self, image_path, spectral_wcs_path, band, names=None, save_path=None,
             show_individual=True, sharpness=3.0, normalize="per_molecule", show=True):
        names = list(names or self.molecules.keys())
        loaded = self.load_line_lists(band, names)
        if not loaded:
            print("Hiçbir molekül için hat listesi yok, çizim yapılamadı.")
            return None

        data = self.fetcher.load_spherex_data(image_path, spectral_wcs_path)
        image, cwave, cband = data["image"], data["cwave"], data["cband"]

        valid = (np.isfinite(image) & np.isfinite(cwave) & (cwave > 0)
                 & ((data["flags"].astype(np.int64) & self.bad_mask) == 0))
        if not valid.any():
            print("Geçerli piksel yok.")
            return None

        raw = {m: self.line_strength_map(band, m, cwave, cband) for m in loaded}
        norm = self.normalize_scores(raw, normalize)
        for m in norm:
            norm[m][~valid] = 0.0

        brightness = self.brightness_map(image, valid)
        rgb = self.compose_rgb(norm, brightness, sharpness)

        wl_min, wl_max = float(np.nanmin(cwave[valid])), float(np.nanmax(cwave[valid]))
        title_extra = f"{band}  |  {wl_min:.2f}-{wl_max:.2f} um"

        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        axes[0].imshow(brightness, cmap="inferno", origin="lower")
        axes[0].set_title(f"SPHEREx image  ({title_extra})")
        axes[1].imshow(rgb, origin="lower")
        axes[1].set_title("Molecule-colored image (HITRAN line strength per pixel wavelength)")
        axes[1].legend(
            handles=[Patch(color=self.molecules[m][2], label=m) for m in loaded],
            loc="upper right", framealpha=0.85
        )
        for ax in axes:
            ax.set_xlabel("x (pixel)")
            ax.set_ylabel("y (pixel)")
        plt.tight_layout()

        if save_path:
            save_path = pathlib.Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=150)
            print(f"Kaydedildi: {save_path}")
        if show:
            plt.show()
        plt.close(fig)

        if show_individual:
            fig2, axs = plt.subplots(1, len(loaded), figsize=(4.5 * len(loaded), 4.5), squeeze=False)
            for ax, m in zip(axs[0], loaded):
                cmap = LinearSegmentedColormap.from_list(m, [(0, 0, 0), self.molecules[m][2]])
                ax.imshow(norm[m], cmap=cmap, origin="lower", vmin=0, vmax=1)
                ax.set_title(m)
                ax.set_xticks([])
                ax.set_yticks([])
            plt.tight_layout()

            if save_path:
                ind_path = save_path.with_name(save_path.stem + "_individual" + save_path.suffix)
                fig2.savefig(ind_path, dpi=150)
                print(f"Kaydedildi: {ind_path}")
            if show:
                plt.show()
            plt.close(fig2)

        return {"rgb": rgb, "scores": norm, "raw_scores": raw, "brightness": brightness, "valid": valid}


if __name__ == "__main__":
    fetcher = FitsFetcher()
    molecule_analyzer = MoleculeAnalyzer(fetcher)
    extractor = SpectralExtractor(fetcher, get_coord=get_coord)
    color_mapper = MolecularColorMapper(fetcher, molecule_analyzer)

    dir_path = pathlib.Path(r"C:\Users\ahmet\Desktop\spherex_extensible_framework\gonder")

    WCS_DIR = pathlib.Path("wcs_files")       # her FITS için üretilen CWAVE/CBAND dosyaları

    OUTPUT_DIR = pathlib.Path("color_maps")   # renkli çıktıların kaydedileceği klasör
    MAKE_COLOR_MAPS = True

    observations = []

    for fits_path in sorted(p for p in dir_path.iterdir() if p.is_file()):
        fetcher.open_fits(fits_path, False, False)
        band = fetcher.band
        fetcher.load_wcs(fits_path, check=True)

        if band is None:
            print(f"Band belirlenemedi, atlandı: {fits_path.name}")
            continue

        wcs_path = fetcher.build_spectral_wcs_file(fits_path, WCS_DIR)

        if MAKE_COLOR_MAPS:
            color_mapper.plot(fits_path, wcs_path, band,
                              save_path=OUTPUT_DIR / f"{fits_path.stem}_molecules.png")

        observations.append((fits_path, wcs_path))

    spectrum = extractor.extract_spectrum(observations)
    extractor.plot_spectrum()
    extractor.save_csv("observed_spectrum.csv")