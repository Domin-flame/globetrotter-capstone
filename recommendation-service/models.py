"""Recommendation Service — owns destinations.json and reviews.json."""
import json
import os
import uuid
import datetime

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DESTINATIONS_FILE = os.path.join(_BASE_DIR, "data", "destinations.json")
REVIEWS_FILE = os.path.join(_BASE_DIR, "data", "reviews.json")
EVENTS_FILE = os.path.join(_BASE_DIR, "data", "events.json")
FAVORITES_FILE = os.path.join(_BASE_DIR, "data", "favorites.json")


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


def get_all_destinations():
    return _read_json(DESTINATIONS_FILE)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def get_all_reviews():
    return _read_json(REVIEWS_FILE)


def get_reviews_for_destination(destination_id):
    return [r for r in get_all_reviews() if r.get("destination_id") == destination_id]


def upsert_review(destination_id, username, rating, comment):
    """One review per user per destination — a second submission edits the first."""
    reviews = get_all_reviews()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for r in reviews:
        if r.get("destination_id") == destination_id and r.get("username") == username:
            r["rating"] = rating
            r["comment"] = comment
            r["updated_at"] = now
            _write_json(REVIEWS_FILE, reviews)
            return r

    new_review = {
        "id": str(uuid.uuid4()),
        "destination_id": destination_id,
        "username": username,
        "rating": rating,
        "comment": comment,
        "created_at": now,
    }
    reviews.append(new_review)
    _write_json(REVIEWS_FILE, reviews)
    return new_review


def get_rating_summary(destination_id):
    revs = get_reviews_for_destination(destination_id)
    if not revs:
        return {"average": None, "count": 0}
    avg = sum(r["rating"] for r in revs) / len(revs)
    return {"average": round(avg, 1), "count": len(revs)}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def get_all_events():
    return _read_json(EVENTS_FILE)


def get_events_for_destination(destination_id):
    return [event for event in get_all_events() if event.get("destination_id") == destination_id]


def event_status(event):
    today = datetime.date.today()
    start_date = event.get("start_date")
    end_date = event.get("end_date")

    if not start_date or not end_date:
        return "upcoming"

    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except ValueError:
        return "upcoming"

    if end_dt < today:
        return "past"
    if start_dt <= today <= end_dt:
        return "ongoing"
    return "upcoming"


def create_event(destination_id, username, title, description, start_date, end_date):
    events = get_all_events()
    event = {
        "id": str(uuid.uuid4()),
        "destination_id": destination_id,
        "username": username,
        "title": title,
        "description": description,
        "start_date": start_date,
        "end_date": end_date,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    events.append(event)
    _write_json(EVENTS_FILE, events)
    return event


def has_ongoing_or_upcoming_event(destination_id):
    return any(
        event_status(event) in {"ongoing", "upcoming"}
        for event in get_events_for_destination(destination_id)
    )


def get_favorite_ids(username):
    """Retourne l'ensemble des id de destinations favorites d'un utilisateur."""
    favorites = _read_json(FAVORITES_FILE)
    return {f["destination_id"] for f in favorites if f["username"] == username}


def add_favorite(username, destination_id):
    favorites = _read_json(FAVORITES_FILE)
    if any(f["username"] == username and f["destination_id"] == destination_id for f in favorites):
        return False  # déjà en favori
    favorites.append({
        "username": username,
        "destination_id": destination_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    _write_json(FAVORITES_FILE, favorites)
    return True


def remove_favorite(username, destination_id):
    favorites = _read_json(FAVORITES_FILE)
    new_favorites = [
        f for f in favorites
        if not (f["username"] == username and f["destination_id"] == destination_id)
    ]
    if len(new_favorites) == len(favorites):
        return False  # n'était pas en favori
    _write_json(FAVORITES_FILE, new_favorites)
    return True