import logging
from collections.abc import Callable

from pulse.app.config import ConnectorConfig, PulseConfig
from pulse.domain.connectors import Connector, PushConnector

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    def __init__(self) -> None:
        self._pull_factories: dict[str, Callable[[], Connector]] = {}
        self._push_factories: dict[str, Callable[[], PushConnector]] = {}
        self._active_pull: list[tuple[Connector, ConnectorConfig]] = []
        self._active_push: list[tuple[PushConnector, ConnectorConfig]] = []

    def register_pull(self, name: str, factory: Callable[[], Connector]) -> None:
        self._pull_factories[name] = factory

    def register_push(self, name: str, factory: Callable[[], PushConnector]) -> None:
        self._push_factories[name] = factory

    async def build_active_connectors(self, config: PulseConfig) -> None:
        self._active_pull = []
        self._active_push = []

        for name, cc in config.connectors.items():
            if not cc.enabled:
                logger.info("Connector '%s' is disabled, skipping", name)
                continue

            if name in self._pull_factories:
                instance = self._pull_factories[name]()
                if not await instance.validate_config():
                    logger.warning(
                        "Connector '%s' failed config validation, skipping", name
                    )
                    continue
                self._active_pull.append((instance, cc))

            elif name in self._push_factories:
                instance = self._push_factories[name]()
                if not await instance.validate_config():
                    logger.warning(
                        "Connector '%s' failed config validation, skipping", name
                    )
                    continue
                self._active_push.append((instance, cc))

            else:
                logger.warning(
                    "Config entry '%s' has no registered connector class, skipping", name
                )

    def get_pull_connectors(self) -> list[tuple[Connector, ConnectorConfig]]:
        return list(self._active_pull)

    def get_push_connectors(self) -> list[tuple[PushConnector, ConnectorConfig]]:
        return list(self._active_push)
