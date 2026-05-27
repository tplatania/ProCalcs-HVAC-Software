"""add discovered_mappings table for Day-12 auto-learn

Revision ID: d2c1a8f4e7b0
Revises: b21d4f0c8a13
Create Date: 2026-05-27 22:30:00.000000

Every (supplier, sku) combo we see in a Wrightsoft BOM upload gets
upserted into this table. On the next run that hits the same SKU,
the builder upgrades the line from 'wrightsoft_passthrough' to
'wrightsoft_discovered' so the SPA tags it as catalog-resolved.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd2c1a8f4e7b0'
down_revision = 'b21d4f0c8a13'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'discovered_mappings',
        sa.Column('id',                 sa.Integer(), nullable=False),
        sa.Column('supplier',           sa.String(length=16),  nullable=False),
        sa.Column('sku',                sa.String(length=128), nullable=False),
        sa.Column('description',        sa.String(length=512), nullable=True),
        sa.Column('section_hint',       sa.String(length=64),  nullable=True),
        sa.Column('times_seen',         sa.Integer(), nullable=False, server_default='1'),
        sa.Column('total_quantity',     sa.Float(),   nullable=False, server_default='0'),
        sa.Column('first_seen_at',      sa.DateTime(), nullable=False),
        sa.Column('last_seen_at',       sa.DateTime(), nullable=False),
        sa.Column('first_seen_run_id',  sa.Integer(), nullable=True),
        sa.Column('last_seen_run_id',   sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier', 'sku', name='uq_discovered_supplier_sku'),
    )
    with op.batch_alter_table('discovered_mappings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_discovered_mappings_supplier'),
                              ['supplier'], unique=False)
        batch_op.create_index(batch_op.f('ix_discovered_mappings_sku'),
                              ['sku'], unique=False)
        batch_op.create_index(batch_op.f('ix_discovered_mappings_last_seen_at'),
                              ['last_seen_at'], unique=False)


def downgrade():
    with op.batch_alter_table('discovered_mappings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_discovered_mappings_last_seen_at'))
        batch_op.drop_index(batch_op.f('ix_discovered_mappings_sku'))
        batch_op.drop_index(batch_op.f('ix_discovered_mappings_supplier'))
    op.drop_table('discovered_mappings')
