"""Deal paging must compile for SQL Server, which requires ORDER BY when paging.

SQLite accepts OFFSET/LIMIT without an ORDER BY, so the original unordered
query worked locally but would fail against Azure SQL.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import CompileError

from database import PropertyDeal
from routers.deals import list_statement


def compile_for_sql_server(statement) -> str:
    return str(statement.compile(dialect=mssql.dialect()))


def test_paged_deals_query_compiles_for_sql_server():
    sql = compile_for_sql_server(list_statement("sheriff_sale", 10, 50))

    assert "ORDER BY property_deals.id" in sql


def test_sql_server_rejects_paging_without_order_by():
    # The query list_statement replaced: this is why it orders by id.
    unordered = select(PropertyDeal).offset(10).limit(50)

    with pytest.raises(CompileError):
        compile_for_sql_server(unordered)
