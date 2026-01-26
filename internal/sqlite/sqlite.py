import os
from datetime import datetime, date, timedelta
from sqlite3 import Connection
import sqlite3
import glob


def get_db_path_for_date(dt: datetime, db_dir: str) -> str:
    """
    Retourne le chemin du fichier SQLite pour une date donnée.

    Args:
        dt: datetime object
        db_dir: Répertoire des fichiers SQLite

    Returns:
        str: Chemin du fichier SQLite
    """
    db_filename = dt.strftime("%Y_%m_%d.db")
    db_dir = os.path.expanduser(db_dir)
    return os.path.join(db_dir, db_filename)


def get_db_paths_for_date_range(
    start_date: datetime, end_date: datetime, db_dir: str
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
            datetime.combine(current_date, datetime.min.time()),
            db_dir,  # pour avoir le jour en datetime
        )
        if os.path.exists(db_path):
            paths.append(db_path)
        current_date += timedelta(days=1)
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


def get_table_name(conn: Connection) -> str | None:
    """
    Trouve le nom de la table à synchroniser dans la base SQLite.
    Cherche d'abord une table contenant "pc-" dans son nom.

    Args:
        conn: Connexion SQLite

    Returns:
        str | None: Nom de la table ou None si aucune table trouvée
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1;")
    result = cursor.fetchone()
    return result[0] if result else None


def get_table_name_from_db_dir(db_dir: str) -> str | None:
    """
    Récupère le nom de la table SQLite depuis le premier fichier .db trouvé dans db_dir.

    Args:
        db_dir: Répertoire contenant les fichiers SQLite

    Returns:
        str | None: Nom de la table ou None si aucune table trouvée
    """

    db_dir = os.path.expanduser(db_dir)
    db_files = glob.glob(os.path.join(db_dir, "*.db"))

    if not db_files:
        return None

    # Utiliser le premier fichier trouvé
    first_db = db_files[0]
    try:
        with connect_sqlite(first_db) as conn:
            table_name = get_table_name(conn)
            return table_name
    except Exception:
        return None
