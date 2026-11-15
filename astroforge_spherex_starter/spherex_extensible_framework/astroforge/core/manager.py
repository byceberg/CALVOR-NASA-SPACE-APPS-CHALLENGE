import importlib.util
import json
import sys
import traceback

class PluginManager:
    VALID_TYPES = {"functional", "visual", "hybrid"}

    def __init__(self, plugins_dir, context):
        self.plugins_dir, self.context = plugins_dir, context
        self.plugins, self.errors, self.folders = {}, {}, {}

    def discover_and_load(self):
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        for folder in sorted(self.plugins_dir.iterdir()):
            manifest_path = folder / "plugin.json"
            if not folder.is_dir() or not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self._load_one(folder, manifest)
            except Exception as exc:
                self.errors[folder.name] = str(exc)
                self.context.logger.error("Plugin %s failed: %s\n%s", folder.name, exc, traceback.format_exc())

    
    def _load_one(self, folder, manifest):
        plugin_id = manifest.get("id")
        

        if not plugin_id or plugin_id in self.plugins:
            raise ValueError("Missing or duplicate plugin id")

        kind = manifest.get("type", "functional")

        if kind not in self.VALID_TYPES:
            raise ValueError("Unsupported plugin type: " + kind)

        entry = manifest.get("entrypoint", "")

        if ":" not in entry:
            raise ValueError("entrypoint must be module:Class")

        module_name, class_name = entry.split(":", 1)

        module_path = (
            folder / (module_name.replace(".", "/") + ".py")
        ).resolve()

        folder = folder.resolve()

        if folder not in module_path.parents or not module_path.is_file():
            raise ValueError("Invalid plugin entrypoint")

        unique_name = "_astroforge_plugin_" + plugin_id

        spec = importlib.util.spec_from_file_location(
            unique_name,
            module_path,
            submodule_search_locations=[str(folder)]
        )

        if spec is None or spec.loader is None:
            raise ImportError("Cannot load plugin module")

        module = importlib.util.module_from_spec(spec)

        print("DEBUG PACKAGE:", repr(module.__package__))
        print("DEBUG PATHS:", module.__spec__.submodule_search_locations)

        sys.modules[unique_name] = module

        try:
            spec.loader.exec_module(module)

            cls = getattr(module, class_name)

            plugin = cls(self.context)
            plugin.manifest = manifest
            plugin.setup()
            plugin.state = "active"

            self.plugins[plugin_id] = plugin
            self.folders[plugin_id] = folder

            self.context.logger.info("Loaded plugin: %s", plugin_id)

        except Exception:
            sys.modules.pop(unique_name, None)
            raise


    def list_plugins(self):
        result = []
        for pid, plugin in self.plugins.items():
            m = plugin.manifest
            kind = m.get("type", "functional")
            result.append({
                "id": pid, "name": m.get("name", pid), "version": m.get("version", "0.0.0"),
                "type": kind, "description": m.get("description", ""), "state": plugin.state,
                "actions": plugin.get_actions() if kind in ("functional", "hybrid") else [],
                "view": plugin.get_view() if kind in ("visual", "hybrid") else None,
                "ui": m.get("ui", {})
            })
        return result

    def execute(self, plugin_id, action_id, payload):
        plugin = self.plugins.get(plugin_id)
        if plugin is None or plugin.state != "active":
            raise KeyError("Plugin is not active: " + plugin_id)
        result = plugin.execute(action_id, payload or {})
        self.context.events.publish("plugin.action.completed", {"plugin_id": plugin_id, "action_id": action_id})
        return result

    def shutdown(self):
        for plugin in reversed(list(self.plugins.values())):
            try:
                plugin.shutdown()
                plugin.state = "stopped"
            except Exception:
                self.context.logger.exception("Plugin shutdown failed")
