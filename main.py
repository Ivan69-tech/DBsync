"""
Point d'entrée principal du synchroniseur SQLite -> PostgreSQL.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection

from config.config import load_config
from connectors.connectors_factory import connector_factory
from synchronizer.synchronizer import synchronize_data
from sqlite.sqlite import get_table_name_from_db_dir

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Pour voir les logs en temps réel dans Docker
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
sys.stdout.flush()

logger = logging.getLogger(__name__)


def main():
    """Fonction principale du synchroniseur."""
    # Parser les arguments de ligne de commande
    parser = argparse.ArgumentParser(
        description="Synchroniseur SQLite -> PostgreSQL"
    )
    parser.add_argument(
        "--config_path",
        type=str,
        default=None,
        help="Chemin vers le fichier de configuration YAML (par défaut: config.yaml à la racine)",
    )
    args = parser.parse_args()

    logger.info("Démarrage du synchroniseur SQLite -> PostgreSQL")

    # Charger la configuration
    config_path = Path(args.config_path) if args.config_path else None
    config = load_config(config_path)

    connector = connector_factory("ppc")

    # Connexion initiale à PostgreSQL
    conn_remote: connection = connector.connect(
        config.postgres_database,
        config.postgres_user,
        config.postgres_password,
        config.postgres_host,
        config.postgres_port,
    )

    table_name = get_table_name_from_db_dir(config.sqlite_db_dir)
    if not table_name:
        logger.error(f"Aucune table SQLite trouvée dans {config.sqlite_db_dir}")
        sys.exit(1)
    logger.info(f"Table SQLite détectée: {table_name}")

    # Boucle principale de synchronisation
    # Note: La table sera créée automatiquement lors de la première synchronisation
    retry_delay = 10
    while True:
        try:
            synchronize_data(conn_remote, config, connector, table_name)
            time.sleep(config.sync_interval_seconds)

        except psycopg2.OperationalError as e:
            logger.warning(
                f"Perte de connexion PostgreSQL: {e}. Tentative de reconnexion..."
            )
            connector.disconnect(conn_remote)

            # Reconnexion
            conn_remote = connector.connect(
                config.postgres_database,
                config.postgres_user,
                config.postgres_password,
                config.postgres_host,
                config.postgres_port,
            )

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur")
            connector.disconnect(conn_remote)
            break

        except Exception as e:
            logger.error(f"Erreur inattendue: {e}", exc_info=True)
            time.sleep(retry_delay)


if __name__ == "__main__":
    main()
