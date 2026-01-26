# DBsync

Synchroniseur de données SQLite → PostgreSQL avec suivi par timestamp pour éviter les doublons.

## Description

DBsync est un outil de synchronisation qui lit des données depuis des fichiers SQLite organisés par date (format `YYYY_MM_DD.db`) et les synchronise vers une base de données PostgreSQL. Le système utilise un mécanisme de timestamp pour ne synchroniser que les nouvelles données et éviter les doublons.

## Fonctionnalités

- ✅ Synchronisation automatique SQLite → PostgreSQL
- ✅ Gestion des timestamps pour éviter les doublons
- ✅ Reconnexion automatique en cas de perte de connexion
- ✅ Support de fichiers SQLite organisés par date
- ✅ Architecture modulaire avec pattern Factory
- ✅ Configuration via YAML et variables d'environnement

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
sqlite_db_dir: "~/Bureau/perso/ppc/db"
sync_interval_seconds: 15
timestamp_file_path: "./timestamp/last_successful_time.json"
```

### 2. Fichier `.env`

Créez un fichier `.env` à la racine du projet :

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
python main.py
```

### Avec Docker

```bash
docker-compose up -d
```

## Architecture

Le projet suit une architecture modulaire :

```
DBsync/
├── config/          # Gestion de la configuration (Pydantic)
├── connectors/      # Connecteurs (pattern Factory)
├── sqlite/          # Utilitaires SQLite
├── synchronizer/    # Logique de synchronisation
├── volume/          # Gestion des timestamps
└── main.py          # Point d'entrée
```

### Flux de synchronisation

1. **Chargement** : Lecture du dernier timestamp depuis `timestamp_file_path`
2. **Extraction** : Récupération des données SQLite avec `timestamp > last_timestamp`
3. **Insertion** : Insertion en batch dans PostgreSQL avec gestion des doublons
4. **Mise à jour** : Sauvegarde du nouveau timestamp

## Développement

### Ajouter un nouveau connecteur

1. Implémenter `ConnectorInterface` dans `connectors/`
2. Enregistrer dans `connectors_factory.py`
3. Utiliser via `connector_factory("nom_connecteur")`

## Licence

Projet personnel

## Bug fix

1. logs des doublons qui n'a pas l'air bon
2. gestion d'erreur si pas de fichier timestamp (quitter le logiciel)
3. perte de connexion avec la base
4. vérifier la bonne connexion même si pas de données à envoyer.
5. Si table supprimée pendant que c'est en cours --> probleme.
