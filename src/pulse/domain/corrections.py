from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Correction:
    id: str
    context_id: str
    message_text: str
    created_at: datetime
