"""TEMP placeholder for slice S4 testing only; the real 0006_phase5_cutover comes from slice S1.

Revision ID: 0006_phase5_cutover
Revises: 0005_phase4_grading
Create Date: 2026-10-23
"""
from typing import Sequence, Union

revision: str = "0006_phase5_cutover"
down_revision: Union[str, None] = "0005_phase4_grading"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
