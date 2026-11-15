import time
import threading
import os
import shutil
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

from astropy.utils.data import conf, download_file
from astropy.coordinates import SkyCoord
from astropy import units as u

from astroquery.ipac.irsa import Irsa

class SpherexDownloader:

    def __init__(self, backend_class):
        conf.remote_timeout = 120

        self.backend_class = backend_class
        self.coordinates = None
        self.search_rad = None
        self.lambda_lower = None
        self.lambda_upper = None
        self.resolution = None
        self.band_name = None
        self.results = None
        self.download_progress = None
        self.lock = threading.Lock()
        self.remaining = 0
        self.speed = 100 * 2**20
        self.time = 0
        
        self.output_dir = Path("downloaded_fits") / backend_class.get_output_file()
        self.output_dir.mkdir(exist_ok=True)

    def calculate_speed(self, total):
        elapsed = time.time() - self.time
        if elapsed <= 0:
            return total
        return total / elapsed

    def calculate_time(self):
     if self.speed <= 0:
         return 0
     return self.remaining / self.speed

    def get_urls(self):
        urls = []
        try:
            pos_coord = SkyCoord(ra=self.backend_class.ra * u.deg, dec=self.backend_class.dec * u.deg)
            radius_val = (self.backend_class.arcsec / 2.0) * u.arcsec
            t_start, t_end = self.backend_class.get_time()

            try:
                self.results = Irsa.query_sia(
                    pos=(pos_coord, radius_val),
                    time=(t_start, t_end),
                    band=self.backend_class.get_band(),
                    collection=["spherex_dr1"]
                )
            except Exception as e:
                self.results = Irsa.query_sia(
                    pos=(pos_coord, radius_val)
                )
        except Exception as e:
            self.results = []

        if self.results is not None and len(self.results) > 0:
            for row in self.results:
                access_url = row["access_url"] if "access_url" in row.colnames else row.get("url", "")
                est_size = row.get("access_estsize", 1024 * 1024)
                try:
                    size_bytes = float(est_size) * 1024 if not isinstance(est_size, str) else 5 * 1024 * 1024
                except:
                    size_bytes = 5 * 1024 * 1024
                if access_url:
                    urls.append({
                        "url": access_url,
                        "size": size_bytes,
                        "total_d": 0
                    })
    
        print(f"İndirilecek toplam gözlem URl: {len(urls)}")
        return urls

    def download(self, item):
        try:
            url = str(item["url"])
            print(f"İndiriliyor: {url}")
            local_cache_path = download_file(
                url,
                cache=True,
                show_progress=False
            )
            
            filename = os.path.basename(url.split("?")[0])
            if not filename.endswith(".fits"):
                filename += ".fits"
            dest_path = self.output_dir / filename
            
            if not dest_path.exists():
                shutil.copy(local_cache_path, dest_path)

        except Exception as e:
            print(e)
            return

        try:
            i =item["index"]
            self.download_progress[i] = item["size"]
            with self.lock:
                self.remaining -= item["size"]
                if self.remaining < 0:
                    self.remaining = 0

                downloaded = sum(self.download_progress)
                self.speed = self.calculate_speed(downloaded)
                remaining_time = self.calculate_time() if self.speed > 0 else 0

        except Exception as e:
            print(f"\nİlerleme takibi hatası: {e}")

    def worker(self, urls):
        while True:
            try:
                item = urls.get_nowait()
            except:
                break

            try:
                self.download(item)
            finally:
                urls.task_done()

    def download_simultaneous(self):
        urls = Queue()
        files = self.get_urls()

        if not files:
            return {
                "total_files": 0,
                "downloaded_files": 0,
                "output_directory": str(self.output_dir.absolute()),
                "status": "no_files_found"
            }

        unique_files = {item["url"]: item for item in files}
        files = list(unique_files.values())
        self.download_progress = [0] * len(files)

        self.remaining = sum(item["size"] for item in files)
        for i, item in enumerate(files):
            item["index"] = i
            urls.put(item)

        max_workers = 16

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.worker, urls)
                for _ in range(max_workers)
            ]
            for future in as_completed(futures):
                future.result()
