from abc import ABC, abstractmethod
from typing import Any
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
    def get_rows_from_sqlite(
        self, db_dir: str, table_name: str, last_timestamp: datetime
    ) -> list[tuple[Any, ...]]:
        pass
