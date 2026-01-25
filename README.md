# Synchroniseur SQLite vers PostgreSQL

Un outil simple pour synchroniser automatiquement des bases de données SQLite quotidiennes vers une base PostgreSQL distante.

## Fonctionnalités

- **Détection automatique des colonnes** : Le système découvre automatiquement la structure de vos tables SQLite
- **Bases quotidiennes** : Supporte les fichiers SQLite nommés au format `YYYY_MM_DD.db` (ex: `2026_01_25.db`)
- **Synchronisation incrémentale** : Ne synchronise que les nouvelles données depuis le dernier timestamp
- **Création automatique de table** : La table PostgreSQL est créée automatiquement avec les bonnes colonnes
- **Ajout dynamique de colonnes** : Si de nouvelles colonnes apparaissent dans SQLite, elles sont ajoutées à PostgreSQL
- **Performance optimale** : Utilise `execute_values` de psycopg2 pour des insertions en masse rapides
- **Gestion des doublons** : Utilise `ON CONFLICT DO NOTHING` pour éviter les doublons automatiquement
- **Robuste** : Gestion des erreurs, reconnexion automatique avec backoff exponentiel, transactions atomiques
- **Docker-ready** : Prêt pour le déploiement avec Docker et Docker Compose

## Prérequis

- Python 3.10+
- PostgreSQL (serveur distant)
- Bases SQLite avec des données horodatées
- Fichier `synchronizer/data/lastSuccessFullTime.json` initialisé (voir section Dépannage)

## Installation

1. Cloner le projet :

```bash
cd /home/deploy/Bureau/perso/postgresql
```

1. Créer un environnement virtuel et installer les dépendances :

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r synchronizer/requirements.txt
```

1. Configurer les fichiers de configuration :

```bash
cd synchronizer
# Copier le template .env et le remplir avec vos identifiants PostgreSQL (REQUIS)
cp .env.example .env
nano .env

# Configurer les autres paramètres (optionnel - utilise les valeurs par défaut si absent)
nano config.yaml
```

## Configuration

### Fichier .env (REQUIS pour PostgreSQL)

Le fichier `.env` contient **toutes les informations de connexion PostgreSQL** et n'est **pas versionné** par git pour des raisons de sécurité.

**⚠️ IMPORTANT** : La configuration PostgreSQL vient **UNIQUEMENT** du fichier `.env`. Le fichier `config.yaml` ne contient plus ces informations.

Copiez `.env.example` vers `.env` et remplissez les valeurs :

```env
# Configuration PostgreSQL (REQUIS)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=mydb
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
```

**Variables requises** :

- `POSTGRES_DATABASE` : Nom de la base de données (requis)
- `POSTGRES_USER` : Utilisateur PostgreSQL (requis)
- `POSTGRES_PASSWORD` : Mot de passe PostgreSQL (requis)
- `POSTGRES_HOST` : Hôte PostgreSQL (défaut: localhost)
- `POSTGRES_PORT` : Port PostgreSQL (défaut: 5432)

### Fichier config.yaml (optionnel)

Le fichier `config.yaml` est **optionnel**. S'il n'existe pas, les valeurs par défaut seront utilisées. Il permet de configurer les autres paramètres :

Éditer le fichier `synchronizer/config.yaml` :

```yaml
# Configuration SQLite source
sqlite:
  # Répertoire contenant vos fichiers .db quotidiens (format: YYYY_MM_DD.db)
  db_dir: "~/Bureau/perso/ppc/db"
  # Nom de la table SQLite (optionnel, auto-détection si non spécifié)
  table_name: null

# Configuration PostgreSQL destination
# ⚠️ Les informations de connexion viennent UNIQUEMENT de .env
# Seul le nom de la table peut être configuré ici
postgresql:
  # Nom de la table PostgreSQL de destination
  table_name: "synced_data"

# Configuration de synchronisation
sync:
  # Intervalle entre les cycles de sync (secondes)
  interval: 15
  # Délai initial de retry (secondes)
  initial_retry_delay: 1
  # Délai maximum de retry (secondes)
  max_retry_delay: 60
  # Timeout de connexion (secondes)
  connect_timeout: 10

# Chemins de fichiers
paths:
  # Fichier de timestamp pour le suivi de la dernière sync
  timestamp_file: "synchronizer/data/lastSuccessFullTime.json"
```

## Structure des données

### Bases SQLite attendues

- **Format de fichier** : `YYYY_MM_DD.db` (ex: `2026_01_25.db`)
- **Emplacement** : Dans le répertoire défini par `sqlite.db_dir` dans `config.yaml`
- **Table** : Une table avec au moins une colonne contenant "time" ou "date" dans son nom (insensible à la casse)
- **Colonnes** : Peuvent être de n'importe quel type (découvertes automatiquement depuis le premier fichier)

Exemple de structure SQLite :

```sql
CREATE TABLE "pc-test" (
    timestamp TIMESTAMP,
    temperature REAL,
    humidity INTEGER,
    status TEXT
);
```

### Table PostgreSQL résultante

La table PostgreSQL sera créée automatiquement avec les mêmes colonnes et une contrainte UNIQUE sur toutes les colonnes pour éviter les doublons :

```sql
CREATE TABLE synced_data (
    timestamp TIMESTAMP,
    temperature DOUBLE PRECISION,
    humidity BIGINT,
    status TEXT,
    UNIQUE (timestamp, temperature, humidity, status)
);
```

**Note** : La contrainte UNIQUE est créée automatiquement sur toutes les colonnes pour permettre l'utilisation de `ON CONFLICT DO NOTHING` lors des insertions.

## Utilisation

### Lancer la synchronisation en continu

```bash
cd synchronizer
python main.py
```

Le programme va :

1. Charger la configuration depuis `.env` (PostgreSQL) et `config.yaml` (optionnel)
2. Se connecter à PostgreSQL (avec retry automatique en cas d'échec)
3. Scanner les fichiers `.db` dans le répertoire configuré (`sqlite.db_dir`)
4. Découvrir la structure de la première table trouvée
5. Créer/mettre à jour la table PostgreSQL avec les colonnes détectées
6. Synchroniser les nouvelles données depuis le dernier timestamp
7. Répéter la synchronisation toutes les N secondes (configuré via `sync.interval`)

### Utilisation avec Docker

```bash
# Construire et lancer avec Docker Compose
docker-compose up -d

# Voir les logs en temps réel
docker-compose logs -f synchronizer

# Arrêter le service
docker-compose down
```

**Note** : Avant de lancer avec Docker, assurez-vous de :

- Créer le fichier `.env` avec les identifiants PostgreSQL (voir section Configuration)
- Configurer `config.yaml` avec les bons chemins (optionnel)
- Créer le fichier `synchronizer/data/lastSuccessFullTime.json` si nécessaire
- Monter le volume contenant vos fichiers SQLite dans `docker-compose.yml` (remplacer `/path/to/your/sqlite/dbs`)

## Logs

Le programme utilise un système de logging structuré avec les niveaux suivants :

- **INFO** : Opérations normales (démarrage, synchronisation, connexions)
- **WARNING** : Avertissements (fichiers manquants, doublons)
- **ERROR** : Erreurs avec stack traces pour le débogage
- **DEBUG** : Informations de débogage détaillées

Format des logs : `YYYY-MM-DD HH:MM:SS [LEVEL] module: message`

## Gestion des erreurs

- **Perte de connexion** : Reconnexion automatique avec backoff exponentiel
- **Fichiers SQLite manquants** : Ignorés avec avertissement
- **Tables vides** : Pas d'erreur, simple message informatif
- **Erreurs d'insertion** : Rollback automatique, transaction atomique

## Paramètres avancés

Dans `config.yaml`, vous pouvez ajuster :

- `sync.interval` : Intervalle entre synchronisations (défaut: 15s)
- `sync.connect_timeout` : Timeout de connexion PostgreSQL (défaut: 10s)
- `sync.initial_retry_delay` : Délai initial avant nouvelle tentative de reconnexion (défaut: 1s)
- `sync.max_retry_delay` : Délai maximum entre tentatives de reconnexion (défaut: 60s)
- `sqlite.db_dir` : Répertoire contenant les fichiers SQLite quotidiens
- `sqlite.table_name` : Nom de la table SQLite (null pour auto-détection)
- `postgresql.table_name` : Nom de la table PostgreSQL de destination
- `paths.timestamp_file` : Chemin du fichier de suivi du dernier timestamp

## Structure du projet

```
postgresql/
├── synchronizer/
│   ├── __init__.py              # Point d'entrée du module
│   ├── main.py                  # Script principal
│   ├── config.py                # Configuration centralisée (Pydantic)
│   ├── config.yaml              # Fichier de configuration YAML (optionnel)
│   ├── .env                     # Configuration PostgreSQL (non versionné, REQUIS)
│   ├── .env.example             # Template pour .env
│   ├── synchronizer.py          # Logique de synchronisation
│   ├── database.py              # Gestion PostgreSQL
│   ├── sqlite_manager.py        # Gestion SQLite
│   ├── file_manager.py          # Gestion des timestamps
│   ├── validator.py             # Validation des données (non utilisé actuellement)
│   ├── requirements.txt         # Dépendances Python
│   ├── Dockerfile               # Image Docker
│   └── data/
│       └── lastSuccessFullTime.json  # Fichier de suivi du timestamp
├── docker-compose.yml           # Configuration Docker Compose
└── README.md
```

## Dépannage

### Erreur "POSTGRES_* doit être défini dans le fichier .env"

- Créer le fichier `.env` en copiant `.env.example` : `cp .env.example .env`
- Remplir toutes les variables requises :
  - `POSTGRES_DATABASE` (requis)
  - `POSTGRES_USER` (requis)
  - `POSTGRES_PASSWORD` (requis)
  - `POSTGRES_HOST` (optionnel, défaut: localhost)
  - `POSTGRES_PORT` (optionnel, défaut: 5432)

### Erreur de connexion PostgreSQL

- **Vérifier que le fichier `.env` existe** dans le répertoire `synchronizer/`
- **Vérifier que toutes les variables requises sont définies** dans `.env`
- Vérifier que PostgreSQL accepte les connexions distantes (fichier `pg_hba.conf`)
- Vérifier le pare-feu et que le port 5432 est ouvert
- Vérifier que le serveur PostgreSQL est démarré

### Erreur "Aucun fichier SQLite trouvé"

- Vérifier que `sqlite.db_dir` dans `config.yaml` pointe vers le bon répertoire
- Vérifier que les fichiers sont au format `YYYY_MM_DD.db` (ex: `2026_01_25.db`)
- Vérifier que le chemin utilise `~` pour le répertoire home ou un chemin absolu

### Erreur "Aucune colonne timestamp trouvée"

- La table SQLite doit avoir une colonne contenant "time" ou "date" dans son nom (insensible à la casse)
- Renommer votre colonne temporelle en conséquence (ex: `timestamp`, `datetime`, `date_time`)

### Erreur "Aucune colonne key trouvée"

- La table SQLite doit avoir une colonne contenant "key", "id", "register" ou "name" dans son nom
- Renommer votre colonne clé en conséquence

### Erreur "Fichier timestamp introuvable"

- Créer le fichier `synchronizer/data/lastSuccessFullTime.json` avec le format :

  ```json
  {"lastSuccessFullTime": "2026-01-23 10:05:06.894054"}
  ```

- Utiliser une date antérieure à vos données SQLite pour une première synchronisation complète
