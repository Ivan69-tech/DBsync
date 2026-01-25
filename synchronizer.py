"""
Logique principale de synchronisation SQLite -> PostgreSQL.
"""

import logging
from datetime import datetime

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import execute_values  # type: ignore[attr-defined]

from config import Config
from database import ensure_table_exists
from file_manager import load_last_timestamp, save_timestamp
from sqlite_manager import fetch_data_since_timestamp

logger = logging.getLogger(__name__)


def synchronize_data(conn_remote: connection, config: Config) -> bool:
    """
    Synchronise les données de SQLite vers PostgreSQL.

    Args:
        conn_remote: Connexion à la base PostgreSQL distante
        config: Configuration complète

    Returns:
        bool: True si la synchronisation a réussi
    """
    try:
        # Charger le dernier timestamp
        last_successful_time = load_last_timestamp(config.paths)
        logger.info(f"Tentative de synchronisation depuis {last_successful_time}")

        # Récupérer les nouvelles données depuis SQLite
        rows, columns, column_types, timestamp_col, key_col = (
            fetch_data_since_timestamp(last_successful_time, config.sqlite)
        )
        logger.info(f"{len(rows)} nouvelles entrées récupérées depuis SQLite")

        if not rows or not columns:
            logger.info("Aucune nouvelle donnée à synchroniser")
            return True

        # S'assurer que la table PostgreSQL existe avec les bonnes colonnes
        ensure_table_exists(
            conn_remote,
            columns,
            column_types,
            config.postgresql.table_name,
            timestamp_col,
            key_col,
        )

        timestamp_col_index = columns.index(timestamp_col)

        # Insérer avec ON CONFLICT DO NOTHING pour ignorer automatiquement les doublons
        # La PRIMARY KEY composite est sur (key_col, timestamp_col)
        try:
            with conn_remote.cursor() as cur_remote:
                # Construire la liste des colonnes pour l'insertion
                columns_list = ", ".join([f'"{col}"' for col in columns])
                # Spécifier explicitement la PRIMARY KEY composite pour ON CONFLICT
                key_col_escaped = f'"{key_col}"'
                timestamp_col_escaped = f'"{timestamp_col}"'

                # Utiliser execute_values pour insertion en masse avec ON CONFLICT
                # On ignore les doublons basés sur la combinaison (key, timestamp)
                insert_query = f"""
                    INSERT INTO {config.postgresql.table_name} ({columns_list})
                    VALUES %s
                    ON CONFLICT ({key_col_escaped}, {timestamp_col_escaped}) DO NOTHING
                """

                execute_values(
                    cur_remote, insert_query, rows, template=None, page_size=1000
                )

                inserted_count = cur_remote.rowcount

            # Commit seulement si tout s'est bien passé
            conn_remote.commit()

            if inserted_count == 0:
                logger.info("Toutes les lignes existent déjà dans la base distante")
            else:
                logger.info(
                    f"{inserted_count} entrées envoyées à la base distante (sur {len(rows)} nouvelles)"
                )
                if inserted_count < len(rows):
                    logger.warning(f"{len(rows) - inserted_count} doublon(s) ignoré(s)")

            last_timestamp_value = rows[-1][timestamp_col_index]
            # Convertir le timestamp Unix en datetime
            if isinstance(last_timestamp_value, (int, float)):
                last_timestamp = datetime.fromtimestamp(last_timestamp_value)
            else:
                # Si c'est déjà un datetime ou une chaîne, essayer de le convertir
                last_timestamp = (
                    last_timestamp_value
                    if isinstance(last_timestamp_value, datetime)
                    else datetime.fromisoformat(str(last_timestamp_value))
                )
            save_timestamp(last_timestamp, config.paths)

            return True

        except Exception as e:
            # Rollback en cas d'erreur
            conn_remote.rollback()
            logger.error(
                f"Erreur lors de l'insertion: {e}. Rollback effectué", exc_info=True
            )
            raise

    except psycopg2.Error as e:
        logger.error(f"Erreur PostgreSQL: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Erreur inconnue lors de la synchronisation: {e}", exc_info=True)
        raise
