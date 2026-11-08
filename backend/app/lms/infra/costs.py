"""Monthly cost estimate (INFRA_PANEL_DESIGN 4, D-I5-5): static rows mirroring the table in `docs/COSTS.md`.

`service` is the first column of that table, word for word: `tests/lms/test_infra.py` fails when a row here and a row
there stop matching. Change both together. Every "next plan" price is unverified (COSTS.md says so)."""
from __future__ import annotations

from typing import NamedTuple, Optional

SOURCE = "docs/COSTS.md"
AS_OF = "2026-11-09"


class CostRow(NamedTuple):
    key: str  # i18n key under infra.costs.*
    service: str  # first column of docs/COSTS.md
    plan: str
    usd_per_month: Optional[float]  # current plan; None = unknown
    next_plan: Optional[str]
    next_usd_per_month: Optional[float]  # None = usage-based or unknown
    next_unit: Optional[str]  # "month", "seat", "usage"
    verified: bool = False


COST_ROWS: tuple[CostRow, ...] = (
    CostRow("render", "Render (API)", "Free", 0, "Starter", 7, "month"),
    CostRow("neon", "Neon (database)", "Free", 0, "Launch", None, "usage"),
    CostRow("vercel", "Vercel (frontend)", "Hobby", 0, "Pro", 20, "seat"),
    CostRow("r2", "Cloudflare R2", "Free tier", 0, None, None, "usage"),
    CostRow("email", "Resend / Brevo / SMTP (email)", "Free", 0, None, None, None),
    CostRow("github", "GitHub (CI, uptime)", "Free", 0, None, None, None),
    CostRow("sentry", "Sentry", "Off", 0, None, None, None),
)


def summary() -> dict:
    known = [r.usd_per_month for r in COST_ROWS if r.usd_per_month is not None]
    return {
        "total_usd": float(sum(known)),
        "complete": len(known) == len(COST_ROWS),
        "rows": [r._asdict() for r in COST_ROWS],
        "source": SOURCE,
        "as_of": AS_OF,
    }
