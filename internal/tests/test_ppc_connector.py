"""
Tests unitaires pour PPCConnector.

Vérifie que le connector écrit bien dans `ppc_raw` avec le bon `site_id`,
et qu'il lit correctement depuis les fichiers SQLite locaux.
"""

import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from connectors.connectors_factory import connector_factory
from connectors.ppc import PPCConnector, _PPC_RAW_TABLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sqlite_row(key: str, timestamp: float, type_: str, value: str) -> sqlite3.Row:
    """Crée une sqlite3.Row à partir de valeurs brutes."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (key TEXT, timestamp REAL, type TEXT, value TEXT)")
    conn.execute("INSERT INTO t VALUES (?, ?, ?, ?)", (key, timestamp, type_, value))
    conn.commit()
    row = conn.execute("SELECT * FROM t").fetchone()
    return row


def make_mock_cursor():
    """Retourne un cursor mock avec rowcount = -1 (psycopg2 execute_values)."""
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.rowcount = 3
    return cursor


def make_mock_conn(cursor=None):
    """Retourne une connexion psycopg2 mockée."""
    conn = MagicMock()
    conn.closed = False
    conn.cursor.return_value = cursor or make_mock_cursor()
    return conn


# ---------------------------------------------------------------------------
# Tests PPCConnector.__init__
# ---------------------------------------------------------------------------

class TestPPCConnectorInit:
    def test_site_id_stored(self):
        connector = PPCConnector(site_id="site-demo-01")
        assert connector.site_id == "site-demo-01"


# ---------------------------------------------------------------------------
# Tests PPCConnector.create_table
# ---------------------------------------------------------------------------

class TestCreateTable:
    def test_does_nothing_if_table_exists(self):
        connector = PPCConnector(site_id="site-demo-01")
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (True,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "ignored_table_name")

        # Aucun CREATE TABLE ne doit être exécuté
        calls_sql = [str(c) for c in cursor.execute.call_args_list]
        assert not any("CREATE TABLE" in s for s in calls_sql)
        conn.commit.assert_called_once()

    def test_creates_table_if_missing(self):
        connector = PPCConnector(site_id="site-demo-01")
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (False,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "ignored_table_name")

        calls_sql = " ".join(str(c) for c in cursor.execute.call_args_list)
        assert "CREATE TABLE" in calls_sql
        assert _PPC_RAW_TABLE in calls_sql

    def test_ignores_table_name_param(self):
        """Le paramètre table_name est ignoré — la cible est toujours ppc_raw."""
        connector = PPCConnector(site_id="site-demo-01")
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (True,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "some_other_table")

        # La requête SELECT doit vérifier ppc_raw, pas some_other_table
        first_call_args = str(cursor.execute.call_args_list[0])
        assert _PPC_RAW_TABLE in first_call_args


# ---------------------------------------------------------------------------
# Tests PPCConnector.push
# ---------------------------------------------------------------------------

class TestPush:
    def test_inserts_with_site_id(self):
        connector = PPCConnector(site_id="site-abc")
        row = make_sqlite_row("bess_0_soc", 1700000000.0, "float", "75.5")
        cursor = make_mock_cursor()
        cursor.rowcount = 1
        conn = make_mock_conn(cursor)

        with patch("connectors.ppc.execute_values") as mock_ev:
            result = connector.push(conn, "ignored", [row])

        mock_ev.assert_called_once()
        _, call_args, call_kwargs = mock_ev.mock_calls[0]
        rows_passed = call_args[2]
        assert rows_passed[0] == ("site-abc", "bess_0_soc", 1700000000.0, "float", "75.5")
        conn.commit.assert_called_once()

    def test_returns_zero_for_empty_rows(self):
        connector = PPCConnector(site_id="site-abc")
        conn = make_mock_conn()

        result = connector.push(conn, "ignored", [])

        assert result == 0
        conn.commit.assert_not_called()

    def test_rollback_on_error(self):
        connector = PPCConnector(site_id="site-abc")
        row = make_sqlite_row("key", 1.0, "float", "1.0")
        conn = make_mock_conn()

        with patch("connectors.ppc.execute_values", side_effect=Exception("DB error")):
            with pytest.raises(Exception, match="DB error"):
                connector.push(conn, "ignored", [row])

        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Tests PPCConnector.pull
# ---------------------------------------------------------------------------

class TestPull:
    def test_reads_from_sqlite(self):
        """Vérifie que pull lit bien la table SQLite nommée d'après le site_id."""
        connector = PPCConnector(site_id="site-demo-01")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Créer un fichier SQLite quotidien
            today = datetime.now()
            db_filename = today.strftime("%Y_%m_%d.db")
            db_path = Path(tmpdir) / db_filename

            conn_sqlite = sqlite3.connect(str(db_path))
            conn_sqlite.execute(
                'CREATE TABLE "site-demo-01" (key TEXT, timestamp REAL, type TEXT, value TEXT)'
            )
            conn_sqlite.execute(
                'INSERT INTO "site-demo-01" VALUES (?, ?, ?, ?)',
                ("bess_0_p", time.time(), "float", "100.0"),
            )
            conn_sqlite.commit()
            conn_sqlite.close()

            last_ts = datetime(2000, 1, 1)
            rows = connector.pull(tmpdir, "site-demo-01", last_ts)

        assert len(rows) == 1
        assert rows[0]["key"] == "bess_0_p"
        assert rows[0]["value"] == "100.0"

    def test_returns_empty_list_on_missing_dir(self):
        connector = PPCConnector(site_id="site-demo-01")
        rows = connector.pull("/nonexistent/path", "site-demo-01", datetime(2000, 1, 1))
        assert rows == []


# ---------------------------------------------------------------------------
# Tests PPCConnector.get_row_timestamp
# ---------------------------------------------------------------------------

class TestGetRowTimestamp:
    def test_float_timestamp(self):
        connector = PPCConnector(site_id="s")
        row = make_sqlite_row("k", 1700000000.0, "float", "1.0")
        ts = connector.get_row_timestamp(row)
        assert isinstance(ts, datetime)
        assert ts == datetime.fromtimestamp(1700000000.0)

    def test_int_timestamp(self):
        connector = PPCConnector(site_id="s")
        # sqlite3.Row avec un entier
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (key TEXT, timestamp INTEGER, type TEXT, value TEXT)")
        conn.execute("INSERT INTO t VALUES ('k', 1700000000, 'float', '1.0')")
        row = conn.execute("SELECT * FROM t").fetchone()
        ts = connector.get_row_timestamp(row)
        assert ts == datetime.fromtimestamp(1700000000)


# ---------------------------------------------------------------------------
# Tests connector_factory
# ---------------------------------------------------------------------------

class TestConnectorFactory:
    def test_returns_ppc_connector_with_site_id(self):
        connector = connector_factory("ppc", site_id="site-demo-01")
        assert isinstance(connector, PPCConnector)
        assert connector.site_id == "site-demo-01"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="not supported"):
            connector_factory("unknown")
