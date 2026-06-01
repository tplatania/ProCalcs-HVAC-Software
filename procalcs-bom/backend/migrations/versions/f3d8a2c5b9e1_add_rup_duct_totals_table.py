"""add rup_duct_totals table for Day-14 Phase 4 cache

Revision ID: f3d8a2c5b9e1
Revises: e9b7c1a3f8d2
Create Date: 2026-05-30 10:00:00.000000

Caches user-entered Wrightsoft Supply Actual Ln(ft) totals per RUP
SHA-256 hash so re-uploading the same file pre-populates the form.
Team-wide cache — any user who uploads the same RUP sees the totals
the first person entered.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'f3d8a2c5b9e1'
down_revision = 'e9b7c1a3f8d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rup_duct_totals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rup_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'known_lengths_ft',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rup_hash', name='uq_rup_duct_totals_hash'),
    )
    with op.batch_alter_table('rup_duct_totals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rup_duct_totals_rup_hash'),
                              ['rup_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_rup_duct_totals_updated_at'),
                              ['updated_at'], unique=False)


def downgrade():
    with op.batch_alter_table('rup_duct_totals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rup_duct_totals_updated_at'))
        batch_op.drop_index(batch_op.f('ix_rup_duct_totals_rup_hash'))
    op.drop_table('rup_duct_totals')
