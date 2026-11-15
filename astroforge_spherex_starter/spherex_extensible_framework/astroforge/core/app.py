import json
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class AstroForgeApp:
    def __init__(self):
        from .config import Config
        from .events import EventBus
        from .logger import create_logger
        from .manager import PluginManager
        from .plugin import PluginContext
        self.root = PROJECT_ROOT
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.config = Config(self.root / "config.json")
        self.logger = create_logger(self.root / "logs")
        self.events = EventBus(self.logger)
        context = PluginContext(self.root, self.data_dir, self.config, self.events, self.logger)
        self.plugins = PluginManager(self.root / "astroforge" / "plugins", context)
        self.plugins.discover_and_load()

    def handler_class(self):
        app = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                app.logger.info("HTTP %s - %s", self.address_string(), fmt % args)

            def send_json(self, data, status=200):
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            def read_json(self):
                size = int(self.headers.get("Content-Length", "0"))
                if size > 2_000_000:
                    raise ValueError("Request body too large")
                raw = self.rfile.read(size) if size else b"{}"
                return json.loads(raw.decode("utf-8"))

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/api/health":
                    return self.send_json({"status": "ok", "name": "AstroForge"})
                if path == "/api/plugins":
                    try:
                        return self.send_json({"plugins": app.plugins.list_plugins(), "errors": app.plugins.errors})
                    except Exception as exc:
                        return self.send_json({"error": str(exc)}, 500)
                if path.startswith("/api/"):
                    return self.send_json({"error": "Not found"}, 404)
                if path.startswith("/plugin-ui/"):
                                return self.serve_plugin_file(path)
                return self.serve_static(path)


            # Handler sınıfına yeni metot:
            def serve_plugin_file(self, request_path):
                parts = [unquote(x) for x in request_path.split("/") if x]
                folder = app.plugins.folders.get(parts[1]) if len(parts) >= 3 else None
                if folder is None:
                    return self.send_json({"error": "Not found"}, 404)
                root = folder.resolve()
                target = (root / "/".join(parts[2:])).resolve()
                allowed = {".html", ".js", ".css", ".json", ".svg", ".png", ".jpg"}
                if root not in target.parents or target.suffix.lower() not in allowed or not target.is_file():
                    return self.send_json({"error": "Not found"}, 404)
                body = target.read_bytes()
                mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
                    mime += "; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                path = urlparse(self.path).path
                if path.startswith("/api/plugins/") and "/actions/" in path:
                    try:
                        parts = [unquote(x) for x in path.split("/") if x]
                        result = app.plugins.execute(parts[2], parts[4], self.read_json())
                        return self.send_json({"result": result})
                    except KeyError as exc:
                        return self.send_json({"error": str(exc)}, 404)
                    except Exception as exc:
                        app.logger.exception("Plugin action failed")
                        return self.send_json({"error": str(exc)}, 400)
                return self.send_json({"error": "Not found"}, 404)

            def serve_static(self, request_path):
                relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
                web_root = (app.root / "astroforge" / "web").resolve()
                target = (web_root / relative).resolve()
                if web_root not in target.parents and target != web_root:
                    return self.send_json({"error": "Invalid path"}, 403)
                if not target.is_file():
                    return self.send_json({"error": "Not found"}, 404)
                body = target.read_bytes()
                mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
                    mime += "; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        return Handler

    def run(self):
        host, port = self.config.get("server.host", "127.0.0.1"), int(self.config.get("server.port", 8765))
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError("Starter server is restricted to loopback")
        server = ThreadingHTTPServer((host, port), self.handler_class())
        self.logger.info("AstroForge running at http://%s:%s", host, port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Stopping AstroForge")
        finally:
            server.server_close()
            self.plugins.shutdown()
