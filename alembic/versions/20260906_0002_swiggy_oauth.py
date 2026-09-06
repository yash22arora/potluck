"""swiggy oauth tables

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "swiggy_oauth_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_enc", sa.Text(), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "redirect_uri", name="uq_client_issuer_redirect"),
    )

    op.create_table(
        "swiggy_auth_requests",
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("account_key", sa.String(length=128), nullable=False),
        sa.Column("code_verifier_enc", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("state"),
    )

    op.create_table(
        "swiggy_tokens",
        sa.Column("account_key", sa.String(length=128), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False, server_default="Bearer"),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column(
            "obtained_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("needs_reauth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("account_key"),
    )


def downgrade() -> None:
    op.drop_table("swiggy_tokens")
    op.drop_table("swiggy_auth_requests")
    op.drop_table("swiggy_oauth_clients")
