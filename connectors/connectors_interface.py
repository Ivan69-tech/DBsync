from abc import ABC, abstractmethod
import sqlite3
from psycopg2.extensions import connection
from datetime import datetime


class ConnectorInterface(ABC):
    @abstractmethod
    def connect(
        self,
        dbname: str,
        user: str,
        password: str,
        host: str,
        port: str | int,
    ) -> connection:
        pass

    @abstractmethod
    def disconnect(self, conn: connection):
        pass

    @abstractmethod
    def create_table(
        self,
        conn: connection,
        table_name: str,
    ):
        pass

    @abstractmethod
    def pull(
        self, db_dir: str, table_name: str, last_timestamp: datetime
    ) -> list[sqlite3.Row]:
        pass

    @abstractmethod
    def push(
        self,
        conn: connection,
        table_name: str,
        rows: list[sqlite3.Row],
    ) -> int:
        pass
