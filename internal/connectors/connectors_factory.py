from connectors.connectors_interface import ConnectorInterface
from connectors.ppc import PPCConnector


def connector_factory(connector_type: str) -> ConnectorInterface:
    if connector_type == "ppc":
        return PPCConnector()
    else:
        raise ValueError(f"Connector type {connector_type} not supported")
