"""
API Gateway (port 5000)

Single entry point for all client requests. Routes each request to
the correct backend service and also serves the frontend, so the
whole app is reachable from one URL (and CORS is a non-issue since
everything appears to come from the same origin).
"""
import os

import requests
from flask import Flask, request, jsonify, send_from_directory, Response

app = Flask(__name__, static_folder="static")

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
}


def proxy(service_key, path):
    target = f"{SERVICES[service_key]}{path}"
    headers = {k: v for k, v in request.headers if k.lower() != "host"}
    try:
        resp = requests.request(
            method=request.method,
            url=target,
            headers=headers,
            params=request.args,
            data=request.get_data(),
            timeout=5,
        )
    except requests.RequestException:
        return jsonify({"error": f"{service_key}-service unavailable"}), 503

    return Response(resp.content, status=resp.status_code, content_type=resp.headers.get("Content-Type", "application/json"))


@app.route("/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"])
def route_request(subpath):
    full_path = "/" + subpath
    base_path = "/" + subpath.split("/")[0]
    if base_path in ROUTES:
        return proxy(ROUTES[base_path], full_path)
    return jsonify({"error": "not found"}), 404


@app.route("/")
def serve_frontend():
    return send_from_directory(app.static_folder, "index.html")


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