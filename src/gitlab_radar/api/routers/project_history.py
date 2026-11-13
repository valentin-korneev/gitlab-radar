from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from gitlab_radar.application.project_history import (
    package_changes,
    package_inventory_at,
    package_periods,
    project_observations,
)
from gitlab_radar.auth import optional_authenticated_access_dependency
from gitlab_radar.database.models import ScanItem, ScanTarget
from gitlab_radar.schemas.history import (
    PackageChangeQuery,
    PackageChangesPage,
    PackageInventoryPage,
    PackagePeriodsPage,
    ProjectHistoryPage,
    ProjectHistoryQuery,
    TargetSummary,
)
from gitlab_radar.services.project import load_projects

router = APIRouter()
Claims = Annotated[dict[str, Any], Depends(optional_authenticated_access_dependency)]


async def _authorize(project_id: int, claims: dict[str, Any]) -> None:
    projects = await load_projects(
        claims.get('preferred_username'), claims.get('visibility_group'), project_ids=[project_id]
    )
    if not projects:
        raise HTTPException(status_code=404, detail='Проект не найден')


async def _target(project_id: int, target_id: int | None) -> ScanTarget:
    query = ScanTarget.filter(gitlab_id=project_id)
    query = query.filter(id=target_id) if target_id is not None else query.filter(is_default=True)
    target = await query.first()
    if target is None:
        raise HTTPException(status_code=404, detail='Цель сканирования не найдена')
    return target


@router.get('/{project_id}/history/targets', response_model=list[TargetSummary])
async def targets(project_id: int, claims: Claims, response: Response) -> list[TargetSummary]:
    response.headers['Cache-Control'] = 'no-store'
    await _authorize(project_id, claims)
    rows = await ScanTarget.filter(gitlab_id=project_id).order_by('-is_default', 'id')
    return [TargetSummary.model_validate(row, from_attributes=True) for row in rows]


@router.get('/{project_id}/history', response_model=ProjectHistoryPage)
async def history(
    project_id: int,
    claims: Claims,
    response: Response,
    filters: Annotated[ProjectHistoryQuery, Query()],
) -> ProjectHistoryPage:
    response.headers['Cache-Control'] = 'no-store'
    await _authorize(project_id, claims)
    return await project_observations(await _target(project_id, filters.target_id), filters)


@router.get('/{project_id}/history/{scan_id}/changes', response_model=PackageChangesPage)
async def changes(
    project_id: int,
    scan_id: int,
    claims: Claims,
    response: Response,
    filters: Annotated[PackageChangeQuery, Query()],
) -> PackageChangesPage:
    response.headers['Cache-Control'] = 'no-store'
    await _authorize(project_id, claims)
    target = await _target(project_id, filters.target_id)
    item = await ScanItem.filter(scan_id=scan_id, target_id=target.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail='Наблюдение проекта не найдено')
    return await package_changes(item, filters)


@router.get('/{project_id}/package-history/{package_key}', response_model=PackagePeriodsPage)
async def periods(
    project_id: int,
    claims: Claims,
    response: Response,
    filters: Annotated[ProjectHistoryQuery, Query()],
    package_key: Annotated[str, Path(pattern=r'^[0-9a-f]{64}$')],
) -> PackagePeriodsPage:
    response.headers['Cache-Control'] = 'no-store'
    await _authorize(project_id, claims)
    target = await _target(project_id, filters.target_id)
    return await package_periods(target.id, package_key, filters)


@router.get('/{project_id}/history/{scan_id}/packages', response_model=PackageInventoryPage)
async def packages(
    project_id: int,
    scan_id: int,
    claims: Claims,
    response: Response,
    filters: Annotated[PackageChangeQuery, Query()],
) -> PackageInventoryPage:
    response.headers['Cache-Control'] = 'no-store'
    await _authorize(project_id, claims)
    target = await _target(project_id, filters.target_id)
    if not await ScanItem.filter(scan_id=scan_id, target_id=target.id).exists():
        raise HTTPException(status_code=404, detail='Наблюдение проекта не найдено')
    return await package_inventory_at(target.id, scan_id, filters)
