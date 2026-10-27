from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from gitlab_radar.auth import authenticated_access_dependency, management_access_dependency
from gitlab_radar.config import settings
from gitlab_radar.database.models import (
    AdminUserVisibilityRule,
    AdminVisibilityPolicy,
    AdminVisibilityPolicyAssignment,
    AdminVisibilityPolicyRule,
    AuthorizedUser,
    UserVisibilityGroup,
    UserVisibilityRule,
)
from gitlab_radar.schemas.visibility import (
    AdminUserVisibility,
    AdminUserVisibilityPayload,
    AdminVisibilityPolicyPayload,
    DefaultVisibilityGroupUpdate,
    UserVisibilityGroupPayload,
    VisibilityRule,
)
from gitlab_radar.schemas.visibility import (
    AdminVisibilityPolicy as AdminVisibilityPolicySchema,
)
from gitlab_radar.schemas.visibility import (
    UserVisibilityGroup as UserVisibilityGroupSchema,
)
from gitlab_radar.services.visibility import (
    replace_admin_user_visibility,
    replace_policy_rules,
    replace_user_group_rules,
)

router = APIRouter()


def _username(claims: dict[str, Any]) -> str:
    preferred_username = claims.get('preferred_username')
    if not isinstance(preferred_username, str) or not preferred_username:
        raise HTTPException(status_code=409, detail='Фильтры доступны только пользователям Keycloak')
    return preferred_username


async def _user_group_schema(group: UserVisibilityGroup) -> UserVisibilityGroupSchema:
    rules = await UserVisibilityRule.filter(group_id=group.id).order_by('sort_order', 'id')
    return UserVisibilityGroupSchema(
        id=group.id,
        name=group.name,
        is_default=group.is_active,
        rules=[VisibilityRule(id=rule.id, action=rule.action, pattern=rule.pattern) for rule in rules],
    )


async def _policy_schema(policy: AdminVisibilityPolicy) -> AdminVisibilityPolicySchema:
    rules = await AdminVisibilityPolicyRule.filter(policy_id=policy.id).order_by('sort_order', 'id')
    return AdminVisibilityPolicySchema(
        id=policy.id,
        name=policy.name,
        rules=[VisibilityRule(id=rule.id, action=rule.action, pattern=rule.pattern) for rule in rules],
    )


async def _ensure_admin_target(preferred_username: str) -> bool:
    if await AuthorizedUser.filter(preferred_username=preferred_username).exists():
        return True
    if preferred_username not in settings.auth.allowed_preferred_usernames:
        return False
    await AuthorizedUser.create(preferred_username=preferred_username, is_admin=True)
    return True


@router.get('/')
async def get_visibility_groups(
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> list[UserVisibilityGroupSchema]:
    username = _username(claims)
    groups = await UserVisibilityGroup.filter(user_id=username).order_by('sort_order', 'id')
    return [await _user_group_schema(group) for group in groups]


@router.post('/', status_code=201)
async def create_visibility_group(
    payload: UserVisibilityGroupPayload,
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> UserVisibilityGroupSchema:
    username = _username(claims)
    try:
        async with in_transaction() as connection:
            group = await UserVisibilityGroup.create(
                user_id=username,
                name=payload.name,
                sort_order=await UserVisibilityGroup.filter(user_id=username).using_db(connection).count(),
                using_db=connection,
            )
            await replace_user_group_rules(group.id, payload.rules, connection)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Группа с таким названием уже существует') from error
    return await _user_group_schema(group)


@router.put('/default')
async def set_default_visibility_group(
    payload: DefaultVisibilityGroupUpdate,
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> dict[str, int | None]:
    username = _username(claims)
    if (
        payload.group_id is not None
        and not await UserVisibilityGroup.filter(id=payload.group_id, user_id=username).exists()
    ):
        raise HTTPException(status_code=404, detail='Группа фильтров не найдена')
    async with in_transaction() as connection:
        await connection.execute_query(
            "SELECT pg_advisory_xact_lock(hashtext('gitlab-radar-visibility-' || $1))",
            [username],
        )
        await UserVisibilityGroup.filter(user_id=username, is_active=True).using_db(connection).update(is_active=False)
        if payload.group_id is not None:
            await (
                UserVisibilityGroup.filter(id=payload.group_id, user_id=username)
                .using_db(connection)
                .update(is_active=True)
            )
    return {'group_id': payload.group_id}


@router.put('/{group_id}')
async def update_visibility_group(
    group_id: int,
    payload: UserVisibilityGroupPayload,
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> UserVisibilityGroupSchema:
    username = _username(claims)
    group = await UserVisibilityGroup.filter(id=group_id, user_id=username).first()
    if group is None:
        raise HTTPException(status_code=404, detail='Группа фильтров не найдена')
    try:
        async with in_transaction() as connection:
            group.name = payload.name
            await group.save(using_db=connection, update_fields=['name'])
            await replace_user_group_rules(group.id, payload.rules, connection)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Группа с таким названием уже существует') from error
    return await _user_group_schema(group)


@router.delete('/{group_id}', status_code=204)
async def delete_visibility_group(
    group_id: int,
    claims: Annotated[dict[str, Any], Depends(authenticated_access_dependency)],
) -> None:
    username = _username(claims)
    deleted = await UserVisibilityGroup.filter(id=group_id, user_id=username).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail='Группа фильтров не найдена')


admin_router = APIRouter(dependencies=[Depends(management_access_dependency)])


@admin_router.get('/policy')
async def get_visibility_policies() -> list[AdminVisibilityPolicySchema]:
    policies = await AdminVisibilityPolicy.all().order_by('name')
    return [await _policy_schema(policy) for policy in policies]


@admin_router.post('/policy', status_code=201)
async def create_visibility_policy(payload: AdminVisibilityPolicyPayload) -> AdminVisibilityPolicySchema:
    try:
        async with in_transaction() as connection:
            policy = await AdminVisibilityPolicy.create(
                name=payload.name,
                using_db=connection,
            )
            await replace_policy_rules(policy.id, payload.rules, connection)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Политика с таким названием уже существует') from error
    return await _policy_schema(policy)


@admin_router.put('/policy/{policy_id}')
async def update_visibility_policy(
    policy_id: int,
    payload: AdminVisibilityPolicyPayload,
) -> AdminVisibilityPolicySchema:
    policy = await AdminVisibilityPolicy.filter(id=policy_id).first()
    if policy is None:
        raise HTTPException(status_code=404, detail='Политика не найдена')
    try:
        async with in_transaction() as connection:
            policy.name = payload.name
            await policy.save(using_db=connection, update_fields=['name'])
            await replace_policy_rules(policy.id, payload.rules, connection)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Политика с таким названием уже существует') from error
    return await _policy_schema(policy)


@admin_router.delete('/policy/{policy_id}', status_code=204)
async def delete_visibility_policy(policy_id: int) -> None:
    deleted = await AdminVisibilityPolicy.filter(id=policy_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail='Политика не найдена')


@admin_router.get('/user/{preferred_username}')
async def get_admin_user_visibility(preferred_username: str) -> AdminUserVisibility:
    if not await _ensure_admin_target(preferred_username):
        raise HTTPException(status_code=404, detail='Пользователь не найден')
    policy_ids = await AdminVisibilityPolicyAssignment.filter(user_id=preferred_username).values_list(
        'policy_id', flat=True
    )
    rules = await AdminUserVisibilityRule.filter(user_id=preferred_username).order_by('sort_order', 'id')
    return AdminUserVisibility(
        preferred_username=preferred_username,
        policy_ids=list(policy_ids),
        rules=[VisibilityRule(id=rule.id, action=rule.action, pattern=rule.pattern) for rule in rules],
    )


@admin_router.put('/user/{preferred_username}')
async def update_admin_user_visibility(
    preferred_username: str,
    payload: AdminUserVisibilityPayload,
) -> AdminUserVisibility:
    if not await _ensure_admin_target(preferred_username):
        raise HTTPException(status_code=404, detail='Пользователь не найден')
    existing_policy_ids = set(
        await AdminVisibilityPolicy.filter(id__in=payload.policy_ids).values_list('id', flat=True)
    )
    if existing_policy_ids != set(payload.policy_ids):
        raise HTTPException(status_code=400, detail='Указана несуществующая политика')
    await replace_admin_user_visibility(preferred_username, payload.policy_ids, payload.rules)
    return await get_admin_user_visibility(preferred_username)
