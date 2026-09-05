"""
API Gateway (port 5000)

Single entry point for all client requests. Routes each request to
the correct backend service and also serves the frontend, so the
whole app is reachable from one URL (and CORS is a non-issue since
everything appears to come from the same origin).
"""
import os
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__, static_folder="static")


@app.after_request
def allow_google_signin_popup(response):
    # Sans cet en-tête explicite, certains navigateurs (Edge/Chrome récents)
    # appliquent une politique COOP par défaut qui bloque le postMessage
    # utilisé par "Sign in with Google" pour renvoyer le jeton au popup —
    # l'utilisateur clique, Google répond, mais le navigateur jette la
    # réponse avant qu'elle n'atteigne notre JS. "same-origin-allow-popups"
    # garde l'isolation d'origine tout en autorisant ce cas précis.
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response

SERVICES = {
    "user": os.environ.get("USER_SERVICE_URL", "http://localhost:5001"),
    "itinerary": os.environ.get("ITINERARY_SERVICE_URL", "http://localhost:5002"),
    "recommendation": os.environ.get("RECOMMENDATION_SERVICE_URL", "http://localhost:5003"),
}

# Route table: URL prefix -> which service handles it
ROUTES = {
    "/register": "user",
    "/login": "user",
    "/auth": "user",
    "/preferences": "user",
    "/itineraries": "itinerary",
    "/destinations": "recommendation",
    "/recommendations": "recommendation",
    "/favorites": "recommendation",
    "/messages": "chat",
    "/uploads": "chat",
    "/media": "chat",
}

SERVICES["chat"] = os.environ.get("CHAT_SERVICE_URL", "http://localhost:5004")

IMAGE_HOSTS = {
    "upload.wikimedia.org",
    "tse4.mm.bing.net",
    "dynamic-media-cdn.tripadvisor.com",
    "images.pexels.com",
    "yaounde6.cm",
    "prod.cdn-medias.jeuneafrique.com",
    "monasteremontfebe.com",
    "camerounreservation.com",
    "a0.muscache.com",
    "images.unsplash.com",
    "guestlodgings.com",
    "cf.bstatic.com",
    "i.ytimg.com",
    "i.pinimg.com",
    "i0.wp.com",
    "www.cuisinedecheznous.net",
    "www.hilton.com",
}


def proxy(service_key, path):
    target = f"{SERVICES[service_key]}{path}"
    headers = {k: v for k, v in request.headers if k.lower() != "host"}
    try:
        resp = requests.request(
            method=request.method,
            url=target,
            headers=headers,
            params=request.args.to_dict(flat=False),
            data=request.get_data(),
            # Sur le plan gratuit de Render, un service endormi peut mettre
            # 20-50s à se réveiller. Un timeout court renvoie une fausse
            # erreur "unavailable" au client alors que le service backend
            # est en réalité en train de démarrer et finit par répondre.
            timeout=55,
        )
    except requests.RequestException:
        return jsonify({"error": f"{service_key}-service unavailable"}), 503

    return Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "application/json"))


@app.route("/image-proxy")
def image_proxy():
    """Serve catalog images from approved hosts without browser hotlink failures."""
    source_url = request.args.get("url", "").strip()
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    allowed_host = hostname in IMAGE_HOSTS or hostname.endswith(".fbcdn.net")
    if parsed.scheme not in {"http", "https"} or not allowed_host:
        return jsonify({"error": "image host not allowed"}), 400

    try:
        image = requests.get(
            source_url,
            headers={"User-Agent": "Dzula/1.0 image proxy"},
            timeout=15,
        )
    except requests.RequestException:
        return jsonify({"error": "image unavailable"}), 502

    content_type = image.headers.get("Content-Type", "")
    if image.status_code != 200 or not content_type.startswith("image/"):
        return jsonify({"error": "image unavailable"}), 502
    if len(image.content) > 16 * 1024 * 1024:
        return jsonify({"error": "image too large"}), 413

    response = Response(image.content, status=200, content_type=content_type)
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.route("/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"])
def route_request(subpath):
    # Sert d'abord les fichiers statiques (images, favicon, etc.) si le
    # chemin correspond à un fichier réel dans gateway/static/ — sinon la
    # route générique ci-dessous les intercepte et renvoie 404 à tort.
    static_dir = app.static_folder or "static"
    static_path = os.path.join(static_dir, subpath)
    if request.method == "GET" and os.path.isfile(static_path):
        return send_from_directory(static_dir, subpath)

    full_path = "/" + subpath
    base_path = "/" + subpath.split("/")[0]
    if base_path in ROUTES:
        return proxy(ROUTES[base_path], full_path)
    return jsonify({"error": "not found"}), 404


@app.route("/")
def serve_frontend():
    static_dir = app.static_folder or "static"
    return send_from_directory(static_dir, "index.html")


@app.route("/health")
def health():
    statuses = {}
    for name, url in SERVICES.items():
        try:
            r = requests.get(f"{url}/health", timeout=2)
            statuses[name] = r.json()
        except requests.RequestException:
            statuses[name] = {"status": "unreachable"}
    return jsonify({"gateway": "ok", "services": statuses}), 200


@app.route("/admin/stats")
def admin_stats():
    """
    Agrège les statistiques admin des 3 services, sur le même principe que
    /health ci-dessus. L'autorisation (JWT valide + username dans la liste
    admin) est vérifiée indépendamment par CHAQUE service, pas ici — le
    gateway se contente de transmettre le header Authorization et de
    relayer un refus si l'un des services répond 401/403.
    """
    auth_header = request.headers.get("Authorization", "")
    headers = {"Authorization": auth_header} if auth_header else {}

    combined = {}
    for name, url in SERVICES.items():
        try:
            r = requests.get(f"{url}/admin/stats", headers=headers, timeout=3)
        except requests.RequestException:
            return jsonify({"error": f"{name}-service unavailable"}), 503

        if r.status_code in (401, 403):
            return Response(r.content, status=r.status_code, content_type="application/json")
        if r.status_code != 200:
            return jsonify({"error": f"{name}-service returned {r.status_code}"}), 502

        combined.update(r.json())

    return jsonify(combined), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)