from pulse.app.config import PulseConfig
from pulse.connectors.registry import ConnectorRegistry


def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    from pulse.connectors.gmail import GmailConnector
    from pulse.connectors.calendar import GoogleCalendarConnector

    registry.register_pull("gmail", lambda: GmailConnector(client=None))
    registry.register_pull("calendar", lambda: GoogleCalendarConnector(client=None))
    # YouTube and GoogleAuthManager integration will be added in Tasks 4-6
