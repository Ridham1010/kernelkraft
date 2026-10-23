"""Load the host-side project configuration."""

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(path=CONFIG_PATH):
    """Return the JSON configuration as a dictionary."""
    with Path(path).open(encoding="utf-8") as config_file:
        return json.load(config_file)
