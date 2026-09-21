"""add feedback threads/messages/attachments tables

In-app feedback / ask threads (testers + team), with durable
attachment bytes stored in-row.

Revision ID: e1f4a9c7d2b8
Revises: d5a9f1c2e8b4
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f4a9c7d2b8'
down_revision = 'd5a9f1c2e8b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'feedback_threads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('page_context', sa.String(length=120), nullable=True),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('client_id', sa.String(length=120), nullable=True),
        sa.Column('target', sa.String(length=32), nullable=False),
        sa.Column('created_by_email', sa.String(length=255), nullable=True),
        sa.Column('agent_clarifications_used', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['bom_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_feedback_threads_status', 'feedback_threads', ['status'])
    op.create_index('ix_feedback_threads_run_id', 'feedback_threads', ['run_id'])
    op.create_index('ix_feedback_threads_created_by_email', 'feedback_threads',
                    ['created_by_email'])
    op.create_index('ix_feedback_threads_created_at', 'feedback_threads', ['created_at'])

    op.create_table(
        'feedback_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('author_email', sa.String(length=255), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['thread_id'], ['feedback_threads.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_feedback_messages_thread_id', 'feedback_messages', ['thread_id'])
    op.create_index('ix_feedback_messages_created_at', 'feedback_messages', ['created_at'])

    op.create_table(
        'feedback_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(length=300), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['thread_id'], ['feedback_threads.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['feedback_messages.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_feedback_attachments_thread_id', 'feedback_attachments',
                    ['thread_id'])


def downgrade():
    op.drop_index('ix_feedback_attachments_thread_id', table_name='feedback_attachments')
    op.drop_table('feedback_attachments')
    op.drop_index('ix_feedback_messages_created_at', table_name='feedback_messages')
    op.drop_index('ix_feedback_messages_thread_id', table_name='feedback_messages')
    op.drop_table('feedback_messages')
    op.drop_index('ix_feedback_threads_created_at', table_name='feedback_threads')
    op.drop_index('ix_feedback_threads_created_by_email', table_name='feedback_threads')
    op.drop_index('ix_feedback_threads_run_id', table_name='feedback_threads')
    op.drop_index('ix_feedback_threads_status', table_name='feedback_threads')
    op.drop_table('feedback_threads')
