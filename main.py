"""
Point d'entrée principal du synchroniseur SQLite -> PostgreSQL.
"""

import logging
import sys
import time

import psycopg2

from config import load_config
from database import close_connection, connect_postgres
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

    # Connexion initiale à PostgreSQL
    conn_remote = connect_postgres(
        pg_config.database,
        pg_config.user,
        pg_config.password,
        pg_config.host,
        pg_config.port,
        sync_config,
    )

    # Boucle principale de synchronisation
    # Note: La table sera créée automatiquement lors de la première synchronisation
    retry_delay = sync_config.initial_retry_delay
    while True:
        try:
            success = synchronize_data(conn_remote, config)
            if success:
                retry_delay = sync_config.initial_retry_delay
            time.sleep(sync_config.interval)

        except psycopg2.OperationalError as e:
            logger.warning(
                f"Perte de connexion PostgreSQL: {e}. Tentative de reconnexion..."
            )
            close_connection(conn_remote)

            # Reconnexion avec backoff exponentiel
            conn_remote = connect_postgres(
                pg_config.database,
                pg_config.user,
                pg_config.password,
                pg_config.host,
                pg_config.port,
                sync_config,
                retry_delay,
            )

            # Réinitialiser le délai après reconnexion réussie
            retry_delay = sync_config.initial_retry_delay

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur")
            close_connection(conn_remote)
            break

        except Exception as e:
            logger.error(f"Erreur inattendue: {e}", exc_info=True)
            # Augmenter le délai avant la prochaine tentative
            retry_delay = min(retry_delay * 2, sync_config.max_retry_delay)
            time.sleep(retry_delay)


if __name__ == "__main__":
    main()
