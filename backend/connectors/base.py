from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConnectionConfig:
    source_id: str
    source_type: str  # postgres | sqlserver | mysql | oracle | snowflake | mongodb | ...
    connection_params: dict
    secret_ref: Optional[str] = None  # e.g. azurekeyvault://vault-name/secret-name
    sample_size: int = 100
    pii_aware_sampling: bool = True
    tenant_id: Optional[str] = None


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    nullable: bool
    is_pk: bool
    is_fk: bool
    default: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class TableMetadata:
    schema_name: str
    table_name: str
    row_count: int
    columns: list[dict]  # list of ColumnMeta as dicts for JSON serialisation
    sample_rows: list[dict]
    change_hash: str  # MD5 of schema fingerprint for incremental detection
    source_system_type: str = ""
    extra: dict = field(default_factory=dict)

    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"


class BaseConnector(ABC):
    """Abstract base for all source connectors.
    All connectors MUST be read-only and use least-privilege credentials.
    """

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    # ── Abstract interface ─────────────────────────────────────────────────
    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if connection is healthy."""
        ...

    @abstractmethod
    def list_tables(self) -> list[str]:
        """Return list of fully-qualified table names (schema.table)."""
        ...

    @abstractmethod
    def extract_table_metadata(self, table_name: str) -> TableMetadata:
        """Extract schema, stats, and samples for a single table."""
        ...

    # ── Shared helpers ─────────────────────────────────────────────────────
    def _resolve_secret(self, secret_ref: str) -> str:
        """Resolve credentials from Azure Key Vault, AWS Secrets Manager, or env."""
        if secret_ref.startswith("azurekeyvault://"):
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
            path = secret_ref.replace("azurekeyvault://", "")
            vault_name, secret_name = path.split("/", 1)
            client = SecretClient(
                vault_url=f"https://{vault_name}.vault.azure.net",
                credential=DefaultAzureCredential(),
            )
            return client.get_secret(secret_name).value

        elif secret_ref.startswith("awssecrets://"):
            import boto3
            secret_name = secret_ref.replace("awssecrets://", "")
            sm = boto3.client("secretsmanager")
            response = sm.get_secret_value(SecretId=secret_name)
            return json.loads(response["SecretString"])

        elif secret_ref.startswith("env://"):
            import os
            env_var = secret_ref.replace("env://", "")
            value = os.getenv(env_var)
            if not value:
                raise ValueError(f"Environment variable '{env_var}' not set")
            return value

        raise ValueError(f"Unknown secret store prefix in: {secret_ref}")

    @staticmethod
    def _compute_schema_hash(columns: list[dict]) -> str:
        """Stable MD5 fingerprint of column schema for change detection."""
        serialised = json.dumps(
            [{k: v for k, v in col.items() if k != "default"} for col in columns],
            sort_keys=True,
        )
        return hashlib.md5(serialised.encode()).hexdigest()
