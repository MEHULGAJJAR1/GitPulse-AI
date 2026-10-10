"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.engine import Connection

from app.db import get_engine
from app.security import Principal, get_principal, require_role

OWNER_RE = r"^[A-Za-z0-9_.-]{1,39}$"
REPO_RE = r"^[A-Za-z0-9_.-]{1,100}$"


def get_conn() -> Iterator[Connection]:
    with get_engine().connect() as conn:
        yield conn


Conn = Annotated[Connection, Depends(get_conn)]
Viewer = Annotated[Principal, Depends(require_role("viewer"))]
Analyst = Annotated[Principal, Depends(require_role("analyst"))]
Admin = Annotated[Principal, Depends(require_role("admin"))]
AnyPrincipal = Annotated[Principal, Depends(get_principal)]
OwnerPath = Annotated[str, Path(pattern=OWNER_RE)]
NamePath = Annotated[str, Path(pattern=REPO_RE)]


def full_name(owner: str, name: str) -> str:
    return f"{owner}/{name}"
