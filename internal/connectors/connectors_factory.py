from connectors.connectors_interface import ConnectorInterface
from connectors.forecaster import ForecasterConnector
from connectors.ppc import PPCConnector
from connectors.psn import PSNConnector


def connector_factory(
    connector_type: str,
    site_id: str = "",
    key_mapping: dict[str, str] | None = None,
    bucket_seconds: int = 1,
) -> ConnectorInterface:
    if connector_type == "ppc":
        return PPCConnector(site_id=site_id)
    elif connector_type == "psn":
        return PSNConnector()
    elif connector_type == "forecaster":
        return ForecasterConnector(site_id=site_id, key_mapping=key_mapping or {}, bucket_seconds=bucket_seconds)
    else:
        raise ValueError("Connector type " + connector_type + " not supported")
