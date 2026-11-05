from pathlib import Path

from jsmn_tools.plugin.zephyr import load_zephyr_resource

def collect(loader):
    root = Path(__file__).parent
    return [
        load_zephyr_resource(loader, root / "schemas/mod_a.openapi.yaml", "mod_a", "mod_a", 0),
    ]

def extend(env):
    env.tests["cool"] = lambda x: True
