import datetime
import json
import os
import uuid

import jwt
from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from flask_cors import CORS
except ImportError:  # pragma: no cover
    class CORS:
        def __init__(self, *args, **kwargs):
            pass

        def init_app(self, *args, **kwargs):
            pass

from app.models import DESTINATIONS_FILE, ITINERARIES_FILE, USERS_FILE, get_all_destinations, get_all_itineraries, get_all_users, get_itineraries_for_user, get_user_by_username, save_itinerary, save_user

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


def _write_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _read_json(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        return json.loads(content) if content else []


def _generate_token(username):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _get_current_user(req):
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


def _with_rating(dest):
    entry = dict(dest)
    entry["rating_avg"] = None
    entry["rating_count"] = 0
    entry["has_event"] = False
    return entry


def create_app():
    app = Flask(__name__)
    CORS(app)

    @app.route("/", methods=["GET"])
    def home():
        return """<!DOCTYPE html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>GlobeTrotter</title></head>
  <body><h1>GlobeTrotter</h1><p>Travel planning made simple.</p></body>
</html>""", 200

    @app.route("/register", methods=["POST"])
    def register():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = data.get("password", "")
        preferences = data.get("preferences", [])

        if not username or not password:
            return jsonify({"error": "username and password are required"}), 400

        if get_user_by_username(username):
            return jsonify({"error": "username already exists"}), 409

        user = {
            "username": username,
            "password_hash": generate_password_hash(password),
            "preferences": preferences,
        }
        save_user(user)
        return jsonify({"message": "user registered successfully", "username": username}), 201

    @app.route("/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = data.get("password", "")

        user = get_user_by_username(username)
        if not user or not user.get("password_hash"):
            return jsonify({"error": "invalid username or password"}), 401
        if not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid username or password"}), 401

        token = _generate_token(username)
        return jsonify({"token": token}), 200

    @app.route("/destinations", methods=["GET"])
    def search_destinations():
        q = request.args.get("q", "").strip().lower()
        tag = request.args.get("tag", "").strip().lower()
        category = request.args.get("category", "").strip().lower()
        neighborhood = request.args.get("neighborhood", "").strip().lower()
        continent = request.args.get("continent", "").strip().lower()
        max_cost_str = request.args.get("max_cost", "").strip()

        max_cost = None
        if max_cost_str:
            try:
                max_cost = int(max_cost_str)
            except ValueError:
                return jsonify({"error": "max_cost must be an integer"}), 400

        results = []
        for dest in get_all_destinations():
            if q:
                searchable = " ".join([
                    str(dest.get("name", "")),
                    str(dest.get("neighborhood", "")),
                    str(dest.get("description", "")),
                ]).lower()
                if q not in searchable:
                    continue
            if tag and tag not in [str(t).lower() for t in dest.get("tags", [])]:
                continue
            if category and category != str(dest.get("category", "")).lower():
                continue
            if neighborhood and neighborhood not in str(dest.get("neighborhood", "")).lower():
                continue
            if continent and continent != str(dest.get("continent", "")).lower():
                continue
            if max_cost is not None:
                cost = dest.get("avg_cost_per_day")
                if cost is None or cost > max_cost:
                    continue
            results.append(dest)

        return jsonify([_with_rating(d) for d in results]), 200

    @app.route("/recommendations", methods=["GET"])
    def get_recommendations():
        username = _get_current_user(request)
        if not username:
            return jsonify({"error": "authentication required"}), 401

        user = get_user_by_username(username)
        if not user:
            return jsonify({"error": "user not found"}), 404

        preferences = [str(p).lower() for p in user.get("preferences", [])]

        try:
            limit = int(request.args.get("limit", 5))
        except ValueError:
            return jsonify({"error": "limit must be an integer"}), 400

        scored = []
        for dest in get_all_destinations():
            dest_tags = [str(t).lower() for t in dest.get("tags", [])]
            score = sum(1 for pref in preferences if pref in dest_tags)
            scored.append((score, dest))

        scored.sort(key=lambda item: (-item[0], item[1].get("name", "")))
        results = []
        for score, dest in scored[:limit]:
            entry = _with_rating(dest)
            entry["match_score"] = score
            results.append(entry)

        return jsonify(results), 200

    @app.route("/itineraries", methods=["POST"])
    def create_itinerary():
        username = _get_current_user(request)
        if not username:
            return jsonify({"error": "authentication required"}), 401

        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        destinations = data.get("destinations", [])

        if not title:
            return jsonify({"error": "title is required"}), 400
        if not isinstance(destinations, list):
            return jsonify({"error": "destinations must be a list"}), 400

        itinerary = {
            "id": str(uuid.uuid4()),
            "username": username,
            "title": title,
            "destinations": destinations,
            "start_date": data.get("start_date", ""),
            "end_date": data.get("end_date", ""),
            "notes": data.get("notes", ""),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        save_itinerary(itinerary)
        return jsonify(itinerary), 201

    @app.route("/itineraries", methods=["GET"])
    def list_itineraries():
        username = _get_current_user(request)
        if not username:
            return jsonify({"error": "authentication required"}), 401

        return jsonify(get_itineraries_for_user(username)), 200

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    return app


app = create_app()
