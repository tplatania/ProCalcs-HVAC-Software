"""add usage_events table for adoption + learning-loop telemetry

Revision ID: a7e2c9d4b1f6
Revises: f3d8a2c5b9e1
Create Date: 2026-07-18 10:00:00.000000

One row per meaningful interaction (bom_generated, chat_message,
attachment_uploaded, override_saved, proposal_applied). provenance
column separates real contractor-team input from test-actor input
(Gerald/dev) so adoption and impact metrics stay honest.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7e2c9d4b1f6'
down_revision = 'f3d8a2c5b9e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'usage_events',
        sa.Column('id',          sa.Integer(),           nullable=False),
        sa.Column('created_at',  sa.DateTime(),          nullable=False),
        sa.Column('event',       sa.String(length=40),   nullable=False),
        sa.Column('actor_email', sa.String(length=255),  nullable=True),
        sa.Column('provenance',  sa.String(length=8),    nullable=False),
        sa.Column('client_id',   sa.String(length=100),  nullable=True),
        sa.Column('job_id',      sa.String(length=255),  nullable=True),
        sa.Column('run_id',      sa.Integer(),           nullable=True),
        sa.Column('detail',      sa.JSON(),              nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_usage_events_created_at',  'usage_events', ['created_at'])
    op.create_index('ix_usage_events_event',       'usage_events', ['event'])
    op.create_index('ix_usage_events_actor_email', 'usage_events', ['actor_email'])
    op.create_index('ix_usage_events_provenance',  'usage_events', ['provenance'])
    op.create_index('ix_usage_events_client_id',   'usage_events', ['client_id'])
    op.create_index('ix_usage_events_run_id',      'usage_events', ['run_id'])


def downgrade():
    op.drop_index('ix_usage_events_run_id',      table_name='usage_events')
    op.drop_index('ix_usage_events_client_id',   table_name='usage_events')
    op.drop_index('ix_usage_events_provenance',  table_name='usage_events')
    op.drop_index('ix_usage_events_actor_email', table_name='usage_events')
    op.drop_index('ix_usage_events_event',       table_name='usage_events')
    op.drop_index('ix_usage_events_created_at',  table_name='usage_events')
    op.drop_table('usage_events')
