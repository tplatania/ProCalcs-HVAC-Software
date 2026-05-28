"""add contractor_overrides table for Day-13 inline-edit corrections

Revision ID: e9b7c1a3f8d2
Revises: d2c1a8f4e7b0
Create Date: 2026-05-28 09:00:00.000000

Per-contractor manual corrections (SKU, supplier, unit price) on
top of Wrightsoft-emitted lines. Consulted by the builder BEFORE
discovered_mappings, so manual edits always beat auto-discovered
ones, which in turn beat raw passthrough.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e9b7c1a3f8d2'
down_revision = 'd2c1a8f4e7b0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'contractor_overrides',
        sa.Column('id',                 sa.Integer(), nullable=False),
        sa.Column('contractor_id',      sa.String(length=64),  nullable=False),
        sa.Column('supplier',           sa.String(length=16),  nullable=False),
        sa.Column('sku',                sa.String(length=128), nullable=False),
        sa.Column('corrected_sku',      sa.String(length=128), nullable=True),
        sa.Column('corrected_supplier', sa.String(length=16),  nullable=True),
        sa.Column('unit_price',         sa.Float(),            nullable=True),
        sa.Column('notes',              sa.String(length=512), nullable=True),
        sa.Column('created_at',         sa.DateTime(),         nullable=False),
        sa.Column('updated_at',         sa.DateTime(),         nullable=False),
        sa.Column('updated_by',         sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'contractor_id', 'supplier', 'sku',
            name='uq_contractor_override_key',
        ),
    )
    with op.batch_alter_table('contractor_overrides', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contractor_overrides_contractor_id'),
                              ['contractor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_contractor_overrides_supplier'),
                              ['supplier'], unique=False)
        batch_op.create_index(batch_op.f('ix_contractor_overrides_sku'),
                              ['sku'], unique=False)
        batch_op.create_index(batch_op.f('ix_contractor_overrides_updated_at'),
                              ['updated_at'], unique=False)


def downgrade():
    with op.batch_alter_table('contractor_overrides', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contractor_overrides_updated_at'))
        batch_op.drop_index(batch_op.f('ix_contractor_overrides_sku'))
        batch_op.drop_index(batch_op.f('ix_contractor_overrides_supplier'))
        batch_op.drop_index(batch_op.f('ix_contractor_overrides_contractor_id'))
    op.drop_table('contractor_overrides')
