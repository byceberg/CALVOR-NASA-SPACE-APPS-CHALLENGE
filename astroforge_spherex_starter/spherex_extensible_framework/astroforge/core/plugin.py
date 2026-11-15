from dataclasses import dataclass

@dataclass
class PluginContext:
    root: object
    data_dir: object
    config: object
    events: object
    logger: object

class BasePlugin:
    # Override only the methods your plugin needs.
    def __init__(self, context):
        self.context = context
        self.manifest = {}
        self.state = "created"

    def setup(self):
        pass

    def shutdown(self):
        pass

    def get_actions(self):
        return []

    def execute(self, action_id, payload):
        raise NotImplementedError("Plugin does not implement actions")

    def get_view(self):
        return None
