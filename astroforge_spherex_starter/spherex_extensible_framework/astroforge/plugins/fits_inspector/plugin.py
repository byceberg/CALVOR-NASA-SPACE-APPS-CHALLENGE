from pathlib import Path
from astroforge.core.plugin import BasePlugin

class FITSInspector(BasePlugin):
    def get_actions(self):
        return [{"id":"inspect_header","name":"Inspect FITS header","description":"Read primary HDU header cards from a local FITS file.","inputs":[
            {"name":"path","label":"Local FITS file path","type":"text","default":""}]}]

    def execute(self, action_id, payload):
        if action_id != "inspect_header":
            raise ValueError("Unknown action")
        path = Path(payload.get("path","")).expanduser().resolve()
        if not path.is_file():
            raise ValueError("File does not exist")
        try:
            from astropy.io import fits
        except ImportError:
            raise RuntimeError("Astropy is required. Install with: pip install astropy")
        with fits.open(path, memmap=True) as hdul:
            return {"file":path.name,"hdu_count":len(hdul),
                    "primary_header":{str(k):str(v) for k,v in hdul[0].header.items()}}
