"""
Configuration centralisée pour le synchroniseur PostgreSQL.
Utilise Pydantic pour la validation et le chargement automatique.
Charge les secrets depuis un fichier .env.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Charger les variables d'environnement depuis .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


class Config(BaseModel):
    """Configuration principale du synchroniseur."""

    # Configuration SQLite
    sqlite_db_dir: str = Field(description="Répertoire des fichiers SQLite")

    # Configuration PostgreSQL (depuis .env)
    postgres_host: str = Field(description="Hôte PostgreSQL")
    postgres_port: int = Field(description="Port PostgreSQL")
    postgres_database: str = Field(description="Nom de la base de données")
    postgres_user: str = Field(description="Utilisateur PostgreSQL")
    postgres_password: str = Field(description="Mot de passe PostgreSQL")

    # Configuration synchronisation
    sync_interval_seconds: int = Field(
        default=15, description="Intervalle entre les cycles de sync (secondes)"
    )

    # env file
    env_file_path: str = Field(description="Fichier .env")

    # Configuration chemins
    timestamp_file_path: str = Field(
        description="Fichier de timestamp pour le suivi de la dernière sync",
    )

    @classmethod
    def load_from_yaml_and_env(cls, config_path: Path | None = None) -> "Config":
        """
        Charge la configuration depuis le fichier YAML et .env.

        Args:
            config_path: Chemin vers le fichier de configuration YAML (optionnel)

        Returns:
            Config: Configuration complète du synchroniseur

        Raises:
            SystemExit: Si un champ requis est manquant ou invalide
        """
        # Charger depuis YAML si le fichier existe
        raw_config: dict[str, Any] = {}

        if config_path is None:
            print(
                "ERREUR: config_path doit être défini",
                file=sys.stderr,
            )
            sys.exit(1)

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    raw_config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Erreur lors du chargement du fichier YAML: {e}")
                sys.exit(1)

        sqlite_db_dir = raw_config.get("sqlite_db_dir")
        if not sqlite_db_dir:
            print(
                "ERREUR: sqlite_db_dir doit être défini dans config.yaml",
                file=sys.stderr,
            )
            sys.exit(1)

        env_file_path = raw_config.get("env_file_path")
        if not env_file_path:
            print(
                "ERREUR: env_file_path doit être défini dans config.yaml",
                file=sys.stderr,
            )
            sys.exit(1)

        env_path = Path(env_file_path).expanduser().resolve()
        if not env_path.exists():
            logger.error(
                f"ERREUR: Le fichier .env n'existe pas au chemin spécifié : {env_path}"
            )
            sys.exit(1)
        load_dotenv(dotenv_path=env_path)

        # Charger la configuration PostgreSQL depuis .env
        postgres_host = os.getenv("POSTGRES_HOST")
        postgres_port = os.getenv("POSTGRES_PORT")
        postgres_database = os.getenv("POSTGRES_DATABASE")
        postgres_user = os.getenv("POSTGRES_USER")
        postgres_password = os.getenv("POSTGRES_PASSWORD")

        # Vérifier que toutes les variables PostgreSQL sont présentes
        if not postgres_host:
            logger.error("ERREUR: POSTGRES_HOST doit être défini dans le fichier .env")
            sys.exit(1)
        if not postgres_port:
            logger.error("ERREUR: POSTGRES_PORT doit être défini dans le fichier .env")
            sys.exit(1)
        if not postgres_database:
            logger.error(
                "ERREUR: POSTGRES_DATABASE doit être défini dans le fichier .env"
            )
            sys.exit(1)
        if not postgres_user:
            logger.error("ERREUR: POSTGRES_USER doit être défini dans le fichier .env")
            sys.exit(1)
        if not postgres_password:
            logger.error(
                "ERREUR: POSTGRES_PASSWORD doit être défini dans le fichier .env"
            )
            sys.exit(1)

        # Construire la configuration complète
        try:
            return cls(
                sqlite_db_dir=str(sqlite_db_dir),
                env_file_path=str(env_file_path),
                postgres_host=str(postgres_host),
                postgres_port=int(postgres_port),
                postgres_database=str(postgres_database),
                postgres_user=str(postgres_user),
                postgres_password=str(postgres_password),
                sync_interval_seconds=raw_config.get("sync_interval_seconds", 15),
                timestamp_file_path=raw_config.get(
                    "timestamp_file_path", "synchronizer/data/lastSuccessFullTime.json"
                ),
            )
        except Exception as e:
            logger.error(f"ERREUR lors de la validation de la configuration: {e}")
            sys.exit(1)


def load_config(config_path: Path | None = None) -> Config:
    """
    Charge la configuration depuis le fichier YAML et .env.

    Args:
        config_path: Chemin vers le fichier de configuration YAML (optionnel)

    Returns:
        Config: Configuration complète du synchroniseur
    """
    return Config.load_from_yaml_and_env(config_path)
