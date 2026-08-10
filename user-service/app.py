"""
User Service (port 5001)

Owns: users.json
Routes:
  POST /register
  POST /login
  POST /auth/google                       (nouveau : connexion via Google)
  GET  /preferences                       (nouveau : lire ses propres préférences)
  PUT  /preferences                       (nouveau : modifier ses préférences)
  GET  /internal/preferences/<username>   (internal-only, called by
                                           Recommendation Service)
"""
import json
import os

import requests as http_requests
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

from models import get_user_by_username, save_user
from auth import generate_token, get_current_user

app = Flask(__name__)
CORS(app)

# À remplacer par ton propre Client ID Google Cloud Console (voir instructions).
# Si laissé vide, la vérification de l'audience du jeton est simplement ignorée —
# à ne faire qu'en développement local, jamais en production.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Chemin direct vers users.json — volontairement indépendant de models.py pour
# ne pas dépendre de fonctions internes non confirmées (voir note à Ryan).
USERS_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "users.json")


def _load_all_users():
    if not os.path.exists(USERS_FILE_PATH):
        return []
    with open(USERS_FILE_PATH, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        return json.loads(content) if content else []


def _persist_all_users(users):
    with open(USERS_FILE_PATH, "w", encoding="utf-8") as fh:
        json.dump(users, fh, indent=2)


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
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
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = get_user_by_username(username)
    # Un compte créé via Google n'a pas de password_hash : on le rejette proprement
    # au lieu de laisser check_password_hash planter sur une valeur None.
    if not user or not user.get("password_hash"):
        return jsonify({"error": "invalid username or password"}), 401
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "invalid username or password"}), 401

    token = generate_token(username)
    return jsonify({"token": token}), 200


@app.route("/auth/google", methods=["POST"])
def google_login():
    """
    Connexion via Google Identity Services.

    Le frontend envoie le jeton d'identité (id_token, un JWT signé par Google)
    obtenu après que l'utilisateur a cliqué sur le bouton Google. On le
    vérifie auprès de l'endpoint tokeninfo de Google (simple, sans dépendance
    supplémentaire — la librairie officielle google-auth serait recommandée
    pour un vrai produit en production, mais ceci suffit largement pour un
    projet étudiant).
    """
    data = request.get_json(silent=True) or {}
    id_token_str = data.get("id_token", "")
    if not id_token_str:
        return jsonify({"error": "id_token is required"}), 400

    try:
        resp = http_requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token_str},
            timeout=5,
        )
    except http_requests.RequestException:
        return jsonify({"error": "unable to verify token with Google"}), 502

    if resp.status_code != 200:
        return jsonify({"error": "invalid Google token"}), 401

    payload = resp.json()

    if GOOGLE_CLIENT_ID and payload.get("aud") != GOOGLE_CLIENT_ID:
        return jsonify({"error": "token audience mismatch"}), 401

    email = payload.get("email")
    email_verified = payload.get("email_verified") in ("true", True)
    if not email or not email_verified:
        return jsonify({"error": "Google account email not verified"}), 401

    username = email  # l'email Google sert d'identifiant unique
    user = get_user_by_username(username)
    is_new_user = user is None

    if is_new_user:
        user = {
            "username": username,
            "password_hash": None,  # pas de mot de passe pour un compte Google
            "preferences": [],
            "auth_provider": "google",
            "display_name": payload.get("name", ""),
        }
        save_user(user)

    token = generate_token(username)
    return jsonify({"token": token, "username": username, "is_new_user": is_new_user}), 200


@app.route("/preferences", methods=["GET"])
def get_preferences():
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    user = get_user_by_username(username)
    if not user:
        return jsonify({"error": "user not found"}), 404

    return jsonify({"username": username, "preferences": user.get("preferences", [])}), 200


@app.route("/preferences", methods=["PUT"])
def update_preferences():
    username = get_current_user(request)
    if not username:
        return jsonify({"error": "authentication required"}), 401

    data = request.get_json(silent=True) or {}
    preferences = data.get("preferences", [])
    if not isinstance(preferences, list):
        return jsonify({"error": "preferences must be a list"}), 400

    users = _load_all_users()
    found = False
    for u in users:
        if u.get("username") == username:
            u["preferences"] = preferences
            found = True
            break

    if not found:
        return jsonify({"error": "user not found"}), 404

    _persist_all_users(users)
    return jsonify({"username": username, "preferences": preferences}), 200


# Liste des usernames/emails autorisés à voir le tableau de bord admin,
# séparés par des virgules (ex: "toi@gmail.com,coequipier@example.com").
ADMIN_USERNAMES = set(
    u.strip() for u in os.environ.get("ADMIN_USERNAMES", "").split(",") if u.strip()
)


def _require_admin(request_obj):
    """Retourne (username, None) si admin, ou (None, response) si refusé."""
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
    return jsonify({"users_count": len(_load_all_users())}), 200


@app.route("/internal/preferences/<username>", methods=["GET"])
def internal_preferences(username):
    """Internal endpoint — called by the Recommendation Service over the
    Docker network only (not exposed publicly through the Gateway)."""
    user = get_user_by_username(username)
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"username": username, "preferences": user.get("preferences", [])}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "user-service", "status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)