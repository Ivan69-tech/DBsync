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

from config.config import Config, ConnectorConfig, load_config
from connectors.connectors_factory import connector_factory
from connectors.connectors_interface import ConnectorInterface
from sqlite.sqlite import get_table_name_from_db_dir
from synchronizer.synchronizer import synchronize_data

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


def _pg_connect(connector: ConnectorInterface, config: Config) -> connection:
    return connector.connect(
        config.postgres_database,
        config.postgres_user,
        config.postgres_password,
        config.postgres_host,
        config.postgres_port,
    )


def main():
    """Fonction principale du synchroniseur."""
    parser = argparse.ArgumentParser(description="Synchroniseur SQLite -> PostgreSQL")
    parser.add_argument(
        "--config_path",
        type=str,
        default=None,
        help="Chemin vers le fichier de configuration YAML",
    )
    args = parser.parse_args()

    logger.info("Démarrage du synchroniseur SQLite -> PostgreSQL")

    config_path = Path(args.config_path) if args.config_path else None
    config = load_config(config_path)

    table_name = None
    while table_name is None:
        table_name = get_table_name_from_db_dir(config.sqlite_db_dir)
        if not table_name:
            logger.error(f"Aucune table SQLite trouvée dans {config.sqlite_db_dir}")
            time.sleep(config.sync_interval_seconds)
    logger.info(f"Table SQLite détectée (site_id): {table_name}")

    # Initialiser un connector + une connexion PG par entrée de config
    # active[i] = (connector, conn_remote, timestamp_file_path)
    active: list[tuple[ConnectorInterface, connection, str]] = []
    for cc in config.connectors:
        connector = connector_factory(cc.type, site_id=table_name, key_mapping=cc.key_mapping)
        conn = _pg_connect(connector, config)
        active.append((connector, conn, cc.timestamp_file_path))
        logger.info(f"Connector '{cc.type}' initialisé (ts: {cc.timestamp_file_path})")

    retry_delay = 10
    while True:
        try:
            for i, (connector, conn_remote, ts_path) in enumerate(active):
                try:
                    if conn_remote.closed:
                        logger.warning(f"Connexion PostgreSQL fermée pour '{config.connectors[i].type}'. Reconnexion...")
                        conn_remote = _pg_connect(connector, config)
                        active[i] = (connector, conn_remote, ts_path)

                    synchronize_data(conn_remote, config, connector, table_name, ts_path)

                except psycopg2.Error as e:
                    logger.warning(f"Erreur PostgreSQL ({config.connectors[i].type}): {e}. Reconnexion...")
                    connector.disconnect(conn_remote)
                    conn_remote = _pg_connect(connector, config)
                    active[i] = (connector, conn_remote, ts_path)

            time.sleep(config.sync_interval_seconds)

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur")
            for connector, conn_remote, _ in active:
                connector.disconnect(conn_remote)
            break

        except Exception as e:
            logger.error(f"Erreur inattendue: {e}", exc_info=True)
            time.sleep(retry_delay)


if __name__ == "__main__":
    main()
