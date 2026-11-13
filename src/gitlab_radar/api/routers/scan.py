import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status

from gitlab_radar.application.scans import request_scan, scan_status, stop_scan
from gitlab_radar.auth import (
    authenticated_access_dependency,
    consume_websocket_ticket,
    management_access_dependency,
)
from gitlab_radar.database.models import ScanRun
from gitlab_radar.schemas.scan import ScanStatus, ScanUpdates

router = APIRouter()


@router.websocket('/ws')
async def scan_status_socket(websocket: WebSocket) -> None:
    ticket = websocket.query_params.get('ticket')
    if ticket is None or not await consume_websocket_ticket(ticket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    previous_status: dict | None = None
    try:
        while True:
            status_payload = (await scan_status()).model_dump(mode='json')
            if status_payload != previous_status:
                await websocket.send_json(status_payload)
                previous_status = status_payload
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1)
            except TimeoutError:
                continue
            if message['type'] == 'websocket.disconnect':
                break
    except WebSocketDisconnect:
        pass


@router.get('/', response_model=ScanStatus, dependencies=[Depends(authenticated_access_dependency)])
async def get_scan_status(response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    return await scan_status()


@router.post('/', status_code=status.HTTP_202_ACCEPTED)
async def scan(
    response: Response, claims: Annotated[dict[str, Any], Depends(management_access_dependency)]
) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    result = await request_scan(claims.get('preferred_username'))
    if result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Сканирование уже запущено')
    return result


@router.get('/{scan_id}', response_model=ScanStatus, dependencies=[Depends(authenticated_access_dependency)])
async def get_run(scan_id: int, response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    run = await ScanRun.get_or_none(id=scan_id)
    if run is None:
        raise HTTPException(status_code=404, detail='Запуск не найден')
    return await scan_status(run)


@router.post('/{scan_id}/stop', response_model=ScanStatus, dependencies=[Depends(management_access_dependency)])
async def stop_run(scan_id: int, response: Response) -> ScanStatus:
    response.headers['Cache-Control'] = 'no-store'
    result = await stop_scan(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Запуск не найден')
    return result


@router.get('/{scan_id}/updates', response_model=ScanUpdates, dependencies=[Depends(authenticated_access_dependency)])
async def get_updates(
    scan_id: int,
    response: Response,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> ScanUpdates:
    response.headers['Cache-Control'] = 'no-store'
    run = await ScanRun.filter(id=scan_id).only('id', 'updated_project_ids').first()
    if run is None:
        raise HTTPException(status_code=404, detail='Запуск не найден')
    if after > len(run.updated_project_ids):
        raise HTTPException(status_code=422, detail='Курсор выходит за границы запуска')
    project_ids = run.updated_project_ids[after : after + limit]
    cursor = after + len(project_ids)
    return ScanUpdates(
        scan_id=scan_id, project_ids=project_ids, cursor=cursor, has_more=cursor < len(run.updated_project_ids)
    )
