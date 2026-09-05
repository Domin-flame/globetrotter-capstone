# Dzula — Guide local de Yaoundé

Dzula est une application de découverte touristique centrée sur Yaoundé. Elle
propose un catalogue de lieux, d'hébergements, de restaurants et de plats
camerounais, avec une expérience éditoriale inspirée des guides locaux comme
MboaTrip.

L'application est construite autour de services Flask indépendants, d'un API
Gateway et d'une interface web servie sur une seule URL.

## Fonctionnalités

- Page d'accueil éditoriale dédiée à Yaoundé : quartiers, culture, marchés et collines.
- Catalogue de 27 entrées actuellement disponibles :
  - attractions et lieux culturels ;
  - hébergements ;
  - restaurants ;
  - plats locaux.
- Recherche plein texte, filtres par catégorie, quartier, tag et budget.
- Carte interactive Leaflet/OpenStreetMap de Yaoundé avec recherche, filtres,
  marqueurs et accès aux fiches détaillées.
- Fiches détaillées avec photos, transport, moyens de paiement, événements et avis.
- Comptes utilisateurs avec JWT, préférences et recommandations personnalisées.
- Tableau de bord utilisateur avec recommandations, itinéraires et favoris.
- Création et consultation d'itinéraires personnels.
- Favoris persistants par utilisateur.
- Chat communautaire temps réel avec Socket.IO :
  - messages texte ;
  - partage d'images et de fichiers audio ;
  - commentaires sur les messages partagés ;
  - historique persistant.
- Interface responsive avec navigation centrée, menu mobile et sélecteur FR/EN.
- Fallback et proxy d'images pour limiter les problèmes de hotlink avec les
  fournisseurs d'images externes.

## Architecture

```text
Navigateur
    |
    v
API Gateway :5000
    |-- User Service            :5001 -> user-service/data/users.json
    |-- Itinerary Service       :5002 -> itinerary-service/data/itineraries.json
    |-- Recommendation Service  :5003 -> recommendation-service/data/*.json
    |-- Chat Service             :5004 -> chat-service/data/messages.json
    |                              -> chat-service/data/media/
    |
    `-- Frontend : gateway/static/index.html
```

Le Gateway est le point d'entrée HTTP principal. Le chat utilise également une
connexion Socket.IO persistante vers le Chat Service, car une connexion
WebSocket ne peut pas être relayée par le proxy HTTP classique du Gateway.

## Services

### User Service

Gère l'inscription, la connexion JWT, les préférences utilisateur et les
routes d'administration.

- `POST /register`
- `POST /login`
- `GET /preferences`
- `PUT /preferences`
- `GET /internal/preferences/<username>`

### Itinerary Service

Gère les itinéraires privés, isolés par utilisateur.

- `GET /itineraries`
- `POST /itineraries`

### Recommendation Service

Gère le catalogue Yaoundé, les recommandations, les favoris, les avis et les
événements.

- `GET /destinations`
- `GET /recommendations`
- `GET /favorites`
- `POST /favorites/<destination_id>`
- `DELETE /favorites/<destination_id>`
- `GET /destinations/<destination_id>/reviews`
- `POST /destinations/<destination_id>/reviews`
- `GET /destinations/<destination_id>/events`
- `POST /destinations/<destination_id>/events`

Les recommandations appellent réellement le User Service pour récupérer les
préférences de l'utilisateur connecté.

### Chat Service

Gère l'historique, les connexions Socket.IO, les médias et les commentaires.

- `GET /messages`
- `POST /uploads`
- `GET /media/<filename>`
- `POST /messages/<message_id>/comments`
- Socket.IO : `connect`, `send_message`, `new_message`, `message_comment`

Les fichiers envoyés sont limités aux formats image JPEG/PNG/WebP et audio
MP3/WAV/OGG/M4A, avec une taille maximale de 15 Mo.

## Lancer avec Docker Compose

Depuis la racine du dépôt :

```bash
docker compose up --build
```

Ouvrir ensuite :

```text
http://localhost:5000/
```

Vérifier l'état des services :

```text
http://localhost:5000/health
```

Arrêter les conteneurs :

```bash
docker compose down
```

Les fichiers JSON sont montés comme volumes Docker afin de conserver les
données pendant les redémarrages. Le Chat Service monte également son dossier
`data/` pour conserver l'historique et les médias partagés.

## Lancer sans Docker

Installer les dépendances de chaque service, puis lancer les cinq processus
dans des terminaux séparés :

```bash
cd user-service && pip install -r requirements.txt && python app.py
cd itinerary-service && pip install -r requirements.txt && python app.py
cd recommendation-service && pip install -r requirements.txt && python app.py
cd chat-service && pip install -r requirements.txt && python app.py
cd gateway && pip install -r requirements.txt && python app.py
```

Les valeurs par défaut utilisent `localhost` et les ports `5001` à `5004`.
Pour Docker, les variables de service sont configurées dans
`docker-compose.yml`.

## Variables d'environnement

Les variables principales sont :

| Variable | Valeur par défaut | Utilisation |
|---|---|---|
| `JWT_SECRET` | `dev-secret-change-me` | Signature des jetons JWT partagés |
| `USER_SERVICE_URL` | `http://localhost:5001` | URL du User Service |
| `ITINERARY_SERVICE_URL` | `http://localhost:5002` | URL de l'Itinerary Service |
| `RECOMMENDATION_SERVICE_URL` | `http://localhost:5003` | URL du Recommendation Service |
| `CHAT_SERVICE_URL` | `http://localhost:5004` | URL du Chat Service |
| `ADMIN_USERNAMES` | vide | Liste CSV des utilisateurs administrateurs |
| `PORT` | `5000` ou `5004` | Port du service lancé |

En production, remplacer impérativement le secret JWT de développement et
prévoir un stockage persistant et protégé pour les médias du chat.

## Tests et validation

Lancer la suite actuelle :

```bash
pytest -q
```

La suite couvre notamment l'inscription, la connexion, les recherches, les
filtres du catalogue, les recommandations, les itinéraires et l'isolation des
données par utilisateur.

Vérifications utiles :

```bash
python -m py_compile gateway/app.py chat-service/app.py
docker compose config
```

## Structure principale

```text
gateway/
  app.py
  static/index.html
user-service/
itinerary-service/
recommendation-service/
  data/destinations.json
  data/favorites.json
chat-service/
  app.py
  data/messages.json
tests/
  test_api.py
docker-compose.yml
```

## Notes de production

- Les coordonnées de la carte sont des points de quartier actuellement
  associés au catalogue Yaoundé ; elles pourront être remplacées par des
  coordonnées précises pour chaque lieu.
- Les photos du catalogue proviennent de sources externes. Le Gateway les
  récupère via une allowlist et applique un fallback local si une source n'est
  plus disponible.
- Le sélecteur français/anglais couvre actuellement la navigation, la page
  d'accueil, la carte et le tableau de bord. La traduction complète du contenu
  éditorial et des messages sera ajoutée progressivement.
