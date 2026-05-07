"""
Connector Forecaster : synchronise les datapoints SQLite du PPC vers la table mesures_reelles PostgreSQL.
Pivote les clés selon le mapping défini dans la config YAML.
"""

import logging
import sqlite3
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import execute_values

from connectors.connectors_interface import ConnectorInterface
from sqlite.sqlite import connect_sqlite, get_db_paths_for_date_range

logger = logging.getLogger(__name__)

_FORECASTER_TABLE = "mesures_reelles"
_PDL_COL = "puissance_pdl_kw"


class ForecasterConnector(ConnectorInterface):
    def __init__(self, site_id: str, key_mapping: dict[str, str]):
        self.site_id = site_id
        self.key_mapping = key_mapping  # ex: {"bess_0_p": "puissance_bess_kw", ...}

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
        """Vérifie que mesures_reelles existe et que l'index unique (site_id, timestamp) est présent."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                    (_FORECASTER_TABLE,),
                )
                result = cur.fetchone()
                table_exists = result[0] if result else False
                if not table_exists:
                    logger.warning("Table mesures_reelles absente, creation en urgence.")
                    cur.execute(
                        f'CREATE TABLE "{_FORECASTER_TABLE}" ('
                        "id SERIAL PRIMARY KEY, "
                        "site_id VARCHAR(64) NOT NULL, "
                        "timestamp TIMESTAMPTZ NOT NULL, "
                        "conso_kw FLOAT NOT NULL, "
                        "production_pv_kw FLOAT NOT NULL, "
                        "soc_kwh FLOAT NOT NULL, "
                        "puissance_bess_kw FLOAT NOT NULL, "
                        "puissance_pdl_kw FLOAT NOT NULL"
                        ")"
                    )
                    logger.info("Table mesures_reelles creee.")
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mesures_reelles_site_ts "
                    f'ON "{_FORECASTER_TABLE}" (site_id, timestamp)'
                )
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
        """Pivote les rows par timestamp et insere dans mesures_reelles."""
        if not rows:
            return 0

        # Grouper par timestamp : {ts_float: {sqlite_key: value_str}}
        groups: dict[float, dict[str, str]] = {}
        for row in rows:
            key = row["key"]
            if key not in self.key_mapping:
                continue
            ts = float(row["timestamp"])
            if ts not in groups:
                groups[ts] = {}
            groups[ts][key] = row["value"]

        required_keys = set(self.key_mapping.keys())
        has_pdl = _PDL_COL in self.key_mapping.values()

        # Colonnes cibles dans l'ordre déterministe
        mapped_cols = list(self.key_mapping.values())
        insert_cols = ["site_id", "timestamp"] + mapped_cols
        if not has_pdl:
            insert_cols.append(_PDL_COL)

        tuples = []
        for ts in sorted(groups):
            key_values = groups[ts]
            if not required_keys.issubset(key_values.keys()):
                continue  # timestamp incomplet, skip silencieux
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            row_values: list = [self.site_id, dt]
            for src_key in self.key_mapping:
                row_values.append(float(key_values[src_key]))
            if not has_pdl:
                row_values.append(0.0)
            tuples.append(tuple(row_values))

        if not tuples:
            return 0

        update_cols = [c for c in insert_cols if c not in ("site_id", "timestamp")]
        cols_str = ", ".join(insert_cols)
        update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        insert_query = (
            f'INSERT INTO "{_FORECASTER_TABLE}" ({cols_str}) VALUES %s '
            f"ON CONFLICT (site_id, timestamp) DO UPDATE SET {update_str}"
        )

        inserted_count = 0
        try:
            with conn.cursor() as cur:
                execute_values(cur, insert_query, tuples, page_size=1000)
                inserted_count = cur.rowcount
            conn.commit()
            logger.info(
                "%d/%d timestamps inseres dans mesures_reelles (site_id=%s)",
                inserted_count, len(tuples), self.site_id,
            )
            return inserted_count
        except Exception as e:
            logger.error("Erreur push mesures_reelles: %s", e, exc_info=True)
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
