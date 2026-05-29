# DBsync

Synchroniseur de données SQLite → PostgreSQL avec suivi par timestamp pour éviter les doublons.

## Description

DBsync est un outil de synchronisation qui lit des données depuis des fichiers SQLite organisés par date (format `YYYY_MM_DD.db`) et les synchronise vers une base de données PostgreSQL. Le système utilise un mécanisme de timestamp par connecteur pour ne synchroniser que les nouvelles données et éviter les doublons.

## Fonctionnalités

- Synchronisation automatique SQLite → PostgreSQL
- Gestion des timestamps pour éviter les doublons
- Reconnexion automatique en cas de perte de connexion
- Support de fichiers SQLite organisés par date
- Architecture modulaire avec pattern Factory
- Configuration via YAML et variables d'environnement
- Multi-connecteurs : plusieurs synchronisations indépendantes en parallèle

## Installation

### Prérequis

- Python 3.9+
- PostgreSQL
- Fichiers SQLite au format `YYYY_MM_DD.db`

### Installation des dépendances

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Fichier `config.yaml`

```yaml
sqlite_db_dir: "/etc/data/sqlite"
sync_interval_seconds: 15
env_file_path: ".env"

connectors:
  - type: "ppc"
    timestamp_file_path: "/etc/timestamp/ppc_last_ts.json"
  # - type: "forecaster"
  #   timestamp_file_path: "/etc/timestamp/forecaster_last_ts.json"
  #   key_mapping:
  #     bess_0_p: puissance_bess_kw
  #     pv_0_p: production_pv_kw
  #     conso_kw: conso_kw
  #     soc_kwh: soc_kwh
```

### 2. Fichier `.env`

Créez un fichier `.env` (chemin défini par `env_file_path`) :

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=mydb
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin
```

## Utilisation

### Exécution directe

```bash
python internal/main.py --config_path config.yaml
```

### Avec Docker

```bash
docker-compose -f docker/docker-compose.yml up -d
```

Le conteneur utilise `config_docker.yaml` par défaut.

## Architecture

```text
DBsync/
├── internal/
│   ├── config/          # Gestion de la configuration (Pydantic)
│   ├── connectors/      # Connecteurs (pattern Factory)
│   ├── sqlite/          # Utilitaires SQLite
│   ├── synchronizer/    # Logique de synchronisation
│   ├── tests/           # Tests unitaires
│   ├── volume/          # Gestion des timestamps
│   └── main.py          # Point d'entrée
├── docker/              # Dockerfile et docker-compose
├── config.yaml          # Configuration locale
└── config_docker.yaml   # Configuration Docker
```

### Flux de synchronisation

1. **Chargement** : Lecture du dernier timestamp depuis `timestamp_file_path`
2. **Extraction** : Récupération des données SQLite avec `timestamp > last_timestamp`
3. **Insertion** : Insertion en batch dans PostgreSQL avec gestion des doublons
4. **Mise à jour** : Sauvegarde du nouveau timestamp

## Connecteurs disponibles

### PPC Connector (`type: "ppc"`)

Synchronise les datapoints bruts du PPC vers la table `ppc_raw` (format key-value).

| Colonne | Type |
|---------|------|
| `site_id` | TEXT |
| `key` | TEXT |
| `timestamp` | DOUBLE PRECISION |
| `type` | TEXT |
| `value` | TEXT |
| PRIMARY KEY | `(site_id, key, timestamp)` |

### PSN Connector (`type: "psn"`)

Synchronise les données de prix vers la table `prices`.

| Colonne | Type |
|---------|------|
| `start_date` | TEXT NOT NULL |
| `end_date` | TEXT NOT NULL |
| `price` | REAL NOT NULL |
| `volume` | REAL NOT NULL |
| PRIMARY KEY | `(start_date, end_date)` |

### Forecaster Connector (`type: "forecaster"`)

Lit les datapoints bruts du PPC (table SQLite nommée d'après le site), pivote les clés selon un mapping YAML, et insère dans la table `mesures_reelles` du Forecaster.

- Regroupe les rows par timestamp
- N'insère que les timestamps pour lesquels **toutes** les clés du mapping sont présentes
- `puissance_pdl_kw` est défaut à `0.0` si absent du mapping
- Upsert sur `(site_id, timestamp)`

Configuration dans `config.yaml` :

```yaml
connectors:
  - type: "forecaster"
    timestamp_file_path: "/etc/timestamp/forecaster_last_ts.json"
    key_mapping:
      bess_0_p: puissance_bess_kw
      pv_0_p: production_pv_kw
      conso_kw: conso_kw
      soc_kwh: soc_kwh
```

## Ajouter un nouveau connecteur

1. Implémenter `ConnectorInterface` dans `internal/connectors/`
2. Enregistrer dans `internal/connectors/connectors_factory.py`
3. Ajouter l'entrée correspondante dans `config.yaml`

## Licence

Projet personnel
