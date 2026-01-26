"""
Logique principale de synchronisation SQLite -> PostgreSQL.
"""

import logging
from datetime import datetime

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import execute_values  # type: ignore[attr-defined]

from config.config import Config
from connectors.connectors_interface import ConnectorInterface
from file_manager import load_last_timestamp, save_timestamp

logger = logging.getLogger(__name__)


def synchronize_data(
    conn_remote: connection, config: Config, connector: ConnectorInterface
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
        last_successful_time = load_last_timestamp(config.paths)
        logger.info(f"Tentative de synchronisation depuis {last_successful_time}")

        # Récupérer les nouvelles données depuis SQLite
        # Le nom de la table SQLite est généralement "data" ou détecté automatiquement
        sqlite_table_name = getattr(config.sqlite, "table_name", "data")
        rows = connector.get_rows_from_sqlite(
            config.sqlite.db_dir,
            sqlite_table_name,
            last_successful_time,
        )
        logger.info(f"{len(rows)} nouvelles entrées récupérées depuis SQLite")

        if not rows:
            logger.info("Aucune nouvelle donnée à synchroniser")
            return

        # S'assurer que la table PostgreSQL existe
        connector.create_table(conn_remote, config.postgresql.table_name)

        # Insérer les données
        # Les colonnes sont : key, timestamp, type, value
        try:
            with conn_remote.cursor() as cur_remote:
                # Utiliser execute_values pour insertion en masse avec ON CONFLICT
                # On ignore les doublons basés sur la combinaison (key, timestamp)
                insert_query = f"""
                    INSERT INTO {config.postgresql.table_name} (key, timestamp, type, value)
                    VALUES %s
                    ON CONFLICT (key, timestamp) DO NOTHING
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

            # Extraire le timestamp de la dernière ligne (index 1 = colonne timestamp)
            if rows:
                last_timestamp_value = rows[-1][1]
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
