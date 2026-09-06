"""Tables.

Phase 2 adds the three that OAuth needs. Phase 1 will add `messages`, phase 6
`facts` / `episodes`, phase 7 `orders`. LangGraph's checkpointer manages its
own tables and is not modelled here.

Import every model in this module so `Base.metadata` is complete for Alembic.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from potluck.db.base import Base


class SwiggyOAuthClient(Base):
    """The result of RFC 7591 dynamic client registration.

    Swiggy does not hand out a client_id in a dashboard — you register a client
    at runtime and it gives you one. Registration is tied to the exact redirect
    URI, so local and deployed each get their own row.
    """

    __tablename__ = "swiggy_oauth_clients"
    __table_args__ = (UniqueConstraint("issuer", "redirect_uri", name="uq_client_issuer_redirect"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issuer: Mapped[str] = mapped_column(String(255))
    redirect_uri: Mapped[str] = mapped_column(String(500))
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SwiggyAuthRequest(Base):
    """One in-flight authorization.

    Holds the PKCE verifier between the redirect out and the callback back. In
    the database rather than in memory because the two halves of the flow may
    be served by different workers, or by a container that restarted in between.
    """

    __tablename__ = "swiggy_auth_requests"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_key: Mapped[str] = mapped_column(String(128))
    code_verifier_enc: Mapped[str] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class SwiggyToken(Base):
    """One household member's Swiggy access token.

    `account_key` is who this token belongs to. For now there is one, "default";
    once the group has members it becomes the Telegram user id of whoever's
    Swiggy account pays.

    There is no refresh token — Swiggy does not issue them in v1. When the
    5-day token expires the only cure is sending the human back through the
    browser, which is what `needs_reauth` exists to signal.
    """

    __tablename__ = "swiggy_tokens"

    account_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    access_token_enc: Mapped[str] = mapped_column(Text)
    token_type: Mapped[str] = mapped_column(String(32), default="Bearer")
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    obtained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    needs_reauth: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["Base", "SwiggyAuthRequest", "SwiggyOAuthClient", "SwiggyToken"]
