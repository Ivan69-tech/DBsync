"""
Logique principale de synchronisation SQLite -> PostgreSQL.
"""

import logging
from datetime import timedelta

import psycopg2
from psycopg2.extensions import connection

from config.config import Config
from connectors.connectors_interface import ConnectorInterface
from volume.volume import load_last_timestamp, save_timestamp

logger = logging.getLogger(__name__)


def synchronize_data(
    conn_remote: connection,
    config: Config,
    connector: ConnectorInterface,
    table_name: str,
) -> None:
    """
    Synchronise les données de SQLite vers PostgreSQL.

    Args:
        conn_remote: Connexion à la base PostgreSQL distante
        config: Configuration complète
        connector: Connecteur pour les opérations SQLite et PostgreSQL
    """
    try:
        # Charger le dernier timestamp
        last_successful_time = load_last_timestamp(config.timestamp_file_path)
        logger.info(f"Tentative de synchronisation depuis {last_successful_time}")

        rows = connector.pull(
            config.sqlite_db_dir,
            table_name,
            last_successful_time,
        )
        logger.info(f"{len(rows)} nouvelles entrées récupérées depuis SQLite")

        if not rows:
            logger.info("Aucune nouvelle donnée à synchroniser")
            return

        # S'assurer que la table PostgreSQL existe
        connector.create_table(conn_remote, table_name)

        # Insérer les données
        inserted_count = connector.push(conn_remote, table_name, rows)

        if inserted_count == 0 and len(rows) > 0:
            logger.info(
                f"Toutes les {len(rows)} lignes récupérées sont déjà en base (doublons). "
                "Mise à jour du timestamp pour avancer."
            )

        if rows:
            # Trier par timestamp pour s'assurer d'avoir le plus récent
            sorted_rows = sorted(
                rows, key=lambda r: connector.get_row_timestamp(r).timestamp()
            )
            last_timestamp = connector.get_row_timestamp(sorted_rows[-1])
            last_timestamp = last_timestamp + timedelta(microseconds=1)

            save_timestamp(last_timestamp, config.timestamp_file_path)
            logger.info(f"Timestamp mis à jour: {last_timestamp}")

    except psycopg2.Error as e:
        logger.error(f"Erreur PostgreSQL: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Erreur inconnue lors de la synchronisation: {e}", exc_info=True)
        raise
