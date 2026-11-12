"""
Reverse sync for the user side of the user <-> access group relationship.

`litellm_accessgrouptable.assigned_user_ids` and `litellm_usertable.access_group_ids`
are two copies of the same relationship. The access-group endpoints maintain both
copies already; this module is what the user write paths call so an edit from that
side is mirrored back.

It deliberately lives outside `access_group_endpoints`, which is a lazily
registered feature router (see `_lazy_features.LAZY_FEATURES`). Importing that
module eagerly from `internal_user_endpoints` would put it in `sys.modules`
without its router ever being included, which drops its routes from the OpenAPI
schema.
"""

from collections.abc import Mapping, Sequence
from typing import Final, Protocol

from pydantic import TypeAdapter

from litellm.proxy.db.db_span import db_span
from litellm.proxy.management_helpers.access_group_team_sync import (
    invalidate_access_group_caches,
)
from litellm.types.llms.base import LiteLLMBaseModel
from litellm.types.proxy.management_endpoints.user_requests import UpdateUserRequest

_READ_USER_SQL: Final = 'SELECT access_group_ids FROM "LiteLLM_UserTable" WHERE user_id = $1'

_AFFECTED_SQL: Final = """
SELECT access_group_id FROM "LiteLLM_AccessGroupTable"
WHERE access_group_id = ANY($2::TEXT[])
   OR $1 = ANY(COALESCE(assigned_user_ids, ARRAY[]::TEXT[]))
"""

_ATTACH_SQL: Final = """
UPDATE "LiteLLM_AccessGroupTable"
SET assigned_user_ids = array_append(COALESCE(assigned_user_ids, ARRAY[]::TEXT[]), $1)
WHERE access_group_id = ANY($2::TEXT[])
  AND NOT ($1 = ANY(COALESCE(assigned_user_ids, ARRAY[]::TEXT[])))
RETURNING access_group_id
"""

_DETACH_SQL: Final = """
UPDATE "LiteLLM_AccessGroupTable"
SET assigned_user_ids = array_remove(assigned_user_ids, $1)
WHERE $1 = ANY(COALESCE(assigned_user_ids, ARRAY[]::TEXT[]))
  AND NOT (access_group_id = ANY($2::TEXT[]))
RETURNING access_group_id
"""


class _AffectedGroup(LiteLLMBaseModel):
    access_group_id: str


class _UserGroups(LiteLLMBaseModel):
    access_group_ids: tuple[str, ...] | None = None


_AffectedGroups: Final = TypeAdapter(tuple[_AffectedGroup, ...])
_UserRows: Final = TypeAdapter(tuple[_UserGroups, ...])


class AccessGroupSyncTx(Protocol):
    async def query_raw(self, query: str, *args: object) -> Sequence[Mapping[str, object]]: ...


class _Transaction(Protocol):
    async def __aenter__(self) -> AccessGroupSyncTx: ...

    async def __aexit__(self, *exc_info: object) -> None: ...


class _PrismaDb(Protocol):
    def tx(self) -> _Transaction: ...


class _PrismaClient(Protocol):
    @property
    def db(self) -> _PrismaDb: ...


async def reconcile_user_access_group_membership(tx: AccessGroupSyncTx, user_id: str) -> tuple[str, ...]:
    """
    Reconcile every access group's `assigned_user_ids` against the user's own
    `access_group_ids`, and return the groups whose cache the caller has to drop once the
    transaction commits.

    A user with no row reconciles to an empty set, which detaches them from every group.
    """
    user_rows: Final = _UserRows.validate_python(await tx.query_raw(_READ_USER_SQL, user_id))
    desired: Final = (user_rows[0].access_group_ids or ()) if user_rows else ()
    affected: Final = _AffectedGroups.validate_python(await tx.query_raw(_AFFECTED_SQL, user_id, desired))
    await tx.query_raw(_ATTACH_SQL, user_id, desired)
    await tx.query_raw(_DETACH_SQL, user_id, desired)
    return tuple(group.access_group_id for group in affected)


async def sync_user_access_group_membership(prisma_client: _PrismaClient, user_id: str) -> None:
    """Reconcile the mirror for an already committed user write, in its own transaction."""
    async with db_span("sync_user_access_group_membership", "LiteLLM_AccessGroupTable"), prisma_client.db.tx() as tx:
        affected: Final = await reconcile_user_access_group_membership(tx, user_id)

    await invalidate_access_group_caches(affected)


async def sync_user_update_access_group_membership(
    prisma_client: _PrismaClient,
    user_id: str,
    data: UpdateUserRequest,
) -> None:
    """
    Mirror a user UPDATE onto the group side, honouring `exclude_unset` semantics.

    A request that never mentions `access_group_ids` leaves the user's own list alone and
    must leave the group's copy alone too.
    """
    if "access_group_ids" not in data.model_fields_set:
        return
    await sync_user_access_group_membership(prisma_client=prisma_client, user_id=user_id)
