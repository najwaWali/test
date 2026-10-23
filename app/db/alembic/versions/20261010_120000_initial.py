"""initial schema: tickets + classification_attempts

Revision ID: 20261010_120000
Revises:
Create Date: 2026-10-10 12:00:00 UTC

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261010_120000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=True),
        sa.Column("priority", sa.String(length=8), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_tickets_source_id"),
    )
    op.create_index("idx_tickets_category_priority", "tickets", ["category", "priority"])
    op.create_index("idx_tickets_status", "tickets", ["status"])

    op.create_table(
        "classification_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("parsed_category", sa.String(length=16), nullable=True),
        sa.Column("parsed_priority", sa.String(length=8), nullable=True),
        sa.Column("parsed_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "ticket_id", "attempt_number", name="uq_attempts_ticket_attempt_number"
        ),
    )
    op.create_index(
        "idx_attempts_ticket_created",
        "classification_attempts",
        ["ticket_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_attempts_ticket_created", table_name="classification_attempts")
    op.drop_table("classification_attempts")
    op.drop_index("idx_tickets_status", table_name="tickets")
    op.drop_index("idx_tickets_category_priority", table_name="tickets")
    op.drop_table("tickets")
