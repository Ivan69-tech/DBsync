"""
Configuration centralisée pour le synchroniseur PostgreSQL.
Utilise Pydantic pour la validation et le chargement automatique.
Charge les secrets depuis un fichier .env.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Charger les variables d'environnement depuis .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class SqliteConfig(BaseModel):
    """Configuration SQLite source."""

    db_dir: str = Field(
        default="./data/sqlite", description="Répertoire des fichiers SQLite"
    )


class PostgresRemoteConfig(BaseModel):
    """Configuration du serveur PostgreSQL distant."""

    host: str = Field(default="localhost", description="Hôte PostgreSQL")
    port: int = Field(default=5432, description="Port PostgreSQL")
    database: str = Field(default="", description="Nom de la base de données")
    user: str = Field(default="", description="Utilisateur PostgreSQL")
    password: str = Field(default="", description="Mot de passe PostgreSQL")

    @classmethod
    def from_env(cls) -> "PostgresRemoteConfig":
        """
        Crée une configuration PostgreSQL depuis les variables d'environnement.

        Returns:
            PostgresRemoteConfig: Configuration chargée depuis .env
        """
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DATABASE", ""),
            user=os.getenv("POSTGRES_USER", ""),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )


class PostgresqlConfig(BaseModel):
    """Configuration PostgreSQL complète."""

    remote: PostgresRemoteConfig = Field(default_factory=PostgresRemoteConfig)
    table_name: str = Field(
        default="synced_data", description="Nom de la table de destination"
    )


class SyncConfig(BaseModel):
    """Configuration de synchronisation."""

    interval: int = Field(
        default=15, description="Intervalle entre les cycles de sync (secondes)"
    )
    initial_retry_delay: int = Field(
        default=1, description="Délai initial de retry (secondes)"
    )
    max_retry_delay: int = Field(
        default=60, description="Délai maximum de retry (secondes)"
    )
    connect_timeout: int = Field(
        default=10, description="Timeout de connexion (secondes)"
    )


class PathsConfig(BaseModel):
    """Configuration des chemins de fichiers."""

    timestamp_file: str = Field(
        default="./data/lastSuccessFullTime.json",
        description="Fichier de timestamp pour le suivi de la dernière sync",
    )


class Config(BaseModel):
    """Configuration principale du synchroniseur."""

    sqlite: SqliteConfig = Field(default_factory=SqliteConfig)
    postgresql: PostgresqlConfig = Field(default_factory=PostgresqlConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)


def load_config(config_path: Path | None = None) -> Config:
    """
    Charge la configuration depuis le fichier YAML (optionnel) et .env.

    La configuration PostgreSQL est chargée UNIQUEMENT depuis .env.
    Les autres paramètres (SQLite, sync, paths) peuvent venir du YAML ou utiliser les valeurs par défaut.

    Args:
        config_path: Chemin vers le fichier de configuration YAML (optionnel)

    Returns:
        Config: Configuration complète du synchroniseur

    Raises:
        yaml.YAMLError: Si le fichier YAML est invalide
        pydantic.ValidationError: Si la configuration est invalide
        ValueError: Si les variables PostgreSQL requises ne sont pas définies dans .env
    """
    # Initialiser avec les valeurs par défaut
    raw_config: dict[str, Any] = {}

    # Charger depuis YAML si le fichier existe
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}

    # La configuration PostgreSQL vient UNIQUEMENT de .env
    pg_remote_from_env = PostgresRemoteConfig.from_env()

    # Vérifier que les valeurs requises sont présentes
    if not pg_remote_from_env.database:
        raise ValueError("POSTGRES_DATABASE doit être défini dans le fichier .env")
    if not pg_remote_from_env.user:
        raise ValueError("POSTGRES_USER doit être défini dans le fichier .env")
    if not pg_remote_from_env.password:
        raise ValueError("POSTGRES_PASSWORD doit être défini dans le fichier .env")

    # Forcer la configuration PostgreSQL depuis .env
    raw_config["postgresql"] = {
        "remote": pg_remote_from_env.model_dump(),
        "table_name": raw_config.get("postgresql", {}).get("table_name", "synced_data"),
    }

    return Config(**raw_config)
