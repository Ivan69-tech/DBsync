"""
Gestion des connexions et opérations SQLite.
"""

import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from sqlite3 import Connection
from typing import Any

from config import SqliteConfig

logger = logging.getLogger(__name__)

# Type alias pour les données
RowData = tuple[Any, ...]  # timestamp + colonnes variables (peut contenir None)


def get_db_path_for_date(dt: datetime, sqlite_config: SqliteConfig) -> str:
    """
    Retourne le chemin du fichier SQLite pour une date donnée.

    Args:
        dt: datetime object
        sqlite_config: Configuration SQLite

    Returns:
        str: Chemin du fichier SQLite
    """
    db_filename = dt.strftime("%Y_%m_%d.db")
    db_dir = os.path.expanduser(sqlite_config.db_dir)
    return os.path.join(db_dir, db_filename)


def get_db_paths_for_date_range(
    start_date: datetime, end_date: datetime, sqlite_config: SqliteConfig
) -> list[str]:
    """
    Retourne la liste des chemins de fichiers SQLite pour une plage de dates.

    Args:
        start_date: datetime de début
        end_date: datetime de fin
        sqlite_config: Configuration SQLite

    Returns:
        list: Liste des chemins de fichiers SQLite
    """
    paths: list[str] = []
    current_date: date = start_date.date()
    end_date_only: date = end_date.date()

    while current_date <= end_date_only:
        db_path = get_db_path_for_date(
            datetime.combine(current_date, datetime.min.time()), sqlite_config
        )
        if os.path.exists(db_path):
            paths.append(db_path)
        current_date += timedelta(days=1)
    print(f"🔍 Chemins SQLite trouvés: {paths}")
    return paths


def connect_sqlite(db_path: str) -> Connection:
    """
    Établit une connexion SQLite.

    Args:
        db_path: Chemin du fichier SQLite

    Returns:
        Connection: Connexion SQLite
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Fichier SQLite introuvable : {db_path}")

    conn = sqlite3.connect(
        db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    conn.row_factory = sqlite3.Row
    return conn


def get_table_name(conn: Connection, sqlite_config: SqliteConfig) -> str | None:
    """
    Trouve le nom de la table à synchroniser dans la base SQLite.

    Args:
        conn: Connexion SQLite
        sqlite_config: Configuration SQLite

    Returns:
        str | None: Nom de la table ou None si aucune table trouvée
    """
    cursor = conn.cursor()

    # Si un nom de table est spécifié dans config, vérifier qu'elle existe
    if sqlite_config.table_name:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (sqlite_config.table_name,),
        )
        result = cursor.fetchone()
        return result[0] if result else None

    # Sinon, prendre la première table non-système
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    result = cursor.fetchone()
    return result[0] if result else None


def get_table_columns(conn: Connection, table_name: str) -> list[str]:
    """
    Récupère la liste des colonnes d'une table SQLite.

    Args:
        conn: Connexion SQLite
        table_name: Nom de la table

    Returns:
        list: Liste des noms de colonnes
    """
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    columns = [row[1] for row in cursor.fetchall()]
    return columns


def get_column_type(conn: Connection, table_name: str, column_name: str) -> str:
    """
    Récupère le type SQLite d'une colonne.

    Args:
        conn: Connexion SQLite
        table_name: Nom de la table
        column_name: Nom de la colonne

    Returns:
        str: Type de la colonne (TEXT, INTEGER, REAL, TIMESTAMP, etc.)
    """
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    for row in cursor.fetchall():
        if row[1] == column_name:
            return row[2].upper()
    return "TEXT"


def fetch_data_since_timestamp(
    timestamp: datetime,
    sqlite_config: SqliteConfig,
) -> tuple[list[RowData], list[str], dict[str, str], str, str]:
    """
    Récupère toutes les données depuis un timestamp donné depuis tous les fichiers SQLite pertinents.

    Args:
        timestamp: datetime - Timestamp de départ
        sqlite_config: Configuration SQLite

    Returns:
        tuple: (list de tuples de données, list des noms de colonnes, dict des types de colonnes, timestamp_col, key_col)
    """
    sqlite_db_dir = os.path.expanduser(sqlite_config.db_dir)

    # Déterminer la plage de dates à rechercher (depuis le timestamp jusqu'à maintenant)
    end_date: datetime = datetime.now()
    start_date: datetime = timestamp

    # Obtenir tous les fichiers SQLite pertinents
    db_paths: list[str] = get_db_paths_for_date_range(
        start_date, end_date, sqlite_config
    )

    if not db_paths:
        logger.warning(f"Aucun fichier SQLite trouvé dans {sqlite_db_dir}")
        return [], [], {}, "", ""

    all_rows: list[RowData] = []
    columns: list[str] = []
    column_types: dict[str, str] = {}
    timestamp_col: str | None = None
    key_col: str | None = None

    # Parcourir chaque fichier SQLite
    for db_path in db_paths:
        try:
            conn = connect_sqlite(db_path)

            # Trouver la table à synchroniser
            table_name = get_table_name(conn, sqlite_config)
            if not table_name:
                logger.warning(f"Aucune table trouvée dans {db_path}")
                conn.close()
                continue

            # Récupérer les colonnes et leurs types (une seule fois)
            if not columns:
                columns = get_table_columns(conn, table_name)
                column_types = {
                    col: get_column_type(conn, table_name, col) for col in columns
                }
                logger.info(f"Table '{table_name}' détectée avec colonnes: {columns}")

            # Trouver la colonne timestamp (doit contenir 'time' ou 'date' dans son nom)
            if not timestamp_col:
                for col in columns:
                    col_lower = col.lower()
                    if "time" in col_lower or "date" in col_lower:
                        timestamp_col = col
                        break

            # Trouver la colonne key (doit contenir 'key', 'id', 'register', 'name' dans son nom)
            if not key_col:
                for col in columns:
                    col_lower = col.lower()
                    if (
                        col_lower in ["key", "id", "register", "name"]
                        or "key" in col_lower
                        or "register" in col_lower
                    ):
                        key_col = col
                        break

            if not timestamp_col:
                logger.warning(f"Aucune colonne timestamp trouvée dans {db_path}")
                conn.close()
                continue

            if not key_col:
                logger.warning(f"Aucune colonne key trouvée dans {db_path}")
                conn.close()
                continue

            # Récupérer les données depuis le timestamp
            cursor = conn.cursor()
            # Échapper les noms de colonnes pour éviter les erreurs avec les caractères spéciaux
            columns_escaped = [f'"{col}"' for col in columns]
            columns_str = ", ".join(columns_escaped)
            timestamp_col_escaped = f'"{timestamp_col}"'

            # Convertir le datetime en timestamp Unix si la colonne contient des nombres
            # On essaie d'abord de convertir en timestamp Unix
            timestamp_value = timestamp.timestamp()

            query = f"""
                SELECT {columns_str}
                FROM "{table_name}"
                WHERE {timestamp_col_escaped} >= ?
                ORDER BY {timestamp_col_escaped} ASC
            """
            # Utiliser >= pour inclure les lignes avec le même timestamp exact
            # On filtrera les doublons après si nécessaire
            cursor.execute(query, (timestamp_value,))

            rows = cursor.fetchall()
            # Convertir les Row objects en tuples
            for row in rows:
                all_rows.append(tuple(row))

            conn.close()

        except Exception as e:
            logger.warning(
                f"Erreur lors de la lecture de {db_path}: {e}", exc_info=True
            )
            continue

    if not timestamp_col or not key_col:
        return [], [], {}, "", ""

    return all_rows, columns, column_types, timestamp_col, key_col
