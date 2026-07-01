import json
import pytest
from unittest.mock import MagicMock, patch
from app.core.types.common import NodeInput
from app.nodes.built_in.databases.mysql.generic_mysql_node import GenericMySQLDBExecutor
import mysql.connector

@pytest.mark.asyncio
async def test_mysql_node_connection_positive():
    node = GenericMySQLDBExecutor()
    config = {
        "host": "test-host",
        "port": "3306",
        "user": "test-user",
        "password": "test-password",
        "database": "test-db"
    }
    
    with patch("mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = await node.get_connection(config)
        
        mock_connect.assert_called_once_with(
            host="test-host",
            user="test-user",
            passwd="test-password",
            database="test-db",
            port=3306
        )
        assert conn == mock_conn

@pytest.mark.asyncio
async def test_mysql_node_connection_negative():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-conn-fail",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users"
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch("mysql.connector.connect", side_effect=mysql.connector.Error(msg="Connection refused")):
        result = await node.run(inp)
        assert result.status == "failure"
        assert "Connection refused" in result.error_message

@pytest.mark.asyncio
async def test_mysql_node_query_execution_error():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-exec-fail",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users"
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = mysql.connector.Error(msg="Syntax error")
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        result = await node.run(inp)
        
        assert result.status == "failure"
        assert "Syntax error" in result.error_message

@pytest.mark.asyncio
async def test_mysql_node_execute_raw_query():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-raw",
        data=json.dumps({
            "query_type": "raw",
            "query": "SELECT * FROM users WHERE status = {{ data.status }}",
            "data": {"status": "active"},
            "params": {"status": "active"}
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(GenericMySQLDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = [{"id": 1, "name": "Alice"}]
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             "SELECT * FROM users WHERE status = active",
             "raw",
             {"status": "active"}
         )
         assert json.loads(result.data) == [{"id": 1, "name": "Alice"}]

@pytest.mark.asyncio
async def test_mysql_node_select_all_fields_no_where():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-select-all",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users"
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(GenericMySQLDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = [{"id": 1, "name": "Alice"}]
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             "SELECT * FROM `users`",
             "select",
             []
         )

@pytest.mark.asyncio
async def test_mysql_node_select_selected_fields_with_where():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-select-where",
        data=json.dumps({
            "query_type": "select",
            "table_name": "users",
            "field_names": ["id", "name"],
            "condition": "age > %s",
            "condition_params": [21]
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(GenericMySQLDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = [{"id": 1, "name": "Alice"}]
         
         result = await node.run(inp)
         
         assert result.status == "success"
         mock_exec_query.assert_called_once_with(
             mock_conn,
             "SELECT `id`, `name` FROM `users` WHERE age > %s",
             "select",
             [21]
         )

@pytest.mark.asyncio
async def test_mysql_node_execute_insert_query_positive():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-insert",
        data=json.dumps({
            "query_type": "insert",
            "table_name": "users",
            "fields": {"name": "Bob", "email": "bob@example.com"}
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(GenericMySQLDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = {"rowcount": 1, "lastrowid": 10}
         
         result = await node.run(inp)
         
         assert result.status == "success"
         sql_arg = mock_exec_query.call_args[0][1]
         assert "INSERT INTO `users`" in sql_arg
         assert "%s" in sql_arg
         assert "?" not in sql_arg

@pytest.mark.asyncio
async def test_mysql_node_execute_update_query_positive():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-update",
        data=json.dumps({
            "query_type": "update",
            "table_name": "users",
            "fields": {"status": "inactive"},
            "condition": "id = %s",
            "condition_params": [5]
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(GenericMySQLDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = {"rowcount": 1, "lastrowid": None}
         
         result = await node.run(inp)
         
         assert result.status == "success"
         sql_arg = mock_exec_query.call_args[0][1]
         params_arg = mock_exec_query.call_args[0][3]
         
         assert "UPDATE `users` SET `status` = %s WHERE id = %s" in sql_arg
         assert params_arg == ["inactive", 5]

@pytest.mark.asyncio
async def test_mysql_node_update_query_negative_missing_condition():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-update-fail",
        data=json.dumps({
            "query_type": "update",
            "table_name": "users",
            "fields": {"status": "inactive"}
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    result = await node.run(inp)
    assert result.status == "failure"
    assert "condition (WHERE clause) is required" in result.error_message

@pytest.mark.asyncio
async def test_mysql_node_execute_delete_query_positive():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-delete",
        data=json.dumps({
            "query_type": "delete",
            "table_name": "users",
            "condition": "id = %s",
            "condition_params": [10]
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    with patch.object(GenericMySQLDBExecutor, "get_connection") as mock_get_conn, \
         patch.object(GenericMySQLDBExecutor, "execute_query") as mock_exec_query:
         
         mock_conn = MagicMock()
         mock_get_conn.return_value = mock_conn
         mock_exec_query.return_value = {"rowcount": 1, "lastrowid": None}
         
         result = await node.run(inp)
         
         assert result.status == "success"
         sql_arg = mock_exec_query.call_args[0][1]
         params_arg = mock_exec_query.call_args[0][3]
         
         assert "DELETE FROM `users` WHERE id = %s" in sql_arg
         assert params_arg == [10]

@pytest.mark.asyncio
async def test_mysql_node_delete_query_negative_missing_condition():
    node = GenericMySQLDBExecutor()
    inp = NodeInput(
        trace_id="test-trace-delete-fail",
        data=json.dumps({
            "query_type": "delete",
            "table_name": "users"
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    result = await node.run(inp)
    assert result.status == "failure"
    assert "condition (WHERE clause) is required" in result.error_message

@pytest.mark.asyncio
async def test_mysql_node_validation_failures():
    node = GenericMySQLDBExecutor()
    
    # Missing table name for select
    inp = NodeInput(
        trace_id="test-trace-val-fail",
        data=json.dumps({
            "query_type": "select"
        }),
        config={
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pwd",
            "database": "db"
        }
    )
    
    result = await node.run(inp)
    assert result.status == "failure"
    assert "table_name is required" in result.error_message

    # Missing fields for insert
    inp2 = NodeInput(
        trace_id="test-trace-val-fail-2",
        data=json.dumps({
            "query_type": "insert",
            "table_name": "users"
        }),
        config=inp.config
    )
    result2 = await node.run(inp2)
    assert result2.status == "failure"
    assert "Either 'fields' or 'field_names' & 'field_values' must be provided" in result2.error_message
