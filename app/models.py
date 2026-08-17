import json
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_FILE = os.path.join(_PROJECT_ROOT, "user-service", "data", "users.json")
ITINERARIES_FILE = os.path.join(_PROJECT_ROOT, "itinerary-service", "data", "itineraries.json")
DESTINATIONS_FILE = os.path.join(_PROJECT_ROOT, "recommendation-service", "data", "destinations.json")
REVIEWS_FILE = os.path.join(_PROJECT_ROOT, "recommendation-service", "data", "reviews.json")


def _read_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        return json.loads(content) if content else []


def _write_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def get_all_users():
    return _read_json(USERS_FILE)


def get_user_by_username(username):
    for user in get_all_users():
        if user.get("username") == username:
            return user
    return None


def save_user(user):
    users = get_all_users()
    users.append(user)
    _write_json(USERS_FILE, users)


def get_all_itineraries():
    return _read_json(ITINERARIES_FILE)


def get_itineraries_for_user(username):
    return [it for it in get_all_itineraries() if it.get("username") == username]


def save_itinerary(itinerary):
    itineraries = get_all_itineraries()
    itineraries.append(itinerary)
    _write_json(ITINERARIES_FILE, itineraries)


def get_all_destinations():
    return _read_json(DESTINATIONS_FILE)
