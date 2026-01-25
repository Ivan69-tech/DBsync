"""
Gestion des connexions et opérations PostgreSQL.
"""

import logging
import time

import psycopg2
from psycopg2.extensions import connection

from config import SyncConfig

logger = logging.getLogger(__name__)


def connect_postgres(
    dbname: str,
    user: str,
    password: str,
    host: str,
    port: str | int,
    sync_config: SyncConfig,
    retry_delay: int | None = None,
) -> connection:
    """
    Établit une connexion PostgreSQL avec backoff exponentiel.

    Args:
        dbname: Nom de la base de données
        user: Utilisateur
        password: Mot de passe
        host: Hôte
        port: Port
        sync_config: Configuration de synchronisation
        retry_delay: Délai initial avant nouvelle tentative (backoff exponentiel)

    Returns:
        Connection: Connexion PostgreSQL
    """
    if retry_delay is None:
        retry_delay = sync_config.initial_retry_delay

    current_delay = retry_delay
    while True:
        try:
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=sync_config.connect_timeout,
            )
            logger.info(f"Connexion PostgreSQL établie: {host}:{port}/{dbname}")
            return conn
        except psycopg2.OperationalError as e:
            logger.warning(
                f"Erreur PostgreSQL {host}: {e}. Nouvelle tentative dans {current_delay} secondes"
            )
            time.sleep(current_delay)
            # Backoff exponentiel avec limite maximale
            current_delay = min(current_delay * 2, sync_config.max_retry_delay)


def sqlite_to_postgres_type(sqlite_type: str) -> str:
    """
    Convertit un type SQLite en type PostgreSQL.

    Args:
        sqlite_type: Type SQLite (ex: INTEGER, TEXT, REAL, TIMESTAMP)

    Returns:
        str: Type PostgreSQL correspondant
    """
    sqlite_type_upper = sqlite_type.upper()

    if "INT" in sqlite_type_upper:
        return "BIGINT"
    elif (
        "REAL" in sqlite_type_upper
        or "FLOAT" in sqlite_type_upper
        or "DOUBLE" in sqlite_type_upper
    ):
        return "DOUBLE PRECISION"
    elif (
        "TEXT" in sqlite_type_upper
        or "CHAR" in sqlite_type_upper
        or "CLOB" in sqlite_type_upper
    ):
        return "TEXT"
    elif "BLOB" in sqlite_type_upper:
        return "BYTEA"
    elif "TIME" in sqlite_type_upper or "DATE" in sqlite_type_upper:
        return "TIMESTAMP"
    else:
        return "TEXT"  # Par défaut


def ensure_table_exists(
    conn_remote: connection,
    columns: list[str],
    column_types: dict[str, str],
    table_name: str,
    timestamp_column: str,
    key_column: str,
) -> None:
    """
    S'assure que la table PostgreSQL existe avec les bonnes colonnes.
    Ajoute les colonnes manquantes si la table existe déjà.
    Crée une PRIMARY KEY composite sur (key_column, timestamp_column) lors de la création de la table.

    Args:
        conn_remote: Connexion à la base distante
        columns: Liste des noms de colonnes
        column_types: Dictionnaire {nom_colonne: type_sqlite}
        table_name: Nom de la table PostgreSQL
        timestamp_column: Nom de la colonne timestamp pour la PRIMARY KEY composite
        key_column: Nom de la colonne key pour la PRIMARY KEY composite
    """
    try:
        with conn_remote.cursor() as cur_remote:
            # Vérifier si la table existe
            cur_remote.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """,
                (table_name,),
            )

            result = cur_remote.fetchone()
            table_exists: bool = result[0] if result else False

            if not table_exists:
                # Créer la table avec toutes les colonnes
                columns_def: list[str] = []
                for col in columns:
                    pg_type = sqlite_to_postgres_type(column_types.get(col, "TEXT"))
                    columns_def.append(f'"{col}" {pg_type}')

                # Créer une PRIMARY KEY composite sur (key_column, timestamp_column)
                key_col_escaped = f'"{key_column}"'
                timestamp_col_escaped = f'"{timestamp_column}"'
                create_table_sql = f"""
                    CREATE TABLE {table_name} (
                        {", ".join(columns_def)},
                        PRIMARY KEY ({key_col_escaped}, {timestamp_col_escaped})
                    )
                """
                cur_remote.execute(create_table_sql)
                logger.info(
                    f"Table {table_name} créée avec {len(columns)} colonnes et PRIMARY KEY composite sur ({key_column}, {timestamp_column})"
                )
            else:
                # Vérifier les colonnes existantes
                cur_remote.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = %s
                """,
                    (table_name,),
                )

                existing_columns = {row[0] for row in cur_remote.fetchall()}

                # Ajouter les colonnes manquantes
                for col in columns:
                    if col not in existing_columns:
                        pg_type = sqlite_to_postgres_type(column_types.get(col, "TEXT"))
                        alter_sql = (
                            f'ALTER TABLE {table_name} ADD COLUMN "{col}" {pg_type}'
                        )
                        cur_remote.execute(alter_sql)
                        logger.info(f"Colonne {col} ajoutée à {table_name}")

                logger.debug(f"Table {table_name} vérifiée")

        conn_remote.commit()

    except Exception as e:
        logger.error(
            f"Erreur lors de la création/modification de la table: {e}", exc_info=True
        )
        conn_remote.rollback()
        raise


def close_connection(conn: connection | None) -> None:
    """
    Ferme proprement une connexion PostgreSQL.

    Args:
        conn: Connexion à fermer
    """
    try:
        if conn:
            conn.close()
    except (psycopg2.Error, AttributeError):
        pass
