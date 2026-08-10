# GlobeTrotter — Phase 2 : Microservices

Découpage du monolithe en 3 services indépendants + 1 API Gateway,
conforme au diagramme du cours (slide "Phase 2 – Microservices").

## Architecture

```
Client → API Gateway (5000) ──→ User Service (5001)          → users.json
                              ├─→ Itinerary Service (5002)    → itineraries.json
                              └─→ Recommendation Service (5003) → destinations.json
                                        │
                                        └── appel REST interne vers
                                            User Service pour récupérer
                                            les préférences
```

- **User Service** : `POST /register`, `POST /login`, + une route interne
  `GET /internal/preferences/<username>` (jamais exposée publiquement,
  utilisée uniquement par le Recommendation Service sur le réseau Docker).
- **Itinerary Service** : `POST /itineraries`, `GET /itineraries` — vérifie
  le JWT localement (secret partagé), sans appeler le User Service.
- **Recommendation Service** : `GET /destinations`, `GET /recommendations`
  — pour `/recommendations`, fait un **vrai appel HTTP** au User Service
  pour récupérer les préférences (c'est l'exemple donné explicitement
  dans le cours). C'est la différence entre "faire semblant" de découper
  et une vraie décomposition en microservices.
- **API Gateway** : point d'entrée unique, route chaque requête vers le
  bon service, et sert aussi le frontend — donc tout reste accessible
  depuis une seule URL, sans souci de CORS.

## ⚠️ Avant de lancer : récupère tes vraies données

Les fichiers `data/*.json` de chaque service sont vides (`[]`) pour l'instant.
Copie tes vraies données depuis ton projet monolithe :

```bash
cp /chemin/vers/ancien/projet/data/users.json         user-service/data/users.json
cp /chemin/vers/ancien/projet/data/itineraries.json   itinerary-service/data/itineraries.json
cp /chemin/vers/ancien/projet/data/destinations.json  recommendation-service/data/destinations.json
```

## Lancer tout avec Docker Compose

```bash
docker compose up --build
```

Puis ouvre **http://localhost:5000/** — le frontend est servi directement
par le Gateway, tout passe par le port 5000.

Vérifier que tous les services sont en vie :
```
http://localhost:5000/health
```
→ renvoie le statut du Gateway + des 3 services.

## Lancer sans Docker (pour déboguer un service isolément)

Dans 4 terminaux séparés :
```bash
cd user-service && pip install -r requirements.txt && python app.py
cd itinerary-service && pip install -r requirements.txt && python app.py
cd recommendation-service && pip install -r requirements.txt && python app.py
cd gateway && pip install -r requirements.txt && python app.py
```
Sans Docker Compose, les variables d'environnement `USER_SERVICE_URL` etc.
ne sont pas définies automatiquement — elles retombent sur `localhost`
par défaut, donc ça marche aussi tant que tu lances tout sur la même
machine.

## Ce qui correspond au cahier des charges du cours (slide 78)

| Exigence du cours | Où c'est fait |
|---|---|
| 3 services indépendants | `user-service/`, `itinerary-service/`, `recommendation-service/` |
| Chaque service possède ses propres données | 1 fichier JSON par service, aucun partage direct |
| Communication synchrone REST inter-services | Recommendation Service → User Service via `requests` |
| API Gateway comme point d'entrée unique | `gateway/app.py` |
| Déployé via Docker Compose | `docker-compose.yml` à la racine |

## Prochaine étape suggérée (Phase 3 du cours)

Containeriser proprement pour le cloud, load balancing, auto-scaling —
mais un service à la fois, seulement une fois que cette Phase 2 tourne
et est validée.
