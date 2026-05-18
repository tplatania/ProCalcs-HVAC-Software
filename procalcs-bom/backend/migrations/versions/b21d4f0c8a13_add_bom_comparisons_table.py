"""add bom_comparisons table for Phase 7 audit + Day-2 backlog aggregation

Revision ID: b21d4f0c8a13
Revises: 3661371ab0be
Create Date: 2026-05-18 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b21d4f0c8a13'
down_revision = '3661371ab0be'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bom_comparisons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_email', sa.String(length=255), nullable=True),
        sa.Column('bom_run_id', sa.Integer(), nullable=False),
        sa.Column('sample_filename', sa.String(length=255), nullable=True),
        sa.Column(
            'metrics',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column(
            'missing_skus',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['bom_run_id'], ['bom_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('bom_comparisons', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bom_comparisons_created_at'),
                              ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_bom_comparisons_created_by_email'),
                              ['created_by_email'], unique=False)
        batch_op.create_index(batch_op.f('ix_bom_comparisons_bom_run_id'),
                              ['bom_run_id'], unique=False)


def downgrade():
    with op.batch_alter_table('bom_comparisons', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bom_comparisons_bom_run_id'))
        batch_op.drop_index(batch_op.f('ix_bom_comparisons_created_by_email'))
        batch_op.drop_index(batch_op.f('ix_bom_comparisons_created_at'))
    op.drop_table('bom_comparisons')
