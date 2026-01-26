"""
Point d'entrée principal du synchroniseur SQLite -> PostgreSQL.
"""

import logging
import sys
import time

import psycopg2
from psycopg2.extensions import connection

from config.config import load_config
from connectors.connectors_factory import connector_factory
from synchronizer import synchronize_data

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
    logger.info("Démarrage du synchroniseur SQLite -> PostgreSQL")

    # Charger la configuration
    config = load_config()

    # Configuration PostgreSQL
    pg_config = config.postgresql.remote
    sync_config = config.sync
    connector = connector_factory("ppc")

    # Connexion initiale à PostgreSQL
    conn_remote: connection = connector.connect(
        pg_config.database,
        pg_config.user,
        pg_config.password,
        pg_config.host,
        pg_config.port,
    )

    # Boucle principale de synchronisation
    # Note: La table sera créée automatiquement lors de la première synchronisation
    retry_delay = 10
    while True:
        try:
            synchronize_data(conn_remote, config, connector)
            time.sleep(sync_config.interval)

        except psycopg2.OperationalError as e:
            logger.warning(
                f"Perte de connexion PostgreSQL: {e}. Tentative de reconnexion..."
            )
            connector.disconnect(conn_remote)

            # Reconnexion
            conn_remote = connector.connect(
                pg_config.database,
                pg_config.user,
                pg_config.password,
                pg_config.host,
                pg_config.port,
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
