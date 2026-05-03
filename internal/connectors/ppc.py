"""
Connector PPC : synchronise les donnees SQLite du PPC vers la table ppc_raw PostgreSQL.
"""

import logging
import sqlite3
import time
from datetime import datetime

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import execute_values

from connectors.connectors_interface import ConnectorInterface
from sqlite.sqlite import connect_sqlite, get_db_paths_for_date_range

logger = logging.getLogger(__name__)

_PPC_RAW_TABLE = "ppc_raw"


class PPCConnector(ConnectorInterface):
    def __init__(self, site_id: str):
        self.site_id = site_id

    def connect(self, dbname, user, password, host, port):
        connect_timeout = 10
        retry_delay = 10
        while True:
            try:
                conn = psycopg2.connect(
                    dbname=dbname, user=user, password=password,
                    host=host, port=port, connect_timeout=connect_timeout,
                )
                logger.info("Connexion PostgreSQL etablie: %s:%s/%s", host, port, dbname)
                return conn
            except psycopg2.OperationalError as e:
                logger.warning("Erreur PostgreSQL %s: %s. Retry dans %ds", host, e, retry_delay)
                time.sleep(retry_delay)

    def disconnect(self, conn):
        try:
            if conn:
                conn.close()
        except (psycopg2.Error, AttributeError) as e:
            logger.warning("Erreur fermeture connexion: %s", e)

    def create_table(self, conn, table_name):
        """Verifie que ppc_raw existe. Le parametre table_name est ignore."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                    (_PPC_RAW_TABLE,),
                )
                result = cur.fetchone()
                table_exists = result[0] if result else False
                if not table_exists:
                    logger.warning("Table ppc_raw absente, creation en urgence.")
                    cur.execute(
                        'CREATE TABLE "ppc_raw" ('
                        'site_id TEXT NOT NULL, key TEXT NOT NULL, '
                        'timestamp DOUBLE PRECISION NOT NULL, '
                        'type TEXT NOT NULL, value TEXT NOT NULL, '
                        'PRIMARY KEY (site_id, key, timestamp))'
                    )
                    cur.execute('CREATE INDEX IF NOT EXISTS ix_ppc_raw_site_id ON "ppc_raw" (site_id)')
                    cur.execute('CREATE INDEX IF NOT EXISTS ix_ppc_raw_timestamp ON "ppc_raw" (timestamp)')
                    logger.info("Table ppc_raw creee.")
            conn.commit()
        except Exception as e:
            logger.error("Erreur create_table: %s", e, exc_info=True)
            if not conn.closed:
                conn.rollback()
            raise

    def pull(self, db_dir, table_name, last_timestamp):
        """Lit les lignes SQLite avec timestamp > last_timestamp."""
        db_paths = get_db_paths_for_date_range(last_timestamp, datetime.now(), db_dir)
        rows_list = []
        last_ts_seconds = last_timestamp.timestamp()
        try:
            for db_path in db_paths:
                conn = connect_sqlite(str(db_path))
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT * FROM "' + table_name + '" WHERE timestamp > ? ORDER BY timestamp ASC',
                        (last_ts_seconds,),
                    )
                    rows_list.extend(cursor.fetchall())
                finally:
                    conn.close()
            logger.info("%d lignes depuis %d fichier(s) SQLite", len(rows_list), len(db_paths))
            return rows_list
        except Exception as e:
            logger.error("Erreur lecture SQLite: %s", e, exc_info=True)
            return []

    def push(self, conn, table_name, rows):
        """Insere dans ppc_raw. Le parametre table_name est ignore."""
        if not rows:
            return 0
        inserted_count = 0
        try:
            rows_tuples = [
                (self.site_id, row["key"], row["timestamp"], row["type"], row["value"])
                for row in rows
            ]
            with conn.cursor() as cur:
                insert_query = (
                    'INSERT INTO "ppc_raw" (site_id, key, timestamp, type, value) '
                    'VALUES %s ON CONFLICT (site_id, key, timestamp) DO NOTHING'
                )
                execute_values(cur, insert_query, rows_tuples, page_size=1000)
                inserted_count = cur.rowcount
            conn.commit()
            logger.info("%d/%d lignes inserees dans ppc_raw (site_id=%s)",
                        inserted_count, len(rows), self.site_id)
            return inserted_count
        except Exception as e:
            logger.error("Erreur push ppc_raw: %s", e, exc_info=True)
            if not conn.closed:
                conn.rollback()
            raise

    def get_row_timestamp(self, row):
        ts = row["timestamp"]
        if isinstance(ts, datetime):
            return ts
        elif isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts)
        else:
            return datetime.fromisoformat(str(ts))
