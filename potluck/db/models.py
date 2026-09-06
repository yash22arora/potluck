"""Tables.

Empty on purpose. Phase 1 adds `messages`, phase 4 adds nothing (LangGraph's
checkpointer manages its own tables), phase 6 adds `facts` / `episodes`, and
phase 7 adds `orders`.

Import every model here so `Base.metadata` is complete when Alembic looks at it.
"""

from potluck.db.base import Base

__all__ = ["Base"]
