from typing import Final
from unittest.mock import AsyncMock, MagicMock

import pytest

from litellm.proxy.management_helpers.access_group_user_sync import (
    reconcile_user_access_group_membership,
    sync_user_update_access_group_membership,
)
from litellm.types.proxy.management_endpoints.user_requests import UpdateUserRequest


class _FakeTx:
    def __init__(self, user_rows: list[dict[str, object]], affected: list[dict[str, object]]) -> None:
        self.user_rows: Final = user_rows
        self.affected: Final = affected
        self.queries: list[tuple[object, ...]] = []

    async def query_raw(self, query: str, *args: object) -> list[dict[str, object]]:
        self.queries.append((query, *args))
        if "FROM \"LiteLLM_UserTable\"" in query:
            return self.user_rows
        if "OR $1 = ANY(COALESCE(assigned_user_ids" in query:
            return self.affected
        return []


@pytest.mark.asyncio
async def test_reconcile_attaches_and_detaches_against_user_row() -> None:
    tx = _FakeTx(
        user_rows=[{"access_group_ids": ("ag-keep", "ag-new")}],
        affected=[{"access_group_id": "ag-keep"}, {"access_group_id": "ag-old"}, {"access_group_id": "ag-new"}],
    )

    affected = await reconcile_user_access_group_membership(tx, "user-1")

    assert affected == ("ag-keep", "ag-old", "ag-new")
    assert any("array_append" in query[0] and query[1:] == ("user-1", ("ag-keep", "ag-new")) for query in tx.queries)
    assert any("array_remove" in query[0] and query[1:] == ("user-1", ("ag-keep", "ag-new")) for query in tx.queries)


@pytest.mark.asyncio
async def test_reconcile_missing_user_detaches_every_group() -> None:
    tx = _FakeTx(user_rows=[], affected=[{"access_group_id": "ag-1"}])

    affected = await reconcile_user_access_group_membership(tx, "deleted-user")

    assert affected == ("ag-1",)
    assert any(query[1:] == ("deleted-user", ()) for query in tx.queries if "array_remove" in query[0])


@pytest.mark.asyncio
async def test_sync_user_update_skips_when_access_group_ids_unset(monkeypatch) -> None:
    called = False

    async def _sync(**_kwargs) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "litellm.proxy.management_helpers.access_group_user_sync.sync_user_access_group_membership",
        _sync,
    )

    await sync_user_update_access_group_membership(
        prisma_client=MagicMock(),
        user_id="user-1",
        data=UpdateUserRequest(user_id="user-1", user_email="a@example.com"),
    )

    assert called is False


@pytest.mark.asyncio
async def test_sync_user_update_runs_when_access_group_ids_set(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def _sync(*, prisma_client, user_id: str) -> None:
        seen["user_id"] = user_id
        seen["prisma_client"] = prisma_client

    monkeypatch.setattr(
        "litellm.proxy.management_helpers.access_group_user_sync.sync_user_access_group_membership",
        _sync,
    )
    prisma = MagicMock()

    await sync_user_update_access_group_membership(
        prisma_client=prisma,
        user_id="user-1",
        data=UpdateUserRequest(user_id="user-1", access_group_ids=["ag-1"]),
    )

    assert seen == {"user_id": "user-1", "prisma_client": prisma}
