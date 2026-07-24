"""add chat_messages table — persistent BOM Review Assistant conversations

Revision ID: d5a9f1c2e8b4
Revises: c4f8b2a7e3d9
Create Date: 2026-07-24 16:00:00.000000

One row per chat turn keyed to a bom_run, so Richard can resume a
review conversation later and Gerald can read it. Cascade-deletes with
the run. Attachments stored as metadata only (no raw bytes).
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5a9f1c2e8b4'
down_revision = 'c4f8b2a7e3d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'chat_messages',
        sa.Column('id',           sa.Integer(),          nullable=False),
        sa.Column('run_id',       sa.Integer(),          nullable=False),
        sa.Column('created_at',   sa.DateTime(),         nullable=False),
        sa.Column('role',         sa.String(length=16),  nullable=False),
        sa.Column('content',      sa.Text(),             nullable=True),
        sa.Column('actions',      sa.JSON(),             nullable=True),
        sa.Column('attachments',  sa.JSON(),             nullable=True),
        sa.Column('author_email', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['bom_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_messages_run_id',     'chat_messages', ['run_id'])
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])


def downgrade():
    op.drop_index('ix_chat_messages_created_at', table_name='chat_messages')
    op.drop_index('ix_chat_messages_run_id',     table_name='chat_messages')
    op.drop_table('chat_messages')
