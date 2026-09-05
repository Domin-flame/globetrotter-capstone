"""
Chat Service (port 5004)

Salon communautaire public en temps réel (WebSocket via Socket.IO).

⚠️ Particularité architecturale : ce service est appelé DIRECTEMENT par le
navigateur, pas relayé par le gateway. Le gateway proxy actuel ne fait que
des requêtes HTTP classiques (une requête → une réponse) et ne peut pas
transmettre une connexion WebSocket persistante de la même façon. Le
frontend se connecte donc à ce service sur sa propre URL.

Routes / événements :
  GET  /health                 — vérification de santé (comme les autres services)
  GET  /messages                — historique des derniers messages (REST, au chargement)
  WS   connect                  — nécessite un jeton JWT valide dans le handshake
  WS   send_message             — envoie un message, diffusé à tous les clients connectés
  WS   new_message (broadcast)  — reçu par tous les clients quand un message est publié
"""
import eventlet
eventlet.monkey_patch()

import os
import json
import datetime
import uuid
from werkzeug.utils import secure_filename

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import jwt

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")  # simplifié pour ce projet étudiant

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"

MESSAGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "messages.json")
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "media")
MAX_HISTORY = 100
MAX_MESSAGE_LENGTH = 500
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_MEDIA = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
}


def _load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return []
    with open(MESSAGES_FILE, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
        messages = json.loads(content) if content else []
        changed = False
        for message in messages:
            if not message.get("id"):
                message["id"] = str(uuid.uuid4())
                changed = True
            message.setdefault("comments", [])
        if changed:
            _save_messages(messages)
        return messages


def _save_messages(messages):
    os.makedirs(os.path.dirname(MESSAGES_FILE), exist_ok=True)
    with open(MESSAGES_FILE, "w", encoding="utf-8") as fh:
        json.dump(messages[-MAX_HISTORY:], fh, indent=2, ensure_ascii=False)


def _verify_token(token):
    """Même principe que get_current_user dans les autres services, mais on
    reçoit le jeton directement en argument (pas via un header HTTP), puisque
    la connexion WebSocket ne fonctionne pas de la même façon."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "chat-service", "status": "ok"}), 200


@app.route("/messages", methods=["GET"])
def get_history():
    """Historique chargé une fois au démarrage du salon (REST classique),
    les nouveaux messages arrivent ensuite en direct via WebSocket."""
    return jsonify({"messages": _load_messages()}), 200


@app.route("/uploads", methods=["POST"])
def upload_media():
    username = _verify_token(request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    if not username:
        return jsonify({"error": "authentication required"}), 401
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.mimetype or uploaded.mimetype not in ALLOWED_MEDIA:
        return jsonify({"error": "unsupported media type"}), 400
    content = uploaded.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "file too large"}), 413
    extension = ALLOWED_MEDIA[uploaded.mimetype]
    filename = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_DIR, filename), "wb") as media_file:
        media_file.write(content)
    return jsonify({"url": f"/media/{filename}", "type": uploaded.mimetype, "name": secure_filename(uploaded.filename or filename), "size": len(content)}), 201


@app.route("/media/<path:filename>", methods=["GET"])
def media_file(filename):
    return send_from_directory(MEDIA_DIR, filename, max_age=86400)


@app.route("/messages/<message_id>/comments", methods=["POST"])
def add_comment(message_id):
    username = _verify_token(request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    if not username:
        return jsonify({"error": "authentication required"}), 401
    text = (request.get_json(silent=True) or {}).get("text", "").strip()[:300]
    if not text:
        return jsonify({"error": "comment is required"}), 400
    messages = _load_messages()
    message = next((item for item in messages if item.get("id") == message_id), None)
    if not message:
        return jsonify({"error": "message not found"}), 404
    comment = {"id": str(uuid.uuid4()), "username": username, "text": text, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    message.setdefault("comments", []).append(comment)
    message["comments"] = message["comments"][-50:]
    _save_messages(messages)
    socketio.emit("message_comment", {"message_id": message_id, "comment": comment})
    return jsonify(comment), 201


@socketio.on("connect")
def handle_connect(auth):
    username = _verify_token((auth or {}).get("token"))
    if not username:
        return False  # refuse la connexion si le jeton est absent/invalide


@socketio.on("send_message")
def handle_send_message(data):
    username = _verify_token((data or {}).get("token"))
    if not username:
        emit("chat_error", {"error": "authentication required"})
        return

    text = (data.get("text") or "").strip()
    if not text:
        return
    text = text[:MAX_MESSAGE_LENGTH]

    media = data.get("media") if isinstance(data.get("media"), dict) else None
    if media:
        media_url = media.get("url", "")
        media_type = media.get("type", "")
        if not media_url.startswith("/media/") or media_type not in ALLOWED_MEDIA:
            emit("chat_error", {"error": "invalid media attachment"})
            return
        media = {
            "url": media_url,
            "type": media_type,
            "name": secure_filename(str(media.get("name", "shared-media")))[:120],
            "size": int(media.get("size", 0)),
        }

    message = {
        "id": str(uuid.uuid4()),
        "username": username,
        "text": text,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "media": media,
        "comments": [],
    }

    messages = _load_messages()
    messages.append(message)
    _save_messages(messages)

    emit("new_message", message, broadcast=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5004))
    socketio.run(app, host="0.0.0.0", port=port)