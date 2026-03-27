from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CorrectionApplication:
    id: str
    correction_id: str
    status: str
    target_type: str
    target_ref: str
    operation: str
    summary: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
