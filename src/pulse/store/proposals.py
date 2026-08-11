"""Queue of proposed corrections to the factual half of the profile.

Facts are the only part of a self-description an agent can legitimately maintain: they
have a truth value the data can check. Even so, nothing is applied without the user
saying yes — a wrong inference silently written into a profile is worse than a stale
one, because a stale profile is at least visibly stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import aiosqlite

PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
SUPERSEDED = "superseded"


@dataclass(slots=True)
class FactProposal:
    id: str
    field: str
    current_value: str | None
    proposed_value: str
    evidence: str
    status: str
    created_at: str
    decided_at: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "field": self.field,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "evidence": self.evidence,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
        }


def _row(r) -> FactProposal:
    return FactProposal(
        id=r[0],
        field=r[1],
        current_value=r[2],
        proposed_value=r[3],
        evidence=r[4],
        status=r[5],
        created_at=r[6],
        decided_at=r[7],
    )


_COLUMNS = (
    "id, field, current_value, proposed_value, evidence, status, created_at, decided_at"
)


class FactProposalRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def propose(
        self,
        *,
        field: str,
        proposed_value: str,
        evidence: str,
        current_value: str | None = None,
        now: str | None = None,
    ) -> FactProposal:
        """Queue a proposal, superseding any pending one for the same field.

        Re-proposing the same field replaces the earlier suggestion rather than
        stacking: two pending answers to one question is not a queue, it is a bug.
        """
        stamp = now or datetime.now(UTC).isoformat()
        await self._db.execute(
            "UPDATE fact_proposals SET status = ?, decided_at = ? "
            "WHERE field = ? AND status = ?",
            (SUPERSEDED, stamp, field, PENDING),
        )
        proposal = FactProposal(
            id=uuid4().hex[:12],
            field=field,
            current_value=current_value,
            proposed_value=proposed_value,
            evidence=evidence,
            status=PENDING,
            created_at=stamp,
        )
        await self._db.execute(
            f"INSERT INTO fact_proposals ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proposal.id,
                proposal.field,
                proposal.current_value,
                proposal.proposed_value,
                proposal.evidence,
                proposal.status,
                proposal.created_at,
                None,
            ),
        )
        await self._db.commit()
        return proposal

    async def get(self, proposal_id: str) -> FactProposal | None:
        cur = await self._db.execute(
            f"SELECT {_COLUMNS} FROM fact_proposals WHERE id = ?", (proposal_id,)
        )
        row = await cur.fetchone()
        await cur.close()
        return _row(row) if row else None

    async def list_pending(self) -> list[FactProposal]:
        cur = await self._db.execute(
            f"SELECT {_COLUMNS} FROM fact_proposals WHERE status = ? "
            "ORDER BY created_at ASC",
            (PENDING,),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [_row(r) for r in rows]

    async def decide(
        self, proposal_id: str, status: str, *, now: str | None = None
    ) -> FactProposal | None:
        """Accept or reject a pending proposal. Returns it, or None if not pending."""
        if status not in (ACCEPTED, REJECTED):
            raise ValueError(f"Unsupported decision: {status}")
        proposal = await self.get(proposal_id)
        if proposal is None or proposal.status != PENDING:
            return None
        stamp = now or datetime.now(UTC).isoformat()
        await self._db.execute(
            "UPDATE fact_proposals SET status = ?, decided_at = ? WHERE id = ?",
            (status, stamp, proposal_id),
        )
        await self._db.commit()
        proposal.status = status
        proposal.decided_at = stamp
        return proposal
