"""
Tests de l'API GlobeTrotter (Phase 1) -- calés sur le vrai code du repo
sas-bergson/globetrotter-capstone.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import USERS_FILE, ITINERARIES_FILE


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True

    with open(USERS_FILE, "w") as f:
        json.dump([], f)
    with open(ITINERARIES_FILE, "w") as f:
        json.dump([], f)

    with app.test_client() as c:
        yield c

    with open(USERS_FILE, "w") as f:
        json.dump([], f)
    with open(ITINERARIES_FILE, "w") as f:
        json.dump([], f)


def _register_and_login(client, username="alice", password="secret123", preferences=None):
    client.post("/register", json={
        "username": username, "password": password, "preferences": preferences or ["beach", "culture"]
    })
    resp = client.post("/login", json={"username": username, "password": password})
    token = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_home_page_serves_frontend(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data
    assert b"GlobeTrotter" in resp.data


def test_register_creates_user(client):
    resp = client.post("/register", json={"username": "bob", "password": "secret123", "preferences": ["nature"]})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["username"] == "bob"
    assert "message" in body


def test_register_missing_fields_fails(client):
    resp = client.post("/register", json={"username": "onlyname"})
    assert resp.status_code == 400


def test_register_duplicate_username_returns_409(client):
    payload = {"username": "dup", "password": "secret123"}
    client.post("/register", json=payload)
    resp = client.post("/register", json=payload)
    assert resp.status_code == 409


def test_login_success_returns_token(client):
    client.post("/register", json={"username": "carol", "password": "mypassword"})
    resp = client.post("/login", json={"username": "carol", "password": "mypassword"})
    assert resp.status_code == 200
    assert "token" in resp.get_json()


def test_login_wrong_password_returns_401(client):
    client.post("/register", json={"username": "dave", "password": "correct"})
    resp = client.post("/login", json={"username": "dave", "password": "incorrect"})
    assert resp.status_code == 401


def test_search_destinations_no_filter(client):
    resp = client.get("/destinations")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 10


def test_search_destinations_by_tag(client):
    resp = client.get("/destinations?tag=beach")
    assert resp.status_code == 200
    for d in resp.get_json():
        assert "beach" in [t.lower() for t in d["tags"]]


def test_search_destinations_by_continent(client):
    resp = client.get("/destinations?continent=Europe")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.get_json()]
    assert "Paris" in names


def test_search_destinations_by_max_cost(client):
    resp = client.get("/destinations?max_cost=40")
    assert resp.status_code == 200
    for d in resp.get_json():
        assert d["avg_cost_per_day"] <= 40


def test_search_destinations_free_text(client):
    resp = client.get("/destinations?q=souk")
    assert resp.status_code == 200
    names = [d["name"] for d in resp.get_json()]
    assert "Marrakech" in names


def test_search_destinations_invalid_max_cost(client):
    resp = client.get("/destinations?max_cost=notanumber")
    assert resp.status_code == 400


def test_recommendations_require_auth(client):
    resp = client.get("/recommendations")
    assert resp.status_code == 401


def test_recommendations_include_match_score(client):
    headers = _register_and_login(client, preferences=["beach"])
    resp = client.get("/recommendations", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) > 0
    assert "match_score" in body[0]
    # les destinations "beach" doivent être en tête (score le plus élevé en premier)
    assert body[0]["match_score"] >= body[-1]["match_score"]


def test_create_and_list_itinerary(client):
    headers = _register_and_login(client, username="itin_user")

    create_resp = client.post("/itineraries", headers=headers, json={
        "title": "Vacances à Kribi",
        "destinations": ["Kribi"],
        "start_date": "2026-08-01",
        "end_date": "2026-08-07",
        "notes": "Avec Iris",
    })
    assert create_resp.status_code == 201
    assert "created_at" in create_resp.get_json()

    list_resp = client.get("/itineraries", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.get_json()) == 1
    assert list_resp.get_json()[0]["title"] == "Vacances à Kribi"


def test_itinerary_requires_title(client):
    headers = _register_and_login(client, username="notitle")
    resp = client.post("/itineraries", headers=headers, json={
        "destinations": ["Kribi"], "start_date": "2026-08-01", "end_date": "2026-08-07"
    })
    assert resp.status_code == 400


def test_itineraries_require_auth(client):
    resp = client.get("/itineraries")
    assert resp.status_code == 401


def test_itineraries_are_isolated_per_user(client):
    headers_a = _register_and_login(client, username="usera")
    headers_b = _register_and_login(client, username="userb")

    client.post("/itineraries", headers=headers_a, json={
        "title": "Voyage A",
        "destinations": ["Yaoundé"],
        "start_date": "2026-09-01",
        "end_date": "2026-09-05",
    })

    resp_b = client.get("/itineraries", headers=headers_b)
    assert resp_b.get_json() == []
