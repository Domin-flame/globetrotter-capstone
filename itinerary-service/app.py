"""
Itinerary Service (port 5002)

Owns: itineraries.json
Routes:
  POST /itineraries
  GET  /itineraries

Verifies the JWT locally (shared secret) — no call to User Service
needed just to check who's logged in.
"""
import uuid
import datetime
import json
import os

from flask import Flask, request, jsonify
from flask_cors import CORS

from auth import get_current_user
from models import get_itineraries_for_user, save_itinerary

app = Flask(__name__)
CORS(app)


@app.route("/itineraries", methods=["POST"])
def create_itinerary():
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
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
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    return jsonify(get_itineraries_for_user(username)), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "itinerary-service", "status": "ok"}), 200


ADMIN_USERNAMES = set(
    u.strip() for u in os.environ.get("ADMIN_USERNAMES", "").split(",") if u.strip()
)
 
# Chemin direct vers itineraries.json — indépendant de models.py pour ne pas
# dépendre de fonctions internes non vérifiées. Ajuste le chemin si ton
# fichier de données n'est pas dans data/itineraries.json relatif à app.py.
ITINERARIES_FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "itineraries.json"
)
 
 
def _load_all_itineraries():
    if not os.path.exists(ITINERARIES_FILE_PATH):
        return []
    with open(ITINERARIES_FILE_PATH, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        return json.loads(content) if content else []
 
 
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
 
    itineraries = _load_all_itineraries()
 
    # Classement des destinations les plus ajoutées aux itinéraires
    # (équivalent du "Lieux les plus appréciés" vu chez Garoua Explorer).
    counts = {}
    for it in itineraries:
        for dest_name in it.get("destinations", []):
            counts[dest_name] = counts.get(dest_name, 0) + 1
 
    top_destinations = sorted(
        ({"name": name, "count": count} for name, count in counts.items()),
        key=lambda x: -x["count"],
    )[:5]
 
    return jsonify({
        "itineraries_count": len(itineraries),
        "top_destinations": top_destinations,
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
