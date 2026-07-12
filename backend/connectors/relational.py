"""Relational database connector supporting PostgreSQL, SQL Server, MySQL, Oracle, Snowflake."""
from sqlalchemy import create_engine, text, inspect
from .base import BaseConnector, ConnectionConfig, TableMetadata


DIALECTS = {
    "postgres":  "postgresql+psycopg2",
    "sqlserver": "mssql+pyodbc",
    "mysql":     "mysql+pymysql",
    "oracle":    "oracle+cx_oracle",
    "snowflake": "snowflake+snowflake-sqlalchemy",
}

SYSTEM_SCHEMAS = {
    "postgres":  {"information_schema", "pg_catalog", "pg_toast"},
    "sqlserver": {"sys", "information_schema", "INFORMATION_SCHEMA"},
    "mysql":     {"information_schema", "performance_schema", "mysql", "sys"},
    "oracle":    {"SYS", "SYSTEM", "OUTLN"},
    "snowflake": {"INFORMATION_SCHEMA"},
}

PII_COLUMN_PATTERNS = [
    "email", "phone", "ssn", "dob", "birth", "passport",
    "credit_card", "password", "hash", "address", "nric",
]


class RelationalConnector(BaseConnector):
    """Handles: postgres, sqlserver, mysql, oracle, snowflake."""

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        p = dict(config.connection_params)  # shallow copy

        # Resolve credentials from secrets backend
        if config.secret_ref:
            secret_val = self._resolve_secret(config.secret_ref)
            if isinstance(secret_val, dict):
                p.update(secret_val)
            else:
                p["password"] = secret_val

        dialect = DIALECTS[config.source_type]
        port = p.get("port", 5432)
        dsn = f"{dialect}://{p['user']}:{p['password']}@{p['host']}:{port}/{p['database']}"

        # Build connect_args for read-only enforcement per dialect
        connect_args = {}
        if config.source_type == "postgres":
            connect_args = {"options": "-c default_transaction_read_only=on"}
        elif config.source_type == "sqlserver":
            dsn += "?driver=ODBC+Driver+18+for+SQL+Server"

        self.engine = create_engine(
            dsn,
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._system_schemas = SYSTEM_SCHEMAS.get(config.source_type, set())

    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            self.logger.error("Connection test failed: %s", exc)
            return False

    def list_tables(self) -> list[str]:
        inspector = inspect(self.engine)
        tables = []
        for schema in inspector.get_schema_names():
            if schema in self._system_schemas:
                continue
            for tbl in inspector.get_table_names(schema=schema):
                tables.append(f"{schema}.{tbl}")
        return tables

    def extract_table_metadata(self, qualified_name: str) -> TableMetadata:
        schema, table = qualified_name.split(".", 1)
        inspector = inspect(self.engine)

        # Schema introspection
        raw_cols = inspector.get_columns(table, schema=schema)
        pk_set = set(
            inspector.get_pk_constraint(table, schema=schema).get("constrained_columns", [])
        )
        fk_set = {
            fk["constrained_columns"][0]
            for fk in inspector.get_foreign_keys(table, schema=schema)
            if fk["constrained_columns"]
        }

        columns = [
            {
                "name": col["name"],
                "data_type": str(col["type"]),
                "nullable": bool(col.get("nullable", True)),
                "is_pk": col["name"] in pk_set,
                "is_fk": col["name"] in fk_set,
                "default": str(col["default"]) if col.get("default") is not None else None,
            }
            for col in raw_cols
        ]

        with self.engine.connect() as conn:
            # Approximate row count
            row_count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            ).scalar() or 0

            # PII-aware column selection for sampling
            if self.config.pii_aware_sampling:
                safe_cols = [
                    f'"{c["name"]}"'
                    for c in columns
                    if not any(p in c["name"].lower() for p in PII_COLUMN_PATTERNS)
                ]
                select_cols = ", ".join(safe_cols) if safe_cols else "*"
            else:
                select_cols = "*"

            rows = conn.execute(
                text(f'SELECT {select_cols} FROM "{schema}"."{table}" LIMIT {self.config.sample_size}')
            ).mappings().all()

        return TableMetadata(
            schema_name=schema,
            table_name=table,
            row_count=row_count,
            columns=columns,
            sample_rows=[dict(r) for r in rows],
            change_hash=self._compute_schema_hash(columns),
            source_system_type=self.config.source_type,
        )
