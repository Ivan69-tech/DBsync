"""
Gestion des connexions et opérations PostgreSQL.
"""

import logging
import time

import psycopg2
from psycopg2.extensions import connection

from connectors.connectors_interface import ConnectorInterface
from sqlite.sqlite import connect_sqlite, get_db_paths_for_date_range
from datetime import datetime
from typing import Any

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
                    # Créer la table avec les colonnes explicites
                    create_table_sql = f"""
                        CREATE TABLE {table_name} (
                            key TEXT,
                            timestamp DOUBLE PRECISION,
                            type TEXT,
                            value DOUBLE PRECISION
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

    def get_rows_from_sqlite(
        self,
        db_dir: str,
        table_name: str,
        last_timestamp: datetime,
    ) -> list[tuple[Any, ...]]:
        """
        Récupère les lignes depuis SQLite avec timestamp > timestamp.

        Args:
            db_path: Chemin du fichier SQLite
            table_name: Nom de la table
            timestamp: Timestamp de départ

        Returns:
            list[tuple[Any, ...]]: Liste de tuples de données
        """

        db_paths = get_db_paths_for_date_range(last_timestamp, datetime.now(), db_dir)
        rows_list: list[tuple[Any, ...]] = []
        try:
            for db_path in db_paths:
                conn = connect_sqlite(str(db_path))
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT * FROM {table_name} WHERE timestamp > ?", (last_timestamp,)
                )
                rows = cursor.fetchall()
                rows_list.extend(rows)
                conn.close()
            return rows_list

        except Exception as e:
            logger.error(f"Erreur lors de la lecture des fichiers SQLite: {e}")
            return []
