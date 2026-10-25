from fastapi import APIRouter, HTTPException, Response, status
from tortoise.exceptions import IntegrityError

from gitlab_radar.database.models import (
    CompanyRequirement,
    CompanyRequirementGroup as CompanyRequirementGroupModel,
)
from gitlab_radar.database.repository import invalidate_project_cache
from gitlab_radar.schemas.company_requirement import (
    CompanyRequirementGroup,
    CompanyRequirementGroupCreate,
    CompanyRequirementGroupOrder,
    CompanyRequirementGroupUpdate,
)
from gitlab_radar.services.dashboard import invalidate_dashboard_cache

router = APIRouter()


@router.get('/')
async def get_groups() -> list[CompanyRequirementGroup]:
    rows = await CompanyRequirementGroupModel.all().order_by('sort_order', 'id')
    return [_serialize(row) for row in rows]


@router.post('/', status_code=status.HTTP_201_CREATED)
async def create_group(payload: CompanyRequirementGroupCreate) -> CompanyRequirementGroup:
    try:
        row = await CompanyRequirementGroupModel.create(**payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Группа с таким названием уже существует') from error
    _invalidate_caches()
    return _serialize(row)


@router.put('/order')
async def reorder_groups(payload: CompanyRequirementGroupOrder) -> list[CompanyRequirementGroup]:
    existing_ids = set(await CompanyRequirementGroupModel.all().values_list('id', flat=True))
    if len(payload.group_ids) != len(existing_ids) or set(payload.group_ids) != existing_ids:
        raise HTTPException(status_code=422, detail='Передан неполный список групп')
    for position, group_id in enumerate(payload.group_ids, start=1):
        await CompanyRequirementGroupModel.filter(id=group_id).update(sort_order=position * 10)
    _invalidate_caches()
    return await get_groups()


@router.put('/{group_id}')
async def update_group(group_id: int, payload: CompanyRequirementGroupUpdate) -> CompanyRequirementGroup:
    row = await CompanyRequirementGroupModel.get_or_none(id=group_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Группа не найдена')
    row.name = payload.name
    row.description = payload.description
    row.sort_order = payload.sort_order
    try:
        await row.save()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Группа с таким названием уже существует') from error
    _invalidate_caches()
    return _serialize(row)


@router.delete('/{group_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: int) -> Response:
    row = await CompanyRequirementGroupModel.get_or_none(id=group_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Группа не найдена')
    if await CompanyRequirement.filter(group_id=group_id).exists():
        raise HTTPException(status_code=409, detail='Сначала перенесите или удалите требования этой группы')
    await row.delete()
    _invalidate_caches()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _serialize(row: CompanyRequirementGroupModel) -> CompanyRequirementGroup:
    return CompanyRequirementGroup(
        id=row.id,
        name=row.name,
        description=row.description,
        sort_order=row.sort_order,
    )


def _invalidate_caches() -> None:
    invalidate_project_cache()
    invalidate_dashboard_cache()
