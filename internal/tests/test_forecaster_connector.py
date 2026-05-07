"""
Tests unitaires pour ForecasterConnector.

Vérifie que le connector pivote correctement les clés SQLite,
ignore les timestamps incomplets, et écrit dans mesures_reelles.
"""

import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectors.connectors_factory import connector_factory
from connectors.forecaster import ForecasterConnector, _FORECASTER_TABLE

_KEY_MAPPING = {
    "bess_0_p": "puissance_bess_kw",
    "pv_0_p": "production_pv_kw",
    "conso_kw": "conso_kw",
    "soc_kwh": "soc_kwh",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sqlite_row(key: str, timestamp: float, value: str) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (key TEXT, timestamp REAL, type TEXT, value TEXT)")
    conn.execute("INSERT INTO t VALUES (?, ?, ?, ?)", (key, timestamp, "float", value))
    conn.commit()
    return conn.execute("SELECT * FROM t").fetchone()


def make_complete_rows(timestamp: float) -> list[sqlite3.Row]:
    """Retourne un jeu complet de rows pour un timestamp donné."""
    return [
        make_sqlite_row("bess_0_p", timestamp, "10.0"),
        make_sqlite_row("pv_0_p", timestamp, "20.0"),
        make_sqlite_row("conso_kw", timestamp, "30.0"),
        make_sqlite_row("soc_kwh", timestamp, "40.0"),
    ]


def make_mock_cursor():
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.rowcount = 1
    return cursor


def make_mock_conn(cursor=None):
    conn = MagicMock()
    conn.closed = False
    conn.cursor.return_value = cursor or make_mock_cursor()
    return conn


# ---------------------------------------------------------------------------
# Tests ForecasterConnector.__init__
# ---------------------------------------------------------------------------

class TestForecasterConnectorInit:
    def test_site_id_and_key_mapping_stored(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        assert connector.site_id == "site-01"
        assert connector.key_mapping == _KEY_MAPPING


# ---------------------------------------------------------------------------
# Tests ForecasterConnector.create_table
# ---------------------------------------------------------------------------

class TestCreateTable:
    def test_does_nothing_if_table_exists(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (True,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "ignored")

        calls_sql = [str(c) for c in cursor.execute.call_args_list]
        assert not any("CREATE TABLE" in s for s in calls_sql)
        conn.commit.assert_called_once()

    def test_creates_table_if_missing(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (False,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "ignored")

        calls_sql = " ".join(str(c) for c in cursor.execute.call_args_list)
        assert "CREATE TABLE" in calls_sql
        assert _FORECASTER_TABLE in calls_sql

    def test_always_creates_unique_index(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (True,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "ignored")

        calls_sql = " ".join(str(c) for c in cursor.execute.call_args_list)
        assert "CREATE UNIQUE INDEX" in calls_sql
        assert "uq_mesures_reelles_site_ts" in calls_sql

    def test_ignores_table_name_param(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        cursor = make_mock_cursor()
        cursor.fetchone.return_value = (True,)
        conn = make_mock_conn(cursor)

        connector.create_table(conn, "some_other_table")

        first_call = str(cursor.execute.call_args_list[0])
        assert _FORECASTER_TABLE in first_call

    def test_rollback_on_error(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        cursor = make_mock_cursor()
        cursor.fetchone.side_effect = Exception("DB error")
        conn = make_mock_conn(cursor)

        with pytest.raises(Exception, match="DB error"):
            connector.create_table(conn, "ignored")

        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Tests ForecasterConnector.push
# ---------------------------------------------------------------------------

class TestPush:
    def test_pivot_complete_timestamp(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        ts = 1700000000.0
        rows = make_complete_rows(ts)
        cursor = make_mock_cursor()
        conn = make_mock_conn(cursor)

        with patch("connectors.forecaster.execute_values") as mock_ev:
            result = connector.push(conn, "ignored", rows)

        mock_ev.assert_called_once()
        _, call_args, _ = mock_ev.mock_calls[0]
        tuples = call_args[2]
        assert len(tuples) == 1

        row_tuple = tuples[0]
        assert row_tuple[0] == "site-01"
        assert isinstance(row_tuple[1], datetime)
        assert row_tuple[1].tzinfo is not None
        assert float(row_tuple[2]) == pytest.approx(10.0)   # puissance_bess_kw
        assert float(row_tuple[3]) == pytest.approx(20.0)   # production_pv_kw
        assert float(row_tuple[4]) == pytest.approx(30.0)   # conso_kw
        assert float(row_tuple[5]) == pytest.approx(40.0)   # soc_kwh
        assert float(row_tuple[6]) == pytest.approx(0.0)    # puissance_pdl_kw default

        conn.commit.assert_called_once()

    def test_incomplete_timestamp_skipped(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        ts = 1700000000.0
        # Manque soc_kwh
        rows = [
            make_sqlite_row("bess_0_p", ts, "10.0"),
            make_sqlite_row("pv_0_p", ts, "20.0"),
            make_sqlite_row("conso_kw", ts, "30.0"),
        ]
        conn = make_mock_conn()

        with patch("connectors.forecaster.execute_values") as mock_ev:
            result = connector.push(conn, "ignored", rows)

        mock_ev.assert_not_called()
        assert result == 0
        conn.commit.assert_not_called()

    def test_pdl_default_zero_when_not_in_mapping(self):
        """puissance_pdl_kw vaut 0.0 si absent du key_mapping."""
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        assert "puissance_pdl_kw" not in _KEY_MAPPING.values()

        ts = 1700000000.0
        rows = make_complete_rows(ts)
        conn = make_mock_conn()

        with patch("connectors.forecaster.execute_values") as mock_ev:
            connector.push(conn, "ignored", rows)

        _, call_args, _ = mock_ev.mock_calls[0]
        tuples = call_args[2]
        row_tuple = tuples[0]
        assert row_tuple[-1] == pytest.approx(0.0)

    def test_pdl_in_mapping_uses_value(self):
        """puissance_pdl_kw est inséré depuis le mapping si présent."""
        mapping_with_pdl = {
            "bess_0_p": "puissance_bess_kw",
            "pv_0_p": "production_pv_kw",
            "conso_kw": "conso_kw",
            "soc_kwh": "soc_kwh",
            "pdl_kw": "puissance_pdl_kw",
        }
        connector = ForecasterConnector(site_id="site-01", key_mapping=mapping_with_pdl)
        ts = 1700000000.0
        rows = make_complete_rows(ts) + [make_sqlite_row("pdl_kw", ts, "5.5")]
        conn = make_mock_conn()

        with patch("connectors.forecaster.execute_values") as mock_ev:
            connector.push(conn, "ignored", rows)

        _, call_args, _ = mock_ev.mock_calls[0]
        tuples = call_args[2]
        row_tuple = tuples[0]
        cols = ["site_id", "timestamp"] + list(mapping_with_pdl.values())
        pdl_idx = cols.index("puissance_pdl_kw")
        assert float(row_tuple[pdl_idx]) == pytest.approx(5.5)
        assert len(row_tuple) == len(cols)

    def test_returns_zero_for_empty_rows(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        conn = make_mock_conn()

        result = connector.push(conn, "ignored", [])

        assert result == 0
        conn.commit.assert_not_called()

    def test_multiple_timestamps_partial_skip(self):
        """Seuls les timestamps complets sont insérés."""
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        ts1 = 1700000000.0
        ts2 = 1700000001.0
        rows = make_complete_rows(ts1) + [
            make_sqlite_row("bess_0_p", ts2, "11.0"),  # ts2 incomplet
        ]
        conn = make_mock_conn()

        with patch("connectors.forecaster.execute_values") as mock_ev:
            connector.push(conn, "ignored", rows)

        _, call_args, _ = mock_ev.mock_calls[0]
        tuples = call_args[2]
        assert len(tuples) == 1
        assert tuples[0][1] == datetime.fromtimestamp(ts1, tz=timezone.utc)

    def test_upsert_query_contains_on_conflict(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        ts = 1700000000.0
        rows = make_complete_rows(ts)
        conn = make_mock_conn()

        with patch("connectors.forecaster.execute_values") as mock_ev:
            connector.push(conn, "ignored", rows)

        _, call_args, _ = mock_ev.mock_calls[0]
        query = call_args[1]
        assert "ON CONFLICT" in query
        assert "DO UPDATE SET" in query

    def test_rollback_on_error(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        ts = 1700000000.0
        rows = make_complete_rows(ts)
        conn = make_mock_conn()

        with patch("connectors.forecaster.execute_values", side_effect=Exception("DB error")):
            with pytest.raises(Exception, match="DB error"):
                connector.push(conn, "ignored", rows)

        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Tests ForecasterConnector.pull
# ---------------------------------------------------------------------------

class TestPull:
    def test_reads_from_sqlite(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)

        with tempfile.TemporaryDirectory() as tmpdir:
            today = datetime.now()
            db_filename = today.strftime("%Y_%m_%d.db")
            db_path = Path(tmpdir) / db_filename

            conn_sqlite = sqlite3.connect(str(db_path))
            conn_sqlite.execute(
                'CREATE TABLE "site-01" (key TEXT, timestamp REAL, type TEXT, value TEXT)'
            )
            conn_sqlite.execute(
                'INSERT INTO "site-01" VALUES (?, ?, ?, ?)',
                ("bess_0_p", time.time(), "float", "10.0"),
            )
            conn_sqlite.commit()
            conn_sqlite.close()

            rows = connector.pull(tmpdir, "site-01", datetime(2000, 1, 1))

        assert len(rows) == 1
        assert rows[0]["key"] == "bess_0_p"
        assert rows[0]["value"] == "10.0"

    def test_returns_empty_list_on_missing_dir(self):
        connector = ForecasterConnector(site_id="site-01", key_mapping=_KEY_MAPPING)
        rows = connector.pull("/nonexistent/path", "site-01", datetime(2000, 1, 1))
        assert rows == []


# ---------------------------------------------------------------------------
# Tests ForecasterConnector.get_row_timestamp
# ---------------------------------------------------------------------------

class TestGetRowTimestamp:
    def test_float_timestamp(self):
        connector = ForecasterConnector(site_id="s", key_mapping={})
        row = make_sqlite_row("k", 1700000000.0, "1.0")
        ts = connector.get_row_timestamp(row)
        assert isinstance(ts, datetime)
        assert ts == datetime.fromtimestamp(1700000000.0)

    def test_int_timestamp(self):
        connector = ForecasterConnector(site_id="s", key_mapping={})
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
    def test_returns_forecaster_connector(self):
        connector = connector_factory("forecaster", site_id="site-01", key_mapping=_KEY_MAPPING)
        assert isinstance(connector, ForecasterConnector)
        assert connector.site_id == "site-01"
        assert connector.key_mapping == _KEY_MAPPING

    def test_returns_forecaster_connector_empty_mapping(self):
        connector = connector_factory("forecaster", site_id="site-01")
        assert isinstance(connector, ForecasterConnector)
        assert connector.key_mapping == {}

    def test_ppc_connector_unaffected(self):
        from connectors.ppc import PPCConnector
        connector = connector_factory("ppc", site_id="site-01")
        assert isinstance(connector, PPCConnector)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="not supported"):
            connector_factory("unknown")
