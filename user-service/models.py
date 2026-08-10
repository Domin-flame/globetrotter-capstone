"""User Service — owns users.json exclusively."""
import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(_BASE_DIR, "data", "users.json")


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
