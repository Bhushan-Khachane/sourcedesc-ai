"""Connector factory — resolves source_type to correct connector class."""
from .base import ConnectionConfig, BaseConnector


RELATIONAL_TYPES = {"postgres", "sqlserver", "mysql", "oracle", "snowflake"}
NOSQL_TYPES = {"mongodb", "cassandra"}


class ConnectorFactory:
    @staticmethod
    def create(config: ConnectionConfig) -> BaseConnector:
        stype = config.source_type.lower()

        if stype in RELATIONAL_TYPES:
            from .relational import RelationalConnector
            return RelationalConnector(config)

        elif stype == "mongodb":
            from .nosql import MongoConnector
            return MongoConnector(config)

        elif stype == "cassandra":
            from .nosql import CassandraConnector
            return CassandraConnector(config)

        elif stype == "adls":
            from .storage import ADLSConnector
            return ADLSConnector(config)

        elif stype == "s3":
            from .storage import S3Connector
            return S3Connector(config)

        elif stype == "salesforce":
            from .saas import SalesforceConnector
            return SalesforceConnector(config)

        elif stype.startswith("mcp:"):
            raise ValueError(
                "MCPConnectorWrapper requires mcp_server_cmd — instantiate directly."
            )

        else:
            raise ValueError(f"Unsupported source type: '{stype}'")
