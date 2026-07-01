import json
import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from app.core.types.common import NodeInput
from app.nodes.built_in.databases.sqlite.sqlite_node import SQLiteDBExecutor

@pytest.mark.asyncio
async def test_sqlite_connection_positive():
    node = SQLiteDBExecutor()
    config = {
        "path": "test-sqlite.db",
        "timeout": 10.0
    }
    
    with patch("sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = await node.get_connection(config)
        
        mock_connect.assert_called_once_with("test-sqlite.db", timeout=10.0)
        assert conn == mock_conn

@pytest.mark.asyncio
async def test_sqlite_connection_negative():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-conn-fail",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users"
        }),
        config={"path": "bad.db"}
    )
    
    with patch("sqlite3.connect", side_effect=sqlite3.Error("Connection error")):
        result = await node.run(inp)
        assert result.status == "failure"
        assert "Connection error" in result.error_message

@pytest.mark.asyncio
async def test_sqlite_query_execution_error():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-exec-fail",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users"
        }),
        config={"path": "test.db"}
    )
    
    with patch.object(SQLiteDBExecutor, "get_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = sqlite3.Error("Query execution syntax error")
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        result = await node.run(inp)
        
        assert result.status == "failure"
        assert "Query execution syntax error" in result.error_message

@pytest.mark.asyncio
async def test_sqlite_select_all_fields_no_where():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-select-all",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users"
        }),
        config={"path": "test.db"}
    )
    
    with patch.object(SQLiteDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(SQLiteDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = [{"id": 1, "name": "Alice"}]
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             'SELECT * FROM "users"',
             "select",
             []
         )
         assert json.loads(result.data) == [{"id": 1, "name": "Alice"}]

@pytest.mark.asyncio
async def test_sqlite_select_selected_fields_with_where():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-select-where",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users",
            "field_names": ["id", "name"],
            "condition": "age > ?",
            "condition_params": [21]
        }),
        config={"path": "test.db"}
    )
    
    with patch.object(SQLiteDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(SQLiteDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = [{"id": 1, "name": "Alice"}]
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             'SELECT "id", "name" FROM "users" WHERE age > ?',
             "select",
             [21]
         )

@pytest.mark.asyncio
async def test_sqlite_insert_query_positive():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-insert",
        data=json.dumps({
            "query_type": "insert",
            "table_name": "users",
            "fields": {"name": "Bob", "age": 30}
        }),
        config={"path": "test.db"}
    )
    
    with patch.object(SQLiteDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(SQLiteDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = {"rowcount": 1, "lastrowid": 10}
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             'INSERT INTO "users" ("name", "age") VALUES (?, ?)',
             "insert",
             ["Bob", 30]
         )

@pytest.mark.asyncio
async def test_sqlite_update_query_positive():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-update",
        data=json.dumps({
            "query_type": "update",
            "table_name": "users",
            "fields": {"age": 31},
            "condition": "name = ?",
            "condition_params": ["Alice"]
        }),
        config={"path": "test.db"}
    )
    
    with patch.object(SQLiteDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(SQLiteDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = {"rowcount": 1, "lastrowid": None}
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             'UPDATE "users" SET "age" = ? WHERE name = ?',
             "update",
             [31, "Alice"]
         )

@pytest.mark.asyncio
async def test_sqlite_update_query_negative_missing_condition():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-update-fail",
        data=json.dumps({
            "query_type": "update",
            "table_name": "users",
            "fields": {"age": 31}
        }),
        config={"path": "test.db"}
    )
    
    result = await node.run(inp)
    assert result.status == "failure"
    assert "condition (WHERE clause) is required" in result.error_message

@pytest.mark.asyncio
async def test_sqlite_delete_query_positive():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-delete",
        data=json.dumps({
            "query_type": "delete",
            "table_name": "users",
            "condition": "id = ?",
            "condition_params": [4]
        }),
        config={"path": "test.db"}
    )
    
    with patch.object(SQLiteDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(SQLiteDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = {"rowcount": 1, "lastrowid": None}
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             'DELETE FROM "users" WHERE id = ?',
             "delete",
             [4]
         )

@pytest.mark.asyncio
async def test_sqlite_delete_query_negative_missing_condition():
    node = SQLiteDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-delete-fail",
        data=json.dumps({
            "query_type": "delete",
            "table_name": "users"
        }),
        config={"path": "test.db"}
    )
    
    result = await node.run(inp)
    assert result.status == "failure"
    assert "condition (WHERE clause) is required" in result.error_message
