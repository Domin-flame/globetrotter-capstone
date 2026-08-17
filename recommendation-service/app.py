"""
Recommendation Service (port 5003)

Owns: destinations.json
Routes:
  GET /destinations
  GET /recommendations

/recommendations makes a REAL inter-service HTTP call to the
User Service to fetch the current user's preferences.
"""
import os
import json
import datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

from auth import get_current_user
from models import (
    get_all_destinations,
    get_reviews_for_destination,
    upsert_review,
    get_rating_summary,
    get_all_events,
    get_events_for_destination,
    create_event,
    event_status,
    has_ongoing_or_upcoming_event,
)

app = Flask(__name__)
CORS(app)

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")

ADMIN_USERNAMES = set(
    u.strip() for u in os.environ.get("ADMIN_USERNAMES", "").split(",") if u.strip()
)


def _with_rating(dest):
    summary = get_rating_summary(dest["id"])
    entry = dict(dest)
    entry["rating_avg"] = summary["average"]
    entry["rating_count"] = summary["count"]
    entry["has_event"] = has_ongoing_or_upcoming_event(dest["id"])
    return entry


def _require_admin(request_obj):
    username = get_current_user(request_obj)
    if not username:
        return None, (jsonify({"error": "authentication required"}), 401)
    if username not in ADMIN_USERNAMES:
        return None, (jsonify({"error": "admin access required"}), 403)
    return username, None


@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    _, error = _require_admin(request)
    if error:
        return error
    return jsonify({"destinations_count": len(get_all_destinations())}), 200


@app.route("/destinations", methods=["GET"])
def search_destinations():
    q = request.args.get("q", "").strip().lower()
    tag = request.args.get("tag", "").strip().lower()
    category = request.args.get("category", "").strip().lower()
    neighborhood = request.args.get("neighborhood", "").strip().lower()
    max_cost_str = request.args.get("max_cost", "").strip()

    max_cost = None
    if max_cost_str:
        try:
            max_cost = int(max_cost_str)
        except ValueError:
            return jsonify({"error": "max_cost must be an integer"}), 400

    destinations = get_all_destinations()
    results = []
    for dest in destinations:
        if q:
            searchable = " ".join([
                dest.get("name", ""), dest.get("neighborhood", ""), dest.get("description", ""),
            ]).lower()
            if q not in searchable:
                continue
        if tag and tag not in [t.lower() for t in dest.get("tags", [])]:
            continue
        if category and category != dest.get("category", "").lower():
            continue
        if neighborhood and neighborhood not in dest.get("neighborhood", "").lower():
            continue
        if max_cost is not None:
            cost = dest.get("avg_cost_per_day")
            if cost is None or cost > max_cost:
                continue
        results.append(dest)

    return jsonify([_with_rating(d) for d in results]), 200


@app.route("/recommendations", methods=["GET"])
def get_recommendations():
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    try:
        resp = requests.get(f"{USER_SERVICE_URL}/internal/preferences/{username}", timeout=55)
    except requests.RequestException:
        return jsonify({"error": "user-service unavailable"}), 503

    if resp.status_code == 404:
        return jsonify({"error": "user not found"}), 404
    if resp.status_code != 200:
        return jsonify({"error": "failed to fetch user preferences"}), 502

    preferences = [p.lower() for p in resp.json().get("preferences", [])]

    try:
        limit = int(request.args.get("limit", 5))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400

    destinations = get_all_destinations()
    scored = []
    for dest in destinations:
        dest_tags = [t.lower() for t in dest.get("tags", [])]
        score = sum(1 for pref in preferences if pref in dest_tags)
        scored.append((score, dest))

    scored.sort(key=lambda x: (-x[0], x[1].get("name", "")))

    results = []
    for score, dest in scored[:limit]:
        entry = _with_rating(dest)
        entry["match_score"] = score
        results.append(entry)

    return jsonify(results), 200


@app.route("/destinations/<int:dest_id>/reviews", methods=["GET"])
def list_reviews(dest_id):
    if not any(d["id"] == dest_id for d in get_all_destinations()):
        return jsonify({"error": "destination not found"}), 404

    reviews = sorted(
        get_reviews_for_destination(dest_id),
        key=lambda r: r.get("created_at", ""),
        reverse=True,
    )
    summary = get_rating_summary(dest_id)
    return jsonify({"reviews": reviews, "average": summary["average"], "count": summary["count"]}), 200


@app.route("/destinations/<int:dest_id>/reviews", methods=["POST"])
def create_review(dest_id):
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    if not any(d["id"] == dest_id for d in get_all_destinations()):
        return jsonify({"error": "destination not found"}), 404

    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    comment = (data.get("comment") or "").strip()

    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "rating must be a whole number between 1 and 5"}), 400
    if len(comment) > 500:
        return jsonify({"error": "comment must be 500 characters or fewer"}), 400

    review = upsert_review(dest_id, username, rating, comment)
    summary = get_rating_summary(dest_id)
    return jsonify({"review": review, "average": summary["average"], "count": summary["count"]}), 201


@app.route("/destinations/<int:dest_id>/events", methods=["GET"])
def list_events(dest_id):
    if not any(d["id"] == dest_id for d in get_all_destinations()):
        return jsonify({"error": "destination not found"}), 404

    events = get_events_for_destination(dest_id)
    enriched = [dict(e, status=event_status(e)) for e in events]
    # à venir puis en cours en premier, terminés à la fin
    order = {"ongoing": 0, "upcoming": 1, "past": 2}
    enriched.sort(key=lambda e: (order[e["status"]], e["start_date"]))
    return jsonify({"events": enriched}), 200


@app.route("/destinations/<int:dest_id>/events", methods=["POST"])
def add_event(dest_id):
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    if not any(d["id"] == dest_id for d in get_all_destinations()):
        return jsonify({"error": "destination not found"}), 404

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or "").strip()

    if not title:
        return jsonify({"error": "title is required"}), 400
    if len(title) > 120:
        return jsonify({"error": "title must be 120 characters or fewer"}), 400
    if len(description) > 500:
        return jsonify({"error": "description must be 500 characters or fewer"}), 400

    try:
        start_dt = datetime.date.fromisoformat(start_date)
        end_dt = datetime.date.fromisoformat(end_date)
    except ValueError:
        return jsonify({"error": "start_date and end_date must be valid dates (YYYY-MM-DD)"}), 400

    if end_dt < start_dt:
        return jsonify({"error": "end_date must be on or after start_date"}), 400

    event = create_event(dest_id, username, title, description, start_date, end_date)
    return jsonify({"event": dict(event, status=event_status(event))}), 201


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "recommendation-service", "status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5003))
    app.run(host="0.0.0.0", port=port)