from astropy import units as u
from astropy.time import Time

class backend:

    def __init__(self):
        self.ra = None
        self.dec =None
        self.arcsec = None
        self.start = None
        self.end = None
        self.selected_band =None

    def set_parameters(self, ra, dec,arcsec, start, end, band, output_file):
        self.ra= ra
        self.dec = dec
        self.arcsec =arcsec
        self.start =start
        self.end = end
        self.selected_band= band
        self.output_file=output_file

    def get_degrees(self):
        return self.ra,self.dec

    def get_output_file(self):
        return self.output_file

    def get_arcsec(self):
        return self.arcsec

    def get_band(self):
        bands = {
            "B1":(0.75, 1.09, 39),
            "B2":(1.10, 1.62, 41),
            "B3":(1.63, 2.41, 41),
            "B4":(2.42, 3.82, 35),
            "B5":(3.83, 4.41, 112),
            "B6":(4.42, 5.00, 128)
        }
        low, high, resolution = bands.get(self.selected_band, (0.75, 1.09, 39))
        return low * u.um, high * u.um

    def band_width(self):
        bands = {
            "B1":(0.75, 1.09, 39),
            "B2":(1.10, 1.62, 41),
            "B3":(1.63, 2.41, 41),
            "B4":(2.42, 3.82, 35),
            "B5":(3.83, 4.41, 112),
            "B6":(4.42, 5.00, 128)
        }
        return bands.get(self.selected_band, (0.75, 1.09, 39))

    def get_time(self):
        def parse_date(date_str):
            if not date_str:
                return "2025-05-01"
            date_str = str(date_str).strip()
            if "." in date_str:
                parts = date_str.split(".")
                if len(parts) == 3:
                    return f"{parts[2]}-{parts[1]}-{parts[0]}"
            return date_str

        start_iso = parse_date(self.start)
        end_iso = parse_date(self.end)
        return (
            Time(start_iso, format="iso"),
            Time(end_iso, format="iso")
        )