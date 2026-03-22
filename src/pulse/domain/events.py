from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Event:
    id: str
    timestamp: datetime
    source: str
    event_type: str
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
