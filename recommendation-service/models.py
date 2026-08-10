"""Recommendation Service — owns destinations.json exclusively."""
import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DESTINATIONS_FILE = os.path.join(_BASE_DIR, "data", "destinations.json")


def _read_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        return json.loads(content) if content else []


def get_all_destinations():
    return _read_json(DESTINATIONS_FILE)
