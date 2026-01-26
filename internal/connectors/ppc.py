"""
Gestion des connexions et opérations PostgreSQL.
"""

import logging
import time
import sqlite3

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import execute_values  # type: ignore[attr-defined]
from connectors.connectors_interface import ConnectorInterface
from sqlite.sqlite import connect_sqlite, get_db_paths_for_date_range
from datetime import datetime


logger = logging.getLogger(__name__)


class PPCConnector(ConnectorInterface):
    """
    Connexion PostgreSQL pour une base ppc.
    """

    def connect(
        self,
        dbname: str,
        user: str,
        password: str,
        host: str,
        port: str | int,
    ) -> connection:
        """
        Établit une connexion PostgreSQL avec retry constant.

        Args:
            dbname: Nom de la base de données
            user: Utilisateur
            password: Mot de passe
            host: Hôte
            port: Port

        Returns:
            Connection: Connexion PostgreSQL
        """
        connect_timeout = 10
        retry_delay = 10

        while True:
            try:
                conn = psycopg2.connect(
                    dbname=dbname,
                    user=user,
                    password=password,
                    host=host,
                    port=port,
                    connect_timeout=connect_timeout,
                )
                logger.info(f"Connexion PostgreSQL établie: {host}:{port}/{dbname}")
                return conn
            except psycopg2.OperationalError as e:
                logger.warning(
                    f"Erreur PostgreSQL {host}: {e}. Nouvelle tentative dans {retry_delay} secondes"
                )
                time.sleep(retry_delay)

    def disconnect(self, conn: connection):
        """
        Ferme proprement une connexion PostgreSQL.

        Args:
            conn: Connexion à fermer
        """
        try:
            if conn:
                conn.close()
                logger.debug("Connexion PostgreSQL fermée")
        except (psycopg2.Error, AttributeError) as e:
            logger.warning(f"Erreur lors de la fermeture de la connexion: {e}")

    def create_table(
        self,
        conn: connection,
        table_name: str,
    ):
        """
        Crée une table PostgreSQL avec les colonnes explicites : key, timestamp, type, value.

        Args:
            conn: Connexion à la base de données
            table_name: Nom de la table
        """
        try:
            with conn.cursor() as cur:
                # Vérifier si la table existe
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """,
                    (table_name,),
                )

                result = cur.fetchone()
                table_exists: bool = result[0] if result else False

                if not table_exists:
                    create_table_sql = f"""
                        CREATE TABLE "{table_name}" (
                            key TEXT,
                            timestamp DOUBLE PRECISION,
                            type TEXT,
                            value DOUBLE PRECISION,
                            PRIMARY KEY (key, timestamp)
                        )
                    """
                    cur.execute(create_table_sql)
                    logger.info(
                        f"Table {table_name} créée avec les colonnes: key, timestamp, type, value"
                    )
                else:
                    logger.debug(f"Table {table_name} existe déjà")

            conn.commit()

        except Exception as e:
            logger.error(
                f"Erreur lors de la création/modification de la table: {e}",
                exc_info=True,
            )
            conn.rollback()
            raise

    def pull(
        self,
        db_dir: str,
        table_name: str,
        last_timestamp: datetime,
    ) -> list[sqlite3.Row]:
        """
        Récupère les lignes depuis SQLite avec timestamp > last_timestamp.

        Args:
            db_dir: Répertoire des fichiers SQLite
            table_name: Nom de la table
            last_timestamp: Timestamp de départ

        Returns:
            list[sqlite3.Row]: Liste de rows SQLite (accès par nom de colonne possible)
        """

        db_paths = get_db_paths_for_date_range(last_timestamp, datetime.now(), db_dir)
        rows_list: list[sqlite3.Row] = []
        try:
            # Convertir le timestamp en secondes depuis l'epoch Unix
            last_timestamp_seconds = last_timestamp.timestamp()
            for db_path in db_paths:
                with connect_sqlite(str(db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        f'SELECT * FROM "{table_name}" WHERE timestamp > ? ORDER BY timestamp ASC',
                        (last_timestamp_seconds,),
                    )
                    rows = cursor.fetchall()
                    rows_list.extend(rows)

            logger.info(
                f"Total: {len(rows_list)} lignes récupérées depuis {len(db_paths)} fichier(s)"
            )
            return rows_list

        except Exception as e:
            logger.error(
                f"Erreur lors de la lecture des fichiers SQLite: {e}", exc_info=True
            )
            return []

    def push(
        self,
        conn: connection,
        table_name: str,
        rows: list[sqlite3.Row],
    ) -> int:
        """
        Insère les lignes dans PostgreSQL.

        Args:
            conn: Connexion PostgreSQL
            table_name: Nom de la table
            rows: Liste de rows SQLite (accès par nom de colonne)

        Returns:
            int: Nombre de lignes insérées
        """
        inserted_count = 0
        try:
            # Convertir les sqlite3.Row en tuples pour execute_values
            # Ordre: key, timestamp, type, value
            rows_tuples = [
                (row["key"], row["timestamp"], row["type"], row["value"])
                for row in rows
            ]

            with conn.cursor() as cur:
                # Échapper le nom de la table avec des guillemets pour gérer les caractères spéciaux
                insert_query = f"""
                    INSERT INTO "{table_name}" (key, timestamp, type, value)
                    VALUES %s
                    ON CONFLICT (key, timestamp) DO NOTHING
                """
                execute_values(
                    cur, insert_query, rows_tuples, template=None, page_size=1000
                )
                inserted_count = cur.rowcount

            logger.info(
                f"{inserted_count} entrées envoyées à la base distante (sur {len(rows)} nouvelles)"
            )
            if inserted_count < len(rows):
                logger.warning(f"{len(rows) - inserted_count} doublon(s) ignoré(s)")

            conn.commit()
            return inserted_count
        except Exception as e:
            logger.error(
                f"Erreur lors de l'insertion dans PostgreSQL: {e}", exc_info=True
            )
            conn.rollback()
            raise  # Relancer l'exception pour que synchronizer.py puisse la gérer
