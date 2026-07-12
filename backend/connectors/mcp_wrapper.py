"""MCP Connector Wrapper — reuses existing MCP database servers as SourceDesc connectors.

Supported MCP servers:
  - @modelcontextprotocol/server-postgres
  - DBHub by Bytebase (MySQL, PostgreSQL, SQL Server, MariaDB)
  - AnythingMCP (PG, MySQL, MSSQL, Oracle, MongoDB)
  - @mongodb-js/mongodb-mcp-server

This avoids re-implementing connectors for standard databases.
"""
import asyncio
import json
from .base import BaseConnector, ConnectionConfig, TableMetadata


class MCPConnectorWrapper(BaseConnector):
    """Wraps any MCP database server as a SourceDesc connector."""

    def __init__(self, config: ConnectionConfig, mcp_server_cmd: list[str]):
        """
        Args:
            config: Standard ConnectionConfig
            mcp_server_cmd: Command to launch MCP server, e.g.
                ['npx', '-y', '@modelcontextprotocol/server-postgres', 'postgresql://...']
        """
        super().__init__(config)
        self.mcp_server_cmd = mcp_server_cmd

    async def _call_tool(self, tool_name: str, args: dict) -> dict:
        """Launch MCP server subprocess and call a tool."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise ImportError(
                "mcp package required for MCP connectors: pip install mcp"
            )

        # Inject resolved secret into env if needed
        env = {}
        if self.config.secret_ref:
            env["DATABASE_PASSWORD"] = self._resolve_secret(self.config.secret_ref)

        server_params = StdioServerParameters(
            command=self.mcp_server_cmd[0],
            args=self.mcp_server_cmd[1:],
            env=env or None,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                if result.content:
                    return json.loads(result.content[0].text)
                return {}

    def _run(self, coro):
        """Run coroutine in event loop, handling already-running loops."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            return asyncio.run(coro)

    def test_connection(self) -> bool:
        try:
            result = self._run(self._call_tool("query", {"sql": "SELECT 1 AS ok"}))
            return bool(result)
        except Exception as exc:
            self.logger.error("MCP connection test failed: %s", exc)
            return False

    def list_tables(self) -> list[str]:
        """Use MCP server's schema listing capability."""
        result = self._run(self._call_tool(
            "query",
            {
                "sql": (
                    "SELECT schemaname || '.' || tablename AS qualified_name "
                    "FROM pg_tables "
                    "WHERE schemaname NOT IN ('pg_catalog','information_schema','pg_toast') "
                    "ORDER BY schemaname, tablename"
                )
            },
        ))
        rows = result.get("rows", [])
        return [r[0] if isinstance(r, list) else r.get("qualified_name", "") for r in rows]

    def extract_table_metadata(self, qualified_name: str) -> TableMetadata:
        schema, table = qualified_name.split(".", 1)

        # Get column schema
        schema_result = self._run(self._call_tool(
            "query",
            {
                "sql": f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = '{table}'
                    ORDER BY ordinal_position
                """
            },
        ))

        columns = [
            {
                "name": row[0] if isinstance(row, list) else row["column_name"],
                "data_type": row[1] if isinstance(row, list) else row["data_type"],
                "nullable": (row[2] if isinstance(row, list) else row["is_nullable"]) == "YES",
                "is_pk": False,
                "is_fk": False,
                "default": None,
            }
            for row in schema_result.get("rows", [])
        ]

        # Get row count
        count_result = self._run(self._call_tool(
            "query", {"sql": f'SELECT COUNT(*) FROM "{schema}"."{table}"'}
        ))
        count_rows = count_result.get("rows", [[0]])
        row_count = count_rows[0][0] if count_rows else 0

        # Get sample data
        sample_result = self._run(self._call_tool(
            "query",
            {"sql": f'SELECT * FROM "{schema}"."{table}" LIMIT {self.config.sample_size}'},
        ))
        sample_rows = [
            dict(zip([c["name"] for c in columns], row)) if isinstance(row, list) else row
            for row in sample_result.get("rows", [])[:5]
        ]

        return TableMetadata(
            schema_name=schema,
            table_name=table,
            row_count=row_count,
            columns=columns,
            sample_rows=sample_rows,
            change_hash=self._compute_schema_hash(columns),
            source_system_type=f"mcp:{self.config.source_type}",
        )
