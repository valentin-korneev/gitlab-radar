from fastapi import APIRouter, Depends, HTTPException, Response, status
from tortoise.exceptions import IntegrityError

from gitlab_radar.auth import management_access_dependency
from gitlab_radar.database.models import CompanyRequirement as CompanyRequirementModel
from gitlab_radar.database.models import CompanyRequirementGroup
from gitlab_radar.database.repository import invalidate_project_cache
from gitlab_radar.schemas.company_requirement import (
    CompanyRequirement,
    CompanyRequirementCreate,
    CompanyRequirementEnabled,
    CompanyRequirementMove,
    CompanyRequirementOrder,
    CompanyRequirementUpdate,
    RequirementCatalog,
    RequirementOption,
)
from gitlab_radar.services.application_parameters import application_parameter_values
from gitlab_radar.services.company_rules import (
    load_company_requirements,
    serialize_company_requirement,
)
from gitlab_radar.services.dashboard import invalidate_dashboard_cache

router = APIRouter()
MAX_REQUIREMENTS_PER_GROUP = 4

SOURCE_TITLES = {
    'package_manager': 'Пакетный менеджер',
    'python_version': 'Версия Python',
    'dependency': 'Зависимость',
    'tool': 'Настроенный инструмент',
    'dependency_and_tool': 'Зависимость и настроенный инструмент',
    'ci_component': 'Компонент GitLab CI',
    'webhook': 'Webhook URL',
    'package_registry': 'Registry Python-пакетов',
    'container_registry': 'Registry контейнеров',
}
OPERATOR_TITLES = {
    'equals': 'Равно одному из значений',
    'greater_than_or_equal': 'Не ниже указанной версии',
    'not_equals': 'Не равно указанным значениям',
    'contains': 'Содержит одно из значений',
    'not_contains': 'Не содержит указанные значения',
    'all_contain_any': 'Каждый элемент содержит разрешенное значение',
}


@router.get('/')
async def get_requirements() -> list[CompanyRequirement]:
    return await load_company_requirements(enabled=None)


@router.get('/catalog', dependencies=[Depends(management_access_dependency)])
async def get_requirement_catalog() -> RequirementCatalog:
    parameters = await application_parameter_values()
    python_version = parameters.get('python_oldest_current_version')
    return RequirementCatalog(
        sources=[
            RequirementOption(
                value=value,
                title=title,
                default_operator='greater_than_or_equal' if value == 'python_version' else None,
                default_values=[python_version] if value == 'python_version' and python_version else [],
            )
            for value, title in SOURCE_TITLES.items()
        ],
        operators=[RequirementOption(value=value, title=title) for value, title in OPERATOR_TITLES.items()],
    )


@router.post('/', status_code=status.HTTP_201_CREATED, dependencies=[Depends(management_access_dependency)])
async def create_requirement(payload: CompanyRequirementCreate) -> CompanyRequirement:
    await _ensure_group_exists(payload.group_id)
    await _ensure_group_has_space(payload.group_id)
    try:
        row = await CompanyRequirementModel.create(**payload.model_dump(mode='json'))
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Требование с таким кодом уже существует') from error
    _invalidate_requirement_caches()
    return _serialize(row)


@router.put('/order', dependencies=[Depends(management_access_dependency)])
async def reorder_requirements(payload: CompanyRequirementOrder) -> list[CompanyRequirement]:
    existing_ids = set(
        await CompanyRequirementModel.filter(group_id=payload.group_id).values_list('id', flat=True),
    )
    if len(payload.requirement_ids) != len(existing_ids) or set(payload.requirement_ids) != existing_ids:
        raise HTTPException(status_code=422, detail='Передан неполный список требований группы')
    for position, requirement_id in enumerate(payload.requirement_ids, start=1):
        await CompanyRequirementModel.filter(id=requirement_id).update(sort_order=position * 10)
    _invalidate_requirement_caches()
    return await load_company_requirements(enabled=None)


@router.put('/{requirement_id}', dependencies=[Depends(management_access_dependency)])
async def update_requirement(requirement_id: int, payload: CompanyRequirementUpdate) -> CompanyRequirement:
    row = await CompanyRequirementModel.get_or_none(id=requirement_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Требование не найдено')
    await _ensure_group_exists(payload.group_id)
    if row.group_id != payload.group_id:
        await _ensure_group_has_space(payload.group_id)
    for field, value in payload.model_dump(mode='json').items():
        setattr(row, field, value)
    try:
        await row.save()
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Требование с таким кодом уже существует') from error
    _invalidate_requirement_caches()
    return _serialize(row)


@router.patch('/{requirement_id}/enabled', dependencies=[Depends(management_access_dependency)])
async def set_requirement_enabled(
    requirement_id: int,
    payload: CompanyRequirementEnabled,
) -> CompanyRequirement:
    row = await CompanyRequirementModel.get_or_none(id=requirement_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Требование не найдено')
    row.enabled = payload.enabled
    await row.save(update_fields=['enabled'])
    _invalidate_requirement_caches()
    return _serialize(row)


@router.patch('/{requirement_id}/group', dependencies=[Depends(management_access_dependency)])
async def move_requirement(requirement_id: int, payload: CompanyRequirementMove) -> CompanyRequirement:
    row = await CompanyRequirementModel.get_or_none(id=requirement_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Требование не найдено')
    await _ensure_group_exists(payload.group_id)
    if row.group_id != payload.group_id:
        await _ensure_group_has_space(payload.group_id)
        row.group_id = payload.group_id
        row.sort_order = await CompanyRequirementModel.filter(group_id=payload.group_id).count() * 10 + 10
        await row.save(update_fields=['group_id', 'sort_order'])
        _invalidate_requirement_caches()
    return _serialize(row)


@router.delete(
    '/{requirement_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(management_access_dependency)],
)
async def delete_requirement(requirement_id: int) -> Response:
    deleted = await CompanyRequirementModel.filter(id=requirement_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail='Требование не найдено')
    _invalidate_requirement_caches()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _serialize(row: CompanyRequirementModel) -> CompanyRequirement:
    return serialize_company_requirement(row)


def _invalidate_requirement_caches() -> None:
    invalidate_project_cache()
    invalidate_dashboard_cache()


async def _ensure_group_exists(group_id: int) -> None:
    if not await CompanyRequirementGroup.filter(id=group_id).exists():
        raise HTTPException(status_code=422, detail='Выбранная группа не существует')


async def _ensure_group_has_space(group_id: int) -> None:
    if await CompanyRequirementModel.filter(group_id=group_id).count() >= MAX_REQUIREMENTS_PER_GROUP:
        raise HTTPException(
            status_code=409,
            detail=f'В группе может быть не больше {MAX_REQUIREMENTS_PER_GROUP} требований',
        )
