"""Declarative base. Every table in the project inherits from this, and
Alembic's autogenerate walks Base.metadata to find them.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
