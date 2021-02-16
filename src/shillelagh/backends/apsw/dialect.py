import json
from typing import Any
from typing import cast
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import apsw
import sqlalchemy.types
from shillelagh.adapters.base import Adapter
from shillelagh.backends.apsw import db
from shillelagh.backends.apsw.vt import VTTable
from shillelagh.exceptions import ProgrammingError
from sqlalchemy import exc
from sqlalchemy.dialects.sqlite.base import SQLiteDialect
from sqlalchemy.engine.url import URL
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.pool.base import _ConnectionFairy


class APSWDialect(SQLiteDialect):
    name = "shillelagh"
    driver = "apsw"

    @classmethod
    def dbapi(cls):
        return db

    def __init__(
        self,
        adapters: Optional[List[str]] = None,
        adapter_args: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._adapters = adapters
        self._adapter_args = adapter_args

    def create_connect_args(
        self,
        url: URL,
    ) -> Tuple[
        Tuple[str, Optional[List[str]], Optional[Dict[str, Any]], Optional[str]],
        Dict[str, Any],
    ]:
        path = str(url.database) or ":memory:"
        return ((path, self._adapters, self._adapter_args, self.isolation_level), {})

    def do_ping(self, dbapi_connection: _ConnectionFairy) -> bool:
        return True

    def get_columns(self, connection, table_name, schema=None, **kw):
        adapter = self._get_adapter_for_table_name(connection, table_name)
        columns = adapter.get_columns()
        return [
            {
                "name": column_name,
                "type": getattr(sqlalchemy.types, field.type),
                "nullable": True,
                "default": None,
                "autoincrement": "auto",
                "primary_key": 0,
            }
            for column_name, field in columns.items()
        ]

    def _get_table_sql(self, connection, table_name, schema=None, **kw) -> str:
        adapter = self._get_adapter_for_table_name(connection, table_name)
        table = VTTable(adapter)
        return table.get_create_table(table_name)

    def _get_adapter_for_table_name(self, connection, table_name) -> Adapter:
        raw_connection = cast(db.Connection, connection.engine.raw_connection())
        for adapter in raw_connection._adapters:
            if adapter.supports(table_name):
                break
        else:
            raise ProgrammingError(f"Unsupported table: {table_name}")

        uri_args = adapter.parse_uri(table_name)
        adapter_args = raw_connection._adapter_args.get(adapter.__name__.lower(), ())
        return adapter(*uri_args, *adapter_args)


class APSWGSheetsDialect(APSWDialect):
    """Drop-in replacement for gsheetsdb."""

    name = "gsheets"

    def __init__(
        self,
        service_account_file: Optional[str] = None,
        service_account_info: Optional[Dict[str, Any]] = None,
        subject: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)

        self.service_account_info = service_account_info
        if service_account_file:
            with open(service_account_file) as fp:
                self.service_account_info = json.load(fp)
        self.subject = subject

    def create_connect_args(
        self,
        url: URL,
    ) -> Tuple[
        Tuple[str, Optional[List[str]], Optional[Dict[str, Any]], Optional[str]],
        Dict[str, Any],
    ]:
        adapter_args: Dict[str, Any] = {}
        if self.service_account_info:
            adapter_args["gsheetsapi"] = (self.service_account_info, self.subject)

        return (":memory:", ["gsheetsapi"], adapter_args, self.isolation_level), {}
