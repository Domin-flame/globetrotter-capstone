"""Itinerary Service — owns itineraries.json exclusively."""
import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ITINERARIES_FILE = os.path.join(_BASE_DIR, "data", "itineraries.json")


def _read_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        return json.loads(content) if content else []


def _write_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def get_all_itineraries():
    return _read_json(ITINERARIES_FILE)


def get_itineraries_for_user(username):
    return [it for it in get_all_itineraries() if it.get("username") == username]


def save_itinerary(itinerary):
    itineraries = get_all_itineraries()
    itineraries.append(itinerary)
    _write_json(ITINERARIES_FILE, itineraries)
