from connectors.connectors_interface import ConnectorInterface
from connectors.ppc import PPCConnector
from connectors.psn import PSNConnector


def connector_factory(connector_type: str, site_id: str = "") -> ConnectorInterface:
    if connector_type == "ppc":
        return PPCConnector(site_id=site_id)
    elif connector_type == "psn":
        return PSNConnector()
    else:
        raise ValueError("Connector type " + connector_type + " not supported")
