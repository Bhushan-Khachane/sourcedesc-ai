"""NoSQL connectors: MongoDB, Cassandra."""
import json
import hashlib
from .base import BaseConnector, ConnectionConfig, TableMetadata


class MongoConnector(BaseConnector):
    """MongoDB connector — reads collection schemas via document sampling."""

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        from pymongo import MongoClient

        p = dict(config.connection_params)
        if config.secret_ref:
            secret = self._resolve_secret(config.secret_ref)
            if isinstance(secret, dict):
                p.update(secret)
            else:
                p["password"] = secret

        uri = (
            p.get("uri")
            or f"mongodb://{p['user']}:{p['password']}@{p['host']}:{p.get('port', 27017)}/{p['database']}"
        )
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db_name = p["database"]

    def test_connection(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception as exc:
            self.logger.error("MongoDB connection failed: %s", exc)
            return False

    def list_tables(self) -> list[str]:
        db = self.client[self.db_name]
        return [f"{self.db_name}.{col}" for col in db.list_collection_names()]

    def extract_table_metadata(self, qualified_name: str) -> TableMetadata:
        _, collection_name = qualified_name.split(".", 1)
        db = self.client[self.db_name]
        collection = db[collection_name]

        row_count = collection.estimated_document_count()

        # Infer schema by sampling documents and merging field sets
        sample_docs = list(collection.find({}, limit=self.config.sample_size))
        inferred_fields: dict[str, set] = {}
        for doc in sample_docs:
            for key, value in doc.items():
                if key == "_id":
                    continue
                inferred_fields.setdefault(key, set()).add(type(value).__name__)

        columns = [
            {
                "name": field,
                "data_type": " | ".join(sorted(types)),
                "nullable": True,
                "is_pk": False,
                "is_fk": False,
                "default": None,
            }
            for field, types in inferred_fields.items()
        ]

        # Sanitise samples — convert ObjectId / datetime to str
        clean_samples = [
            {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
             for k, v in doc.items() if k != "_id"}
            for doc in sample_docs[:5]
        ]

        return TableMetadata(
            schema_name=self.db_name,
            table_name=collection_name,
            row_count=row_count,
            columns=columns,
            sample_rows=clean_samples,
            change_hash=self._compute_schema_hash(columns),
            source_system_type="mongodb",
        )


class CassandraConnector(BaseConnector):
    """Cassandra connector via cassandra-driver."""

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        from cassandra.cluster import Cluster
        from cassandra.auth import PlainTextAuthProvider

        p = dict(config.connection_params)
        if config.secret_ref:
            secret = self._resolve_secret(config.secret_ref)
            p.update(secret if isinstance(secret, dict) else {"password": secret})

        auth = PlainTextAuthProvider(p["user"], p["password"])
        self.cluster = Cluster(contact_points=[p["host"]], auth_provider=auth)
        self.keyspace = p["database"]

    def test_connection(self) -> bool:
        try:
            session = self.cluster.connect()
            session.execute("SELECT release_version FROM system.local")
            return True
        except Exception as exc:
            self.logger.error("Cassandra connection failed: %s", exc)
            return False

    def list_tables(self) -> list[str]:
        session = self.cluster.connect(self.keyspace)
        rows = session.execute(
            "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
            [self.keyspace],
        )
        return [f"{self.keyspace}.{row.table_name}" for row in rows]

    def extract_table_metadata(self, qualified_name: str) -> TableMetadata:
        keyspace, table = qualified_name.split(".", 1)
        session = self.cluster.connect(keyspace)

        col_rows = session.execute(
            "SELECT column_name, type, kind FROM system_schema.columns "
            "WHERE keyspace_name=%s AND table_name=%s",
            [keyspace, table],
        )
        columns = [
            {
                "name": row.column_name,
                "data_type": row.type,
                "nullable": True,
                "is_pk": row.kind in ("partition_key", "clustering"),
                "is_fk": False,
                "default": None,
            }
            for row in col_rows
        ]

        sample_rows = list(session.execute(f"SELECT * FROM {table} LIMIT {self.config.sample_size}"))
        row_count_result = session.execute(f"SELECT COUNT(*) FROM {table}")
        row_count = row_count_result.one()[0] if row_count_result else 0

        return TableMetadata(
            schema_name=keyspace,
            table_name=table,
            row_count=row_count,
            columns=columns,
            sample_rows=[dict(r._asdict()) for r in sample_rows[:5]],
            change_hash=self._compute_schema_hash(columns),
            source_system_type="cassandra",
        )
