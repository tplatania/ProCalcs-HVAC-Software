"""add patch_ops column to bom_runs — run-scoped surgical corrections

Revision ID: c4f8b2a7e3d9
Revises: a7e2c9d4b1f6
Create Date: 2026-07-18 14:00:00.000000

Day-25 (chat corrections). A patch op is a correction that fixes THIS
run's BOM only — quantity edits, line removals, additions raised in
the review chat. Deliberately separate from contractor_overrides:
overrides carry price/SKU and become standing rules; patches don't
(Tom's "we use what Wrightsoft produced" stance on quantities).
Rule-level corrections flow to the question ledger via rule_candidate
usage events instead of silently becoming rules.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f8b2a7e3d9'
down_revision = 'a7e2c9d4b1f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bom_runs', sa.Column('patch_ops', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('bom_runs', 'patch_ops')
