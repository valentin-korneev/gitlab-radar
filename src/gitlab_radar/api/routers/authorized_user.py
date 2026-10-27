from fastapi import APIRouter, Depends, HTTPException
from tortoise.transactions import in_transaction

from gitlab_radar.auth import management_access_dependency
from gitlab_radar.config import settings
from gitlab_radar.database.models import AuthorizedUser as AuthorizedUserModel
from gitlab_radar.schemas.authorized_user import AuthorizedUser, AuthorizedUserCreate, AuthorizedUserUpdate

router = APIRouter(dependencies=[Depends(management_access_dependency)])


def _environment_admins() -> set[str]:
    admins = set(settings.auth.allowed_preferred_usernames)
    if not settings.auth.required:
        admins.add(settings.auth.development_username)
    return admins


@router.get('/')
async def get_authorized_users() -> list[AuthorizedUser]:
    environment_users = _environment_admins()
    database_users = {user.preferred_username: user for user in await AuthorizedUserModel.all()}
    result = []
    for preferred_username in sorted(environment_users | database_users.keys(), key=str.casefold):
        database_user = database_users.get(preferred_username)
        result.append(
            AuthorizedUser(
                preferred_username=preferred_username,
                source='environment' if preferred_username in environment_users else 'database',
                is_admin=preferred_username in environment_users or bool(database_user and database_user.is_admin),
                is_blocked=bool(database_user and database_user.is_blocked),
            )
        )
    return result


@router.post('/', status_code=201)
async def add_authorized_user(payload: AuthorizedUserCreate) -> AuthorizedUser:
    environment_admin = payload.preferred_username in _environment_admins()
    user, _ = await AuthorizedUserModel.get_or_create(
        preferred_username=payload.preferred_username,
        defaults={'is_admin': environment_admin},
    )
    return AuthorizedUser(
        preferred_username=user.preferred_username,
        source='environment' if environment_admin else 'database',
        is_admin=environment_admin or user.is_admin,
        is_blocked=user.is_blocked,
    )


@router.put('/')
async def update_authorized_user(payload: AuthorizedUserUpdate) -> AuthorizedUser:
    preferred_username = payload.preferred_username
    environment_admins = _environment_admins()
    environment_admin = preferred_username in environment_admins
    if environment_admin and not payload.is_admin:
        raise HTTPException(status_code=409, detail='Роль администратора задана в окружении')
    if not settings.auth.required and preferred_username == settings.auth.development_username and payload.is_blocked:
        raise HTTPException(status_code=409, detail='Локальный тестовый администратор не может быть заблокирован')
    async with in_transaction() as connection:
        await connection.execute_query("SELECT pg_advisory_xact_lock(hashtext('gitlab-radar-authorized-users'))")
        user = await AuthorizedUserModel.filter(preferred_username=preferred_username).using_db(connection).first()
        if user is None:
            if not environment_admin:
                raise HTTPException(status_code=404, detail='Пользователь не найден')
            user = AuthorizedUserModel(preferred_username=preferred_username, is_admin=True)
            await user.save(using_db=connection, force_create=True)
        user.is_admin = payload.is_admin
        user.is_blocked = payload.is_blocked
        await user.save(using_db=connection, update_fields=['is_admin', 'is_blocked'])
        users = await AuthorizedUserModel.all().using_db(connection)
        active_admins = {
            item.preferred_username
            for item in users
            if not item.is_blocked and (item.is_admin or item.preferred_username in environment_admins)
        }
        blocked_users = {item.preferred_username for item in users if item.is_blocked}
        active_admins.update(environment_admins - blocked_users)
        if not active_admins:
            raise HTTPException(status_code=409, detail='Должен остаться хотя бы один активный администратор')
    return AuthorizedUser(
        preferred_username=preferred_username,
        source='environment' if environment_admin else 'database',
        is_admin=environment_admin or user.is_admin,
        is_blocked=user.is_blocked,
    )


@router.delete('/', status_code=204)
async def delete_authorized_user(preferred_username: str) -> None:
    environment_admins = _environment_admins()
    if preferred_username in environment_admins:
        raise HTTPException(status_code=409, detail='Пользователь задан в окружении и не может быть удалён')
    async with in_transaction() as connection:
        await connection.execute_query("SELECT pg_advisory_xact_lock(hashtext('gitlab-radar-authorized-users'))")
        user = await AuthorizedUserModel.filter(preferred_username=preferred_username).using_db(connection).first()
        if user is None:
            raise HTTPException(status_code=404, detail='Пользователь не найден')
        if user.is_admin and not user.is_blocked:
            users = await AuthorizedUserModel.all().using_db(connection)
            blocked_users = {item.preferred_username for item in users if item.is_blocked}
            active_database_admins = {
                item.preferred_username for item in users if item.is_admin and not item.is_blocked
            }
            active_admins = active_database_admins | (environment_admins - blocked_users)
            if active_admins == {preferred_username}:
                raise HTTPException(status_code=409, detail='Должен остаться хотя бы один активный администратор')
        await user.delete(using_db=connection)
