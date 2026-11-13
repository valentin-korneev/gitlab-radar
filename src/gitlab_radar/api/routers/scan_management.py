from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from tortoise.transactions import in_transaction

from gitlab_radar.application.scan_management import scan_history, scan_item_detail, scan_items, scan_statistics
from gitlab_radar.application.scans import scan_status
from gitlab_radar.auth import management_access_dependency
from gitlab_radar.database.models import ScanItem, ScanRun, ScanSchedule
from gitlab_radar.database.scan_jobs import enqueue_scan
from gitlab_radar.database.scan_schedules import save_schedule, set_enabled
from gitlab_radar.schemas.history import ScanChartPoint
from gitlab_radar.schemas.scan import ScanItemState, ScanState, ScanStatus
from gitlab_radar.schemas.scan_management import (
    ScanHistoryPage,
    ScanHistoryQuery,
    ScanItemDetail,
    ScanItemsPage,
    ScheduleEnabled,
    SchedulePayload,
    ScheduleStatus,
)
from gitlab_radar.schemas.scan_options import ScanOptions

router = APIRouter(dependencies=[Depends(management_access_dependency)])
Claims = Annotated[dict[str, Any], Depends(management_access_dependency)]


@router.get('/history', response_model=ScanHistoryPage)
async def history(response: Response, filters: Annotated[ScanHistoryQuery, Query()]) -> ScanHistoryPage:
    response.headers['Cache-Control'] = 'no-store'
    return await scan_history(filters.before, filters.limit, filters.state, filters.source, filters.schedule_id)


@router.get('/statistics', response_model=list[ScanChartPoint])
async def statistics(response: Response, filters: Annotated[ScanHistoryQuery, Query()]) -> list[ScanChartPoint]:
    response.headers['Cache-Control'] = 'no-store'
    return await scan_statistics(filters)


@router.get('/schedules', response_model=list[ScheduleStatus])
async def schedules(response: Response) -> list[ScheduleStatus]:
    response.headers['Cache-Control'] = 'no-store'
    return [ScheduleStatus.model_validate(row, from_attributes=True) for row in await ScanSchedule.all().order_by('id')]


@router.post('/schedules', response_model=ScheduleStatus, status_code=201)
async def create_schedule(payload: SchedulePayload) -> ScheduleStatus:
    return ScheduleStatus.model_validate(await save_schedule(payload), from_attributes=True)


@router.put('/schedules/{schedule_id}', response_model=ScheduleStatus)
async def update_schedule(schedule_id: int, payload: SchedulePayload) -> ScheduleStatus:
    row = await save_schedule(payload, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Расписание не найдено')
    return ScheduleStatus.model_validate(row, from_attributes=True)


@router.patch('/schedules/{schedule_id}/enabled', response_model=ScheduleStatus)
async def enable_schedule(schedule_id: int, payload: ScheduleEnabled) -> ScheduleStatus:
    row = await set_enabled(schedule_id, enabled=payload.enabled)
    if row is None:
        raise HTTPException(status_code=404, detail='Расписание не найдено')
    return ScheduleStatus.model_validate(row, from_attributes=True)


@router.delete('/schedules/{schedule_id}', status_code=204)
async def delete_schedule(schedule_id: int) -> None:
    if not await ScanSchedule.filter(id=schedule_id).delete():
        raise HTTPException(status_code=404, detail='Расписание не найдено')


@router.get('/{scan_id}/items', response_model=ScanItemsPage)
async def items(
    scan_id: int,
    response: Response,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    item_state: Annotated[ScanItemState | None, Query(alias='state')] = None,
) -> ScanItemsPage:
    response.headers['Cache-Control'] = 'no-store'
    if not await ScanRun.filter(id=scan_id).exists():
        raise HTTPException(status_code=404, detail='Запуск не найден')
    return await scan_items(scan_id, after, limit, item_state)


@router.get('/{scan_id}/items/{item_id}', response_model=ScanItemDetail)
async def item(scan_id: int, item_id: int, response: Response) -> ScanItemDetail:
    response.headers['Cache-Control'] = 'no-store'
    detail = await scan_item_detail(scan_id, item_id)
    if detail is None:
        raise HTTPException(status_code=404, detail='Пункт запуска не найден')
    return detail


async def _retry(scan_id: int, claims: dict[str, Any], item_id: int | None = None) -> ScanStatus:
    async with in_transaction() as connection:
        previous = await ScanRun.filter(id=scan_id).using_db(connection).select_for_update().first()
        if previous is None:
            raise HTTPException(status_code=404, detail='Запуск не найден')
        if previous.state in {ScanState.QUEUED, ScanState.RUNNING, ScanState.STOPPING}:
            raise HTTPException(status_code=409, detail='Дождитесь завершения или остановки запуска')
        options = ScanOptions.model_validate(previous.options)
        if item_id is not None:
            previous_item = await ScanItem.filter(id=item_id, scan_id=scan_id).select_related('target').first()
            if previous_item is None:
                raise HTTPException(status_code=404, detail='Пункт запуска не найден')
            options.project_ids = [previous_item.target.gitlab_id]
        run = await enqueue_scan(claims.get('preferred_username'), options, retry_of_id=scan_id)
        if run is None:
            raise HTTPException(status_code=409, detail='Сканирование уже запущено')
        return await scan_status(run)


@router.post('/{scan_id}/retry', response_model=ScanStatus, status_code=202)
async def retry(scan_id: int, claims: Claims) -> ScanStatus:
    return await _retry(scan_id, claims)


@router.post('/{scan_id}/items/{item_id}/retry', response_model=ScanStatus, status_code=202)
async def retry_item(scan_id: int, item_id: int, claims: Claims) -> ScanStatus:
    return await _retry(scan_id, claims, item_id)
