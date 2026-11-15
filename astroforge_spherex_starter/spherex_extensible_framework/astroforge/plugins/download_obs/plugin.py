from astroforge.core.plugin import BasePlugin
from .backend_main import backend
from .downloader import SpherexDownloader

class SPHERExDownloader(BasePlugin):

    def get_actions(self):
        return [
            {
                "id": "download",
                "name": "Download SPHEREx Data",
                "description": "Search and download SPHEREx observations",
                "inputs": [
                    {
                        "name": "fn",
                        "label": "Save Folder Name (e.g. gozlem1)",
                        "type": "text",
                        "required": True
                    },
                    {
                        "name": "ra",
                        "label": "Right Ascension (degrees)",
                        "type": "number",
                        "required": True
                    },
                    {
                        "name": "dec",
                        "label": "Declination (degrees)",
                        "type": "number",
                        "required": True
                    },
                    {
                        "name": "arcsec",
                        "label": "Search Radius (arcsec)",
                        "type": "number",
                        "required": True
                    },
                    {
                        "name": "start",
                        "label": "Start Date",
                        "type": "date",
                        "required": True
                    },
                    {
                        "name": "end",
                        "label": "End Date",
                        "type": "date",
                        "required": True
                    },
                    {
                        "name": "band",
                        "label": "Spectral Band",
                        "type": "select",
                        "options": ["B1", "B2", "B3", "B4", "B5", "B6"],
                        "default": "B1",
                        "required": True
                    }
                ]
            }
        ]

    def execute(self, action_id, payload):
        if action_id != "download":
            raise ValueError(f"Unknown action: {action_id}")
        folder_name = payload.get("folder_name", "gozlem1").strip()

        backend_obj = backend()
        backend_obj.set_parameters(
            ra=float(payload["ra"]),
            dec=float(payload["dec"]),
            arcsec=float(payload["arcsec"]),
            start=payload["start"],
            end=payload["end"],
            band=payload["band"],
            output_file=payload["fn"]
        )
        
        downloader_obj = SpherexDownloader(backend_obj)
        result = downloader_obj.download_simultaneous()

        return {
            "status": "completed",
            "message": f"SPHEREx download finished. Saved to downloaded_fits/{folder_name}",
            "result": result
        }